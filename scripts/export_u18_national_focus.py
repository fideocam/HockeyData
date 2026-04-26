#!/usr/bin/env python3
"""
Export focused current U18 national-team Sankey graphics.

Outputs:
  - FIN U18 as its own SVG + PNG, with a clickable player-link panel in the SVG.
  - One collated SVG + PNG for all non-FIN U18 national teams.

Defaults:
  - season 2026 (2025-26)
  - 1920x1080 HDTV dimensions
  - output folder exports/u18_national_focus_2025_26
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

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SCRIPT_DIR))

from leijonat_client import get_team_main_data, get_team_season_roster, roster_row_link_id, search_players  # noqa: E402
from sankey_builder import SankeyData, build_career_paths_sankey  # noqa: E402
from export_sankey_svgs import (  # noqa: E402
    DEFAULT_TEAM_URL_TEMPLATE,
    careers_for_players,
    discover_teams,
    level_name,
    render_png,
    render_svg,
    safe_component,
    season_label,
)

DEFAULT_OUT = ROOT / "exports" / "u18_national_focus_2025_26"
U18_NATIONAL_LEVEL_ID = "130"
PLAYER_URL_TEMPLATE = "https://www.leijonat.fi/index.php/pelaajat?lkq={linkid}"
STAFF_ROLE_WORDS = {
    "coach",
    "director",
    "doctor",
    "equipment",
    "fysioterapeutti",
    "general manager",
    "huoltaja",
    "joukkueenjohtaja",
    "lääkäri",
    "manager",
    "päävalmentaja",
    "staff",
    "team leader",
    "trainer",
    "valmentaja",
    "video",
}
PLAYER_ROLE_WORDS = {
    "center",
    "defenseman",
    "forward",
    "goalie",
    "goalkeeper",
    "hyökkääjä",
    "keskushyökkääjä",
    "maalivahti",
    "puolustaja",
    "wing",
}


def is_fin_u18(meta: dict) -> bool:
    return str(meta.get("LevelID") or "") == U18_NATIONAL_LEVEL_ID and str(meta.get("TeamName") or "").upper() == "FIN U18"


def is_other_u18_national(meta: dict) -> bool:
    return str(meta.get("LevelID") or "") == U18_NATIONAL_LEVEL_ID and str(meta.get("TeamAbbrv") or "").upper() != "SJL"


def player_url(link_id: str, template: str) -> str:
    return template.format(linkid=str(link_id or "").strip())


def is_player_roster_row(row: dict) -> bool:
    role_text = " ".join(
        str(row.get(key) or "")
        for key in ("RoleName", "RoleName_EN", "RoleAbbrv", "RoleAbbrv_EN", "Position")
    ).casefold()
    if any(word in role_text for word in STAFF_ROLE_WORDS):
        return False
    if any(word in role_text for word in PLAYER_ROLE_WORDS):
        return True
    # Player rows normally have jersey numbers; staff/contact rows often do not.
    return bool(str(row.get("JerseyNr") or "").strip())


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


async def resolve_player_card_links(
    client: httpx.AsyncClient,
    players: list[dict],
    concurrency: int,
) -> None:
    """
    Team-card roster PersonID works for career APIs, but the public player-card
    page is more reliable when opened with a LinkID from the player search API.
    """
    sem = asyncio.Semaphore(max(1, concurrency))

    async def resolve(player: dict) -> None:
        last = str(player.get("LastName") or "").strip()
        first = str(player.get("FirstName") or "").strip()
        if not last or not first:
            return
        query = f"{last} {first}"
        expected_last = normalize_name(last)
        expected_first = normalize_name(first)
        async with sem:
            try:
                rows = await search_players(client, player_name=query)
            except Exception:
                rows = []
        exact = [
            row for row in rows
            if normalize_name(str(row.get("LastName") or "")) == expected_last
            and normalize_name(str(row.get("FirstName") or "")) == expected_first
        ]
        if exact:
            player["PlayerCardLinkID"] = str(exact[0].get("LinkID") or "").strip()

    await asyncio.gather(*(resolve(player) for player in players))


def fit_sankey_to_frame(data: SankeyData, x_min: float = 0.04, x_max: float = 0.84) -> SankeyData:
    """Keep right-side team labels inside static SVG/PNG frame."""
    if not data.node_x or len(data.node_x) != len(data.nodes):
        return data
    current_min = min(data.node_x)
    current_max = max(data.node_x)
    if current_max <= current_min:
        data.node_x = [0.48 for _ in data.node_x]
        return data
    scale = (x_max - x_min) / (current_max - current_min)
    data.node_x = [x_min + (x - current_min) * scale for x in data.node_x]
    data.node_y = [min(0.92, max(0.03, y)) for y in data.node_y]
    return data


def player_link_map(players: list[dict]) -> dict[str, str]:
    links: dict[str, str] = {}
    for player in players:
        name = f"{player.get('LastName', '')} {player.get('FirstName', '')}".strip()
        link_id = str(player.get("PlayerCardLinkID") or player.get("LinkID") or "").strip()
        if name and link_id:
            links.setdefault(name, link_id)
    return links


def split_links_per_player(data: SankeyData, players: list[dict], url_template: str) -> tuple[SankeyData, list[str]]:
    """
    Keep team nodes aggregated, but draw one ribbon per player so each flow can
    link to that player's card instead of linking team nodes to unreliable teams.
    """
    links_by_name = player_link_map(players)
    expanded_links: list[dict] = []
    urls: list[str] = []
    for link in data.links:
        player_names = [str(name) for name in link.get("players", []) if str(name).strip()]
        if not player_names:
            expanded_links.append(link)
            urls.append("")
            continue
        for name in player_names:
            expanded_links.append({
                **link,
                "value": 1,
                "label": f"{data.nodes[link['source']]} → {data.nodes[link['target']]}: {name}",
                "players": [name],
            })
            urls.append(player_url(links_by_name.get(name, ""), url_template))
    data.links = expanded_links
    return data, urls


def inject_flow_links(svg: str, flow_urls: list[str]) -> str:
    """Wrap Plotly Sankey ribbons in player-card anchors, preserving link order."""
    matches = list(re.finditer(r'<path class="sankey-link"[\s\S]*?/>', svg))
    if not matches:
        return svg
    parts: list[str] = []
    cursor = 0
    for i, match in enumerate(matches):
        parts.append(svg[cursor:match.start()])
        path_svg = match.group(0)
        url = flow_urls[i] if i < len(flow_urls) else ""
        if url:
            href = html.escape(url, quote=True)
            label = html.escape(f"Open player card: {url}")
            path_svg = path_svg.replace('style="', 'style="pointer-events: all; ')
            parts.append(
                f'<a xlink:href="{href}" href="{href}" target="_blank" '
                f'style="pointer-events: all; cursor: pointer;"><title>{label}</title>{path_svg}</a>'
            )
        else:
            parts.append(path_svg)
        cursor = match.end()
    parts.append(svg[cursor:])
    return "".join(parts)


async def roster_players(
    client: httpx.AsyncClient,
    team_id: str,
    season: str,
    max_players: int,
) -> tuple[list[dict], str, str, str]:
    meta = await get_team_main_data(client, team_id)
    if not meta:
        raise RuntimeError(f"missing metadata for {team_id}")
    association_id = str(meta.get("AssociationID") or "")
    roster = await get_team_season_roster(client, team_id, season, association_id)
    if not roster:
        raise RuntimeError(f"no roster for {team_id} in {season}")

    team_abbr = str(meta.get("TeamAbbrv") or "").strip()
    team_name = str(meta.get("TeamName") or team_abbr).strip()
    level_id = str(meta.get("LevelID") or "0")
    players: list[dict] = []
    for row in roster:
        if len(players) >= max_players:
            break
        if not is_player_roster_row(row):
            continue
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
            "JerseyNr": row.get("JerseyNr", ""),
            "TeamID": team_id,
            "TeamName": team_name,
        })
    return players, team_abbr, team_name, level_id


def linked_player_panel(svg: str, players: list[dict], width: int, height: int, url_template: str) -> str:
    """Append a compact linked roster panel to the bottom of the SVG."""
    if "</svg>" not in svg:
        return svg
    sorted_players = sorted(players, key=lambda p: (str(p.get("LastName") or ""), str(p.get("FirstName") or "")))
    col_count = 5 if len(sorted_players) > 48 else 4
    row_height = 17
    rows_per_col = max(1, (len(sorted_players) + col_count - 1) // col_count)
    panel_height = min(int(height * 0.42), 46 + rows_per_col * row_height + 12)
    top = max(0, height - panel_height)
    col_width = width / col_count
    start_y = 34
    items_per_col = max(1, (panel_height - 46) // row_height)

    elems = [
        f'<g class="linked-player-panel" transform="translate(0,{top})">',
        f'<rect x="0" y="0" width="{width}" height="{panel_height}" fill="#ffffff" fill-opacity="0.96" stroke="#E5E7EB"/>',
        '<text x="18" y="22" font-family="system-ui, Arial, sans-serif" font-size="16" font-weight="700" fill="#111827">FIN U18 roster - clickable player links</text>',
    ]
    for i, player in enumerate(sorted_players):
        col = i // items_per_col
        row = i % items_per_col
        if col >= col_count:
            continue
        x = 18 + col * col_width
        y = start_y + row * row_height
        jersey = str(player.get("JerseyNr") or "").strip()
        jersey_prefix = f"#{jersey} " if jersey and jersey != "0" else ""
        name = f"{jersey_prefix}{player.get('LastName', '')} {player.get('FirstName', '')}".strip()
        href = html.escape(player_url(player.get("LinkID", ""), url_template), quote=True)
        label = html.escape(name)
        elems.append(
            f'<a xlink:href="{href}" href="{href}" target="_blank">'
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="system-ui, Arial, sans-serif" '
            f'font-size="12" fill="#003580" text-decoration="underline">{label}</text></a>'
        )
    elems.append("</g>")
    return svg.replace("</svg>", "".join(elems) + "</svg>")


def output_pair(output: Path, *parts: str) -> tuple[Path, Path]:
    base = output.joinpath(*(safe_component(part) for part in parts))
    return base.with_suffix(".svg"), base.with_suffix(".png")


async def export_fin_u18(
    client: httpx.AsyncClient,
    args: argparse.Namespace,
    team_id: str,
    team_card_id_cache: dict[tuple[str, str], str],
) -> tuple[Path, Path]:
    players, team_abbr, team_name, level_id = await roster_players(client, team_id, args.season, args.max_players)
    await resolve_player_card_links(client, players, args.link_concurrency)
    careers = await careers_for_players(client, players, concurrency=args.career_concurrency)
    cohort = frozenset(p["LinkID"] for p in players)
    sankey = build_career_paths_sankey(
        players,
        careers,
        team_abbr,
        focal_season=args.season,
        level_id=level_id,
        direction="to_current",
        max_seasons_back=10,
        cohort_link_ids=cohort,
    )
    sankey = fit_sankey_to_frame(sankey)
    sankey, flow_urls = split_links_per_player(sankey, players, args.player_url_template)
    title = f"{team_name} ({season_label(args.season)})"
    subtitle = f"{level_name(level_id)} · {sankey.confirmed_count} players · click a flow to open that player"
    svg = render_svg(sankey, title, subtitle, node_urls=[], width=args.width, height=args.height)
    svg = inject_flow_links(svg, flow_urls)
    png = render_png(sankey, title, subtitle, width=args.width, height=args.height)

    svg_file, png_file = output_pair(args.output, season_label(args.season), "FIN U18", "fin-u18-linked-players")
    svg_file.parent.mkdir(parents=True, exist_ok=True)
    svg_file.write_text(svg, encoding="utf-8")
    png_file.write_bytes(png)
    return svg_file, png_file


async def export_other_u18_collated(
    client: httpx.AsyncClient,
    args: argparse.Namespace,
    team_ids: list[str],
    team_card_id_cache: dict[tuple[str, str], str],
) -> tuple[Path, Path]:
    all_players: list[dict] = []
    careers: dict[str, dict] = {}
    for team_id in team_ids:
        try:
            players, _, team_name, _ = await roster_players(client, team_id, args.season, args.max_players)
            print(f"Adding {team_name}: {len(players)} players", flush=True)
            await resolve_player_card_links(client, players, args.link_concurrency)
            team_careers = await careers_for_players(client, players, concurrency=args.career_concurrency)
            all_players.extend(players)
            careers.update(team_careers)
        except Exception as exc:
            print(f"skip collated {team_id}: {exc}", flush=True)

    # De-duplicate players who may appear in multiple tournament/team rows.
    unique_players: dict[str, dict] = {}
    for player in all_players:
        unique_players.setdefault(player["LinkID"], player)
    players = list(unique_players.values())
    cohort = frozenset(unique_players)
    sankey = build_career_paths_sankey(
        players,
        careers,
        "Other U18 national teams",
        focal_season=args.season,
        level_id=U18_NATIONAL_LEVEL_ID,
        direction="to_current",
        max_seasons_back=10,
        cohort_link_ids=cohort,
    )
    sankey = fit_sankey_to_frame(sankey)
    sankey, flow_urls = split_links_per_player(sankey, players, args.player_url_template)
    title = f"Other U18 national teams ({season_label(args.season)})"
    subtitle = f"{sankey.confirmed_count} unique players · click a flow to open that player"
    svg = render_svg(sankey, title, subtitle, node_urls=[], width=args.width, height=args.height)
    svg = inject_flow_links(svg, flow_urls)
    png = render_png(sankey, title, subtitle, width=args.width, height=args.height)

    svg_file, png_file = output_pair(args.output, season_label(args.season), "Other U18 national teams", "other-u18-national-teams-collated")
    svg_file.parent.mkdir(parents=True, exist_ok=True)
    svg_file.write_text(svg, encoding="utf-8")
    png_file.write_bytes(png)
    return svg_file, png_file


async def export_all(args: argparse.Namespace) -> None:
    args.output.mkdir(parents=True, exist_ok=True)
    gitignore = args.output / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")

    async with httpx.AsyncClient() as client:
        rows = await discover_teams(client, args.team_query)
        fin_team_id = ""
        other_team_ids: list[str] = []
        for row in rows:
            team_id = str(row.get("TeamID") or "").strip()
            if not team_id:
                continue
            meta = await get_team_main_data(client, team_id)
            if not meta or str(meta.get("LevelID") or "") != U18_NATIONAL_LEVEL_ID:
                continue
            team_name = str(meta.get("TeamName") or "")
            if is_fin_u18(meta):
                fin_team_id = team_id
            elif is_other_u18_national(meta):
                other_team_ids.append(team_id)

        if not fin_team_id:
            raise RuntimeError("Could not find FIN U18 team")

        team_card_id_cache: dict[tuple[str, str], str] = {}
        print(f"Exporting FIN U18 linked-player graphic from team {fin_team_id}", flush=True)
        fin_svg, fin_png = await export_fin_u18(client, args, fin_team_id, team_card_id_cache)
        print(f"FIN U18 -> {fin_svg.relative_to(args.output)} + {fin_png.relative_to(args.output)}", flush=True)

        print(f"Exporting collated chart for {len(other_team_ids)} other U18 national teams", flush=True)
        other_svg, other_png = await export_other_u18_collated(client, args, other_team_ids, team_card_id_cache)
        print(f"Other U18 -> {other_svg.relative_to(args.output)} + {other_png.relative_to(args.output)}", flush=True)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export FIN U18 linked-player and other U18 national collated Sankeys.")
    parser.add_argument("--season", default="2026", help="Season end year, e.g. 2026 for 2025-26")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Output directory")
    parser.add_argument("--team-query", default="U18", help="Team search query used to find U18 national teams")
    parser.add_argument("--max-players", type=int, default=300)
    parser.add_argument("--career-concurrency", type=int, default=32)
    parser.add_argument("--link-concurrency", type=int, default=16)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--team-url-template", default=DEFAULT_TEAM_URL_TEMPLATE)
    parser.add_argument("--player-url-template", default=PLAYER_URL_TEMPLATE)
    return parser.parse_args(list(argv))


if __name__ == "__main__":
    asyncio.run(export_all(parse_args(sys.argv[1:])))
