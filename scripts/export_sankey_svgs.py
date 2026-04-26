#!/usr/bin/env python3
"""
Export HockeyData Sankey diagrams as SVG files.

Default export:
  - season 2026 (2025-26)
  - career paths into each team
  - output folder exports/sankey_2025_26

Examples:
  python3 scripts/export_sankey_svgs.py --level 89 --limit 10
  python3 scripts/export_sankey_svgs.py --group U16 --mode to-current
  python3 scripts/export_sankey_svgs.py --team-query Karhu-Kissat

The output directory contains its own .gitignore so generated SVG files are not
uploaded to GitHub.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import re
import sys
from pathlib import Path
from typing import Iterable

import httpx
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from leijonat_client import (  # noqa: E402
    _search_teams_request,
    get_player_career,
    get_team_main_data,
    get_team_season_roster,
    roster_row_link_id,
    search_teams,
)
from main import LEVELS  # noqa: E402
from sankey_builder import (  # noqa: E402
    SankeyData,
    build_career_paths_sankey,
    build_from_previous_sankey,
    build_to_current_sankey,
)
from team_colors import hex_to_rgba, team_color  # noqa: E402

DEFAULT_OUT = ROOT / "exports" / "sankey_2025_26"
INITIALS = "ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ"
# Keep camp/misc levels out, but include national-team levels:
# 127 men, 128 U20, 130 U18, 131 U17, 132 U16, 133 women, 134 women U18.
PRACTICE_AND_MISC_LEVELS = {"0", "123", "135", "139", "153"}
DEFAULT_TEAM_URL_TEMPLATE = "https://www.leijonat.fi/joukkueet?teamid={teamid}"


def season_label(season: str) -> str:
    try:
        y = int(season)
        return f"{y - 1}-{str(y)[2:]}"
    except ValueError:
        return season


def slugify(value: str) -> str:
    s = value.lower()
    s = s.replace("å", "a").replace("ä", "a").replace("ö", "o")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "team"


def safe_component(value: str) -> str:
    """Readable directory name that avoids path separators and shell-hostile chars."""
    s = re.sub(r"[/\\:]+", "-", value).strip()
    s = re.sub(r"\s+", " ", s)
    return s or "Unknown"


def level_group(level_id: str) -> str:
    for level in LEVELS:
        if str(level["id"]) == str(level_id):
            return str(level["group"])
    return "Other"


def level_name(level_id: str) -> str:
    for level in LEVELS:
        if str(level["id"]) == str(level_id):
            return str(level["name"])
    return f"Level {level_id}"


def team_url(team_id: str, template: str) -> str:
    tid = str(team_id or "").strip()
    return template.format(teamid=tid) if tid else ""


def _same_team_abbr(value: str, expected: str) -> bool:
    return re.sub(r"\s+", "", value or "").casefold() == re.sub(r"\s+", "", expected or "").casefold()


async def resolve_team_card_id(
    client: httpx.AsyncClient,
    team_abbr: str,
    level_id: str,
    cache: dict[tuple[str, str], str],
) -> str:
    """Resolve career-history team abbreviations to public joukkuekortti team ids."""
    key = (team_abbr, level_id)
    if key in cache:
        return cache[key]

    rows = await search_teams(client, team_abbr)
    abbr_rows = [
        row for row in rows
        if _same_team_abbr(str(row.get("AssociationAbbrv", "")), team_abbr)
        or _same_team_abbr(str(row.get("TeamName", "")), team_abbr)
    ] or rows

    fallback_id = ""
    for row in abbr_rows:
        candidate_id = str(row.get("TeamID", "")).strip()
        if not candidate_id:
            continue
        if not fallback_id:
            fallback_id = candidate_id
        try:
            meta = await get_team_main_data(client, candidate_id)
        except Exception:
            meta = None
        if meta and str(meta.get("LevelID") or "") == str(level_id):
            cache[key] = candidate_id
            return candidate_id

    cache[key] = fallback_id
    return fallback_id


async def node_urls_for(
    client: httpx.AsyncClient,
    data: SankeyData,
    fallback_team_id: str,
    fallback_team_abbr: str,
    url_template: str,
    cache: dict[tuple[str, str], str],
    concurrency: int = 8,
) -> list[str]:
    specs: list[tuple[str, str, str]] = []
    meta_by_index = data.node_meta if len(data.node_meta) == len(data.nodes) else []
    for i, label in enumerate(data.nodes):
        team_abbr = fallback_team_abbr if label == data.focal_team else ""
        level_id = ""
        if meta_by_index:
            team_abbr = str(meta_by_index[i].get("team", "") or team_abbr)
            level_id = str(meta_by_index[i].get("level_id", "") or "")
        specs.append((label, team_abbr, level_id))

    unique_keys = sorted({(team_abbr, level_id) for _, team_abbr, level_id in specs if team_abbr and level_id})
    sem = asyncio.Semaphore(max(1, concurrency))

    async def resolve_key(team_abbr: str, level_id: str) -> None:
        async with sem:
            await resolve_team_card_id(client, team_abbr, level_id, cache)

    await asyncio.gather(*(resolve_key(team_abbr, level_id) for team_abbr, level_id in unique_keys))

    urls: list[str] = []
    for label, team_abbr, level_id in specs:
        team_id = cache.get((team_abbr, level_id), "") if team_abbr and level_id else ""
        if not team_id and (label == data.focal_team or label.endswith(f"· {data.focal_team}")):
            team_id = fallback_team_id
        urls.append(team_url(team_id, url_template))
    return urls


async def discover_teams(client: httpx.AsyncClient, query: str = "") -> list[dict]:
    """Return unique current Leijonat team search rows."""
    rows: list[dict] = []
    if query:
        rows = await search_teams(client, query)
    else:
        batches = await asyncio.gather(
            *[_search_teams_request(client, "", initial) for initial in INITIALS],
            return_exceptions=True,
        )
        for batch in batches:
            if not isinstance(batch, Exception):
                rows.extend(batch)

    unique: dict[str, dict] = {}
    for row in rows:
        tid = str(row.get("TeamID", "")).strip()
        if tid:
            unique[tid] = row
    return list(unique.values())


async def careers_for_players(client: httpx.AsyncClient, players: list[dict], concurrency: int = 12) -> dict[str, dict]:
    careers: dict[str, dict] = {}
    sem = asyncio.Semaphore(concurrency)

    async def fetch(player: dict) -> None:
        link_id = player["LinkID"]
        async with sem:
            try:
                careers[link_id] = await get_player_career(client, link_id)
            except Exception:
                careers[link_id] = {"Skater": [], "Goalkeeper": []}

    await asyncio.gather(*(fetch(p) for p in players))
    return careers


async def roster_context(
    client: httpx.AsyncClient,
    team_id: str,
    season: str,
    max_players: int,
    career_concurrency: int,
) -> tuple[list[dict], dict[str, dict], str, str, str]:
    meta = await get_team_main_data(client, team_id)
    if not meta:
        raise RuntimeError("missing team metadata")

    association_id = str(meta.get("AssociationID") or "")
    roster = await get_team_season_roster(client, team_id, season, association_id)
    if not roster:
        raise RuntimeError(f"no roster for season {season}")

    team_abbr = str(meta.get("TeamAbbrv") or "").strip()
    team_name = str(meta.get("TeamName") or team_abbr).strip()
    level_id = str(meta.get("LevelID") or "0")

    players: list[dict] = []
    for row in roster[:max_players]:
        link_id = roster_row_link_id(row.get("PersonID", ""))
        if not link_id:
            continue
        players.append({
            "PersonID": link_id,
            "LinkID": link_id,
            "LastName": row.get("LastName", ""),
            "FirstName": row.get("FirstName", ""),
            "Association": team_abbr,
            "Position": row.get("RoleName", ""),
        })
    if not players:
        raise RuntimeError("roster has no player ids")

    careers = await careers_for_players(client, players, concurrency=career_concurrency)
    return players, careers, team_abbr, team_name, level_id


def build_sankey(mode: str, players: list[dict], careers: dict[str, dict], team: str, season: str, level: str) -> SankeyData:
    cohort = frozenset(p["LinkID"] for p in players)
    if mode == "to-current":
        return build_to_current_sankey(players, careers, team, season, level, cohort_link_ids=cohort)
    if mode == "from-previous":
        return build_from_previous_sankey(players, careers, team, season, level, cohort_link_ids=cohort)
    direction = "from_previous" if mode == "career-out" else "to_current"
    return build_career_paths_sankey(
        players,
        careers,
        team,
        focal_season=season,
        level_id=level,
        direction=direction,
        max_seasons_back=10,
        cohort_link_ids=cohort,
    )


def inject_node_links(svg: str, node_urls: list[str]) -> str:
    """Wrap Plotly sankey-node groups in SVG anchors, preserving node order."""
    matches = list(re.finditer(r'<g class="sankey-node"[\s\S]*?</g>', svg))
    if not matches:
        return svg

    parts: list[str] = []
    cursor = 0
    for i, match in enumerate(matches):
        parts.append(svg[cursor:match.start()])
        node_svg = match.group(0)
        url = node_urls[i] if i < len(node_urls) else ""
        if url:
            href = html.escape(url, quote=True)
            parts.append(
                f'<a xlink:href="{href}" href="{href}" target="_blank" '
                f'style="pointer-events: all; cursor: pointer;">{node_svg}</a>'
            )
        else:
            parts.append(node_svg)
        cursor = match.end()
    parts.append(svg[cursor:])
    return "".join(parts)


def build_sankey_figure(
    data: SankeyData,
    title: str,
    subtitle: str,
    width: int,
    height: int,
) -> go.Figure:
    career = data.mode.startswith("career_")

    def team_part(label: str) -> str:
        return label.split(" · ", 1)[1] if career and " · " in label else label

    node_colors = []
    for label in data.nodes:
        node_colors.append(team_color(team_part(label)))

    link_colors = []
    for link in data.links:
        source_idx = int(link["source"])
        source_team = team_part(data.nodes[source_idx]) if 0 <= source_idx < len(data.nodes) else ""
        link_colors.append(hex_to_rgba(team_color(source_team), 0.42))

    node: dict = {
        "pad": 12 if career else 18,
        "thickness": 16 if career else 20,
        "line": {"color": "rgba(0,0,0,0)", "width": 0},
        "label": data.nodes,
        "color": node_colors,
    }
    if career and len(data.node_x) == len(data.nodes) and len(data.node_y) == len(data.nodes):
        node["x"] = data.node_x
        node["y"] = data.node_y

    fig = go.Figure(data=[go.Sankey(
        arrangement="fixed" if "x" in node else "snap",
        orientation="h",
        node=node,
        link={
            "source": [l["source"] for l in data.links],
            "target": [l["target"] for l in data.links],
            "value": [l["value"] for l in data.links],
            "label": [l.get("label", "") for l in data.links],
            "color": link_colors,
        },
    )])
    fig.update_layout(
        title={"text": f"{html.escape(title)}<br><sup>{html.escape(subtitle)}</sup>", "x": 0.02, "xanchor": "left"},
        font={"family": "system-ui, Arial, sans-serif", "size": 11 if career else 13, "color": "#111827"},
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin={"l": 16, "r": 16, "t": 72, "b": 16},
        width=width,
        height=height,
    )
    return fig


def render_svg(
    data: SankeyData,
    title: str,
    subtitle: str,
    size: int = 1200,
    node_urls: list[str] | None = None,
    width: int | None = None,
    height: int | None = None,
) -> str:
    image_width = width or size
    image_height = height or size
    fig = build_sankey_figure(data, title, subtitle, image_width, image_height)
    svg = fig.to_image(format="svg", width=image_width, height=image_height).decode("utf-8")
    return inject_node_links(svg, node_urls or [])


def render_png(
    data: SankeyData,
    title: str,
    subtitle: str,
    width: int = 1920,
    height: int = 1080,
) -> bytes:
    fig = build_sankey_figure(data, title, subtitle, width, height)
    return fig.to_image(format="png", width=width, height=height)


def output_file_for(args: argparse.Namespace, team_id: str, team_name: str, level_id: str) -> Path:
    return (
        args.output
        / safe_component(season_label(args.season))
        / safe_component(level_group(level_id))
        / safe_component(level_name(level_id))
        / safe_component(f"{team_name} [{team_id}]")
        / f"{slugify(args.mode)}.svg"
    )


def should_export(meta: dict, args: argparse.Namespace) -> bool:
    level_id = str(meta.get("LevelID") or "0")
    if level_id in PRACTICE_AND_MISC_LEVELS:
        return False
    if args.level and level_id not in set(args.level):
        return False
    if args.group and level_group(level_id).lower() != args.group.lower():
        return False
    return True


async def export_all(args: argparse.Namespace) -> None:
    args.output.mkdir(parents=True, exist_ok=True)
    gitignore = args.output / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")

    async with httpx.AsyncClient() as client:
        rows = await discover_teams(client, args.team_query)
        print(f"Discovered {len(rows)} candidate teams", flush=True)

        exported = 0
        skipped = 0
        team_card_id_cache: dict[tuple[str, str], str] = {}
        for row in rows:
            team_id = str(row.get("TeamID", "")).strip()
            if not team_id:
                continue
            try:
                meta = await get_team_main_data(client, team_id)
                if not meta or not should_export(meta, args):
                    skipped += 1
                    continue
                level_id = str(meta.get("LevelID") or "0")
                team_name_for_path = str(meta.get("TeamName") or team_id).strip()
                out_file = output_file_for(args, team_id, team_name_for_path, level_id)
                if args.skip_existing and out_file.exists():
                    exported += 1
                    print(f"[{exported}] exists {out_file.relative_to(args.output)}", flush=True)
                    if args.limit and exported >= args.limit:
                        break
                    continue
                print(f"Exporting {meta.get('TeamName') or team_id}...", flush=True)

                players, careers, team_abbr, team_name, level_id = await roster_context(
                    client, team_id, args.season, args.max_players, args.career_concurrency
                )
                sankey = build_sankey(args.mode, players, careers, team_abbr, args.season, level_id)
                node_urls = await node_urls_for(
                    client,
                    sankey,
                    fallback_team_id=team_id,
                    fallback_team_abbr=team_abbr,
                    url_template=args.team_url_template,
                    cache=team_card_id_cache,
                    concurrency=args.link_concurrency,
                )
                title = f"{team_name} ({season_label(args.season)})"
                subtitle = f"{level_name(level_id)} · {sankey.confirmed_count} players · {args.mode}"
                svg = render_svg(sankey, title, subtitle, args.size, node_urls)
                out_file = output_file_for(args, team_id, team_name, level_id)
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(svg, encoding="utf-8")
                exported += 1
                print(f"[{exported}] {team_name} -> {out_file.relative_to(args.output)}", flush=True)
                if args.limit and exported >= args.limit:
                    break
            except Exception as exc:
                skipped += 1
                print(f"skip {team_id}: {exc}", flush=True)

    print(f"Done. Exported {exported} SVG files to {args.output}. Skipped {skipped}.", flush=True)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export HockeyData Sankey diagrams to SVG.")
    parser.add_argument("--season", default="2026", help="Season end year, e.g. 2026 for 2025-26")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Output directory")
    parser.add_argument("--mode", choices=["career-in", "career-out", "to-current", "from-previous"], default="career-in")
    parser.add_argument("--level", action="append", help="Export only this level id; repeat for multiple")
    parser.add_argument("--group", help="Export only one level group, e.g. U16, U18, Men")
    parser.add_argument("--team-query", default="", help="Export only teams returned by this team search")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N exported teams")
    parser.add_argument("--max-players", type=int, default=300, help="Max roster players per team")
    parser.add_argument("--size", type=int, default=1200, help="Square SVG size in pixels")
    parser.add_argument("--career-concurrency", type=int, default=24, help="Concurrent player career lookups per team")
    parser.add_argument("--link-concurrency", type=int, default=8, help="Concurrent team-card link lookups")
    parser.add_argument("--skip-existing", action="store_true", help="Skip SVGs that already exist")
    parser.add_argument(
        "--team-url-template",
        default=DEFAULT_TEAM_URL_TEMPLATE,
        help="Team link URL template; use {teamid} where the team id should be inserted",
    )
    return parser.parse_args(list(argv))


if __name__ == "__main__":
    asyncio.run(export_all(parse_args(sys.argv[1:])))
