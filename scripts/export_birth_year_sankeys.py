#!/usr/bin/env python3
"""
Export Sankey SVGs for a birth-year cohort, grouped by each player's starting team.

The public Leijonat roster/player APIs often leave DOB blank for junior players.
When DOB is unavailable, this script infers the cohort from the first recorded
career season. For 2009-born players, the default first season is 2020
(2019-20), which is where the junior stats usually begin.

Examples:
  python3 scripts/export_birth_year_sankeys.py --initials ABC --max-pages-per-initial 2
  python3 scripts/export_birth_year_sankeys.py --source current-rosters --team-query Karhu-Kissat
  python3 scripts/export_birth_year_sankeys.py --birth-year 2009 --start-season 2020
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SCRIPT_DIR))

from leijonat_client import (  # noqa: E402
    _post,
    get_player_career,
    get_team_main_data,
    get_team_season_roster,
    roster_row_link_id,
    search_players,
)
from sankey_builder import SankeyData  # noqa: E402
from export_sankey_svgs import (  # noqa: E402
    DEFAULT_TEAM_URL_TEMPLATE,
    discover_teams,
    level_group,
    level_name,
    node_urls_for,
    render_svg,
    safe_component,
    season_label,
    should_export,
    slugify,
)

DEFAULT_OUT = ROOT / "exports" / "sankey_birth_year_2009"


def all_career_entries(career: dict) -> list[dict]:
    return career.get("Skater", []) + career.get("Goalkeeper", [])


def birth_year_from_value(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return int(match.group(0)) if match else None


def earliest_career_season(career: dict) -> str:
    seasons = [
        str(entry.get("SeasonNumber") or "")
        for entry in all_career_entries(career)
        if str(entry.get("SeasonNumber") or "").isdigit()
    ]
    return min(seasons, key=int) if seasons else ""


def primary_team_for_season(career: dict, season: str) -> dict:
    best: tuple[int, dict] | None = None
    for entry in all_career_entries(career):
        if str(entry.get("SeasonNumber") or "") != str(season):
            continue
        try:
            web_order = int(entry.get("LevelWebOrder", "9999") or "9999")
        except ValueError:
            web_order = 9999
        for team in entry.get("LevelTeams", []) or []:
            abbr = team.get("AssAbbrv") or team.get("TeamAbbrv") or ""
            if not abbr:
                continue
            meta = {
                "team": abbr,
                "level_id": str(entry.get("LevelID") or ""),
                "level_name": entry.get("LevelName") or "",
            }
            if best is None or web_order < best[0]:
                best = (web_order, meta)
    return best[1] if best else {}


def build_forward_sankey_with_out_of_sport(
    players: list[dict],
    careers: dict[str, dict],
    focal_team: str,
    focal_season: str,
    level_id: str,
    max_seasons_forward: int,
) -> SankeyData:
    start_year = int(focal_season)
    end_year = start_year + max_seasons_forward
    out_team = "Out of sport"
    out_level = "out-of-sport"

    player_paths: dict[str, dict] = {}
    node_players: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    node_meta_by_key: dict[tuple[str, str, str], dict] = {}

    for player in players:
        link_id = player.get("LinkID", "")
        career = careers.get(link_id, {})
        start_meta = primary_team_for_season(career, focal_season)
        if start_meta.get("team") != focal_team or str(start_meta.get("level_id") or "") != str(level_id):
            continue

        path: list[tuple[str, str, str]] = []
        for year in range(start_year, end_year + 1):
            season = str(year)
            meta = primary_team_for_season(career, season)
            if meta.get("team"):
                key = (season, meta["team"], str(meta.get("level_id") or ""))
                path.append(key)
                node_meta_by_key[key] = {
                    "season": season,
                    "season_label": season_label(season),
                    "team": meta["team"],
                    "level_id": str(meta.get("level_id") or ""),
                    "level_name": meta.get("level_name", ""),
                    "team_id": "",
                }
                continue

            # First missing next season means the player has flowed out of recorded hockey.
            if year > start_year:
                key = (season, out_team, out_level)
                path.append(key)
                node_meta_by_key[key] = {
                    "season": season,
                    "season_label": season_label(season),
                    "team": out_team,
                    "level_id": "",
                    "level_name": "Out of sport",
                    "team_id": "",
                }
            break

        if not path:
            continue
        pid = player.get("PersonID", link_id)
        player_name = f"{player.get('LastName', '')} {player.get('FirstName', '')}".strip()
        for key in path:
            node_players[key].append({"id": pid, "name": player_name})
        player_paths[pid] = {"name": player_name, "path": path}

    if not player_paths:
        return SankeyData(
            nodes=[], links=[], player_flows=[], focal_team=focal_team,
            mode="career_from_previous", confirmed_count=0, total_searched=len(players),
        )

    node_set = {key for item in player_paths.values() for key in item["path"]}
    sorted_nodes = sorted(node_set, key=lambda x: (int(x[0]) if x[0].isdigit() else 0, x[1] == out_team, x[1], x[2]))
    node_labels = [f"{season_label(season)} · {team}" for season, team, _ in sorted_nodes]
    node_to_idx = {key: i for i, key in enumerate(sorted_nodes)}
    node_meta = [
        {**node_meta_by_key.get(key, {}), "players": node_players.get(key, [])}
        for key in sorted_nodes
    ]

    seasons = sorted({season for season, _, _ in sorted_nodes}, key=lambda s: int(s) if s.isdigit() else 0)
    season_x = {
        season: 0.02 + 0.96 * i / max(len(seasons) - 1, 1)
        for i, season in enumerate(seasons)
    }
    season_nodes: dict[str, list[int]] = defaultdict(list)
    for i, (season, _, _) in enumerate(sorted_nodes):
        season_nodes[season].append(i)

    node_x = [0.0] * len(sorted_nodes)
    node_y = [0.5] * len(sorted_nodes)
    for season, indexes in season_nodes.items():
        normal = [idx for idx in indexes if sorted_nodes[idx][1] != out_team]
        out = [idx for idx in indexes if sorted_nodes[idx][1] == out_team]
        ordered = normal + out
        for rank, idx in enumerate(ordered):
            node_x[idx] = season_x.get(season, 0.5)
            node_y[idx] = 0.05 + 0.9 * rank / max(len(ordered) - 1, 1) if len(ordered) > 1 else 0.5

    edge_data: dict[tuple[int, int], list[str]] = defaultdict(list)
    for item in player_paths.values():
        path = item["path"]
        for left, right in zip(path, path[1:]):
            src_idx = node_to_idx.get(left)
            tgt_idx = node_to_idx.get(right)
            if src_idx is not None and tgt_idx is not None and src_idx != tgt_idx:
                edge_data[(src_idx, tgt_idx)].append(item["name"])

    links = []
    for (src, tgt), names in sorted(edge_data.items(), key=lambda x: -len(x[1])):
        links.append({
            "source": src,
            "target": tgt,
            "value": len(names),
            "label": f"{node_labels[src]} -> {node_labels[tgt]}: {len(names)} player(s)",
            "players": names,
        })

    return SankeyData(
        nodes=node_labels, links=links, player_flows=[],
        focal_team=focal_team, mode="career_from_previous",
        confirmed_count=len(player_paths), total_searched=len(players),
        node_x=node_x, node_y=node_y, node_meta=node_meta,
    )


async def get_player_basic_data(client: httpx.AsyncClient, link_id: str) -> dict:
    result = await _post(client, f"/modules/mod_playercardmain/helper/getplayerbasicdata6.php?lkq={link_id}", {})
    return result if isinstance(result, dict) else {}


async def careers_for_players(
    client: httpx.AsyncClient,
    players: dict[str, dict],
    concurrency: int,
    cache_file: Path,
) -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}

    careers: dict[str, dict] = {}
    sem = asyncio.Semaphore(max(1, concurrency))
    fetched = 0

    async def fetch(link_id: str) -> None:
        nonlocal fetched
        if link_id in cache:
            careers[link_id] = cache[link_id]
            return
        async with sem:
            try:
                career = await get_player_career(client, link_id)
            except Exception:
                career = {"Skater": [], "Goalkeeper": []}
            careers[link_id] = career
            cache[link_id] = career
            fetched += 1
            if fetched % 100 == 0:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                print(f"Fetched {fetched} new player careers...", flush=True)

    await asyncio.gather(*(fetch(link_id) for link_id in players))
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return careers


async def maybe_attach_birth_years(
    client: httpx.AsyncClient,
    players: dict[str, dict],
    concurrency: int,
    enabled: bool,
) -> None:
    if not enabled:
        return
    sem = asyncio.Semaphore(max(1, concurrency))

    async def fetch(player: dict) -> None:
        if player.get("BirthYear"):
            return
        async with sem:
            try:
                basic = await get_player_basic_data(client, player["LinkID"])
            except Exception:
                basic = {}
            player["BirthYear"] = birth_year_from_value(basic.get("Dob") or player.get("DateOfBirth", ""))

    await asyncio.gather(*(fetch(player) for player in players.values()))


async def collect_start_level_players(client: httpx.AsyncClient, args: argparse.Namespace) -> dict[str, dict]:
    """Collect players from the starting level, then career-filter to the cohort."""
    players: dict[str, dict] = {}
    start_levels = args.start_level or ["146"]
    for level_id in start_levels:
        page = 0
        while True:
            rows = await search_players(client, level=str(level_id), index=page)
            if not rows:
                break
            print(f"Level {level_id} page {page}: {len(rows)} players", flush=True)
            before = len(players)
            for row in rows:
                link_id = str(row.get("LinkID") or "").strip()
                if not link_id:
                    continue
                players.setdefault(link_id, {
                    "PersonID": link_id,
                    "LinkID": link_id,
                    "LastName": row.get("LastName", ""),
                    "FirstName": row.get("FirstName", ""),
                    "Association": row.get("Association", ""),
                    "Position": row.get("Position", ""),
                    "DateOfBirth": row.get("DateOfBirth", ""),
                })
            page += 1
            if args.max_pages and page >= args.max_pages:
                break
            # The endpoint returns fixed-size pages until the final partial page.
            if len(rows) < 20 or len(players) == before:
                break

    print(f"Collected {len(players)} unique players from starting levels {', '.join(start_levels)}.", flush=True)
    return players


async def collect_all_players(client: httpx.AsyncClient, args: argparse.Namespace) -> dict[str, dict]:
    """Collect broad player search results by initial; career filtering happens later."""
    players: dict[str, dict] = {}
    initials = args.initials or "ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ"
    for initial in initials:
        page = 0
        while True:
            result = await _post(
                client,
                "/modules/mod_searchplayersstats/helper/searchplayers.php",
                {
                    "schplrs": "",
                    "schtms": "",
                    "schass": "",
                    "initial": initial,
                    "level": "0",
                    "pid": 0,
                    "index": page,
                },
            )
            rows = result.get("players", []) if isinstance(result, dict) else []
            count = int(result.get("count") or 0) if isinstance(result, dict) else 0
            if not rows:
                break
            print(f"Initial {initial} page {page}: {len(rows)} / {count} players", flush=True)
            for row in rows:
                link_id = str(row.get("LinkID") or "").strip()
                if not link_id:
                    continue
                players.setdefault(link_id, {
                    "PersonID": link_id,
                    "LinkID": link_id,
                    "LastName": row.get("LastName", ""),
                    "FirstName": row.get("FirstName", ""),
                    "Association": row.get("Association", ""),
                    "Position": row.get("Position", ""),
                    "DateOfBirth": row.get("DateOfBirth", ""),
                })
            page += 1
            if args.max_pages_per_initial and page >= args.max_pages_per_initial:
                break
            if page * 20 >= count:
                break

    print(f"Collected {len(players)} unique players from all-player search.", flush=True)
    return players


async def collect_current_players(client: httpx.AsyncClient, args: argparse.Namespace) -> dict[str, dict]:
    rows = await discover_teams(client, args.team_query)
    print(f"Discovered {len(rows)} candidate current teams", flush=True)

    players: dict[str, dict] = {}
    scanned = 0
    skipped = 0
    filter_args = argparse.Namespace(
        level=args.level,
        group=None if args.all_current_levels else args.group,
    )
    for row in rows:
        team_id = str(row.get("TeamID", "")).strip()
        if not team_id:
            continue
        try:
            meta = await get_team_main_data(client, team_id)
            if not meta or not should_export(meta, filter_args):
                skipped += 1
                continue
            scanned += 1
            team_name = str(meta.get("TeamName") or team_id)
            team_abbr = str(meta.get("TeamAbbrv") or "").strip()
            association_id = str(meta.get("AssociationID") or "")
            roster = await get_team_season_roster(client, team_id, args.current_season, association_id)
            print(f"[{scanned}] {team_name}: {len(roster)} roster rows", flush=True)
            for row in roster[: args.max_players_per_team]:
                link_id = roster_row_link_id(row.get("PersonID", ""))
                if not link_id or link_id in players:
                    continue
                players[link_id] = {
                    "PersonID": link_id,
                    "LinkID": link_id,
                    "LastName": row.get("LastName", ""),
                    "FirstName": row.get("FirstName", ""),
                    "Association": team_abbr,
                    "Position": row.get("RoleName", ""),
                    "DateOfBirth": row.get("DateOfBirth", ""),
                    "CurrentTeamID": team_id,
                    "CurrentTeamName": team_name,
                }
            if args.limit_teams and scanned >= args.limit_teams:
                break
        except Exception as exc:
            skipped += 1
            print(f"skip {team_id}: {exc}", flush=True)

    print(f"Collected {len(players)} unique current players. Skipped {skipped} teams.", flush=True)
    return players


def cohort_groups(args: argparse.Namespace, players: dict[str, dict], careers: dict[str, dict]) -> dict[tuple[str, str, str], list[str]]:
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    explicit_births = 0
    inferred = 0
    start_levels = set(str(level) for level in (args.start_level or ["146"]))
    for link_id, player in players.items():
        career = careers.get(link_id, {})
        birth_year = player.get("BirthYear") or birth_year_from_value(player.get("DateOfBirth", ""))
        match_kind = ""
        if birth_year == args.birth_year:
            match_kind = "dob"
        elif earliest_career_season(career) == str(args.start_season):
            match_kind = "inferred"
        else:
            continue

        start_meta = primary_team_for_season(career, str(args.start_season))
        if not start_meta:
            continue
        if start_levels and str(start_meta.get("level_id") or "") not in start_levels:
            continue
        if match_kind == "dob":
            explicit_births += 1
        else:
            inferred += 1
        key = (
            start_meta.get("team", "Unknown"),
            start_meta.get("level_id", ""),
            start_meta.get("level_name", ""),
        )
        groups[key].append(link_id)

    print(
        f"Cohort matched {sum(len(v) for v in groups.values())} players "
        f"({explicit_births} by DOB, {inferred} by first season {season_label(str(args.start_season))}) "
        f"across {len(groups)} starting teams.",
        flush=True,
    )
    return groups


def output_file_for(args: argparse.Namespace, team: str, level_id: str, level_title: str) -> Path:
    return (
        args.output
        / f"born-{args.birth_year}"
        / safe_component(season_label(str(args.start_season)))
        / safe_component(level_group(level_id) if level_id else "Other")
        / safe_component(level_title or level_name(level_id) if level_id else "Unknown level")
        / safe_component(team)
        / "career-out.svg"
    )


async def export_all(args: argparse.Namespace) -> None:
    args.output.mkdir(parents=True, exist_ok=True)
    gitignore = args.output / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")

    async with httpx.AsyncClient() as client:
        if args.source == "all-players":
            players = await collect_all_players(client, args)
        elif args.source == "current-rosters":
            players = await collect_current_players(client, args)
        else:
            players = await collect_start_level_players(client, args)
        await maybe_attach_birth_years(client, players, args.birth_concurrency, not args.no_birth_lookup)
        careers = await careers_for_players(client, players, args.career_concurrency, args.cache_file)
        groups = cohort_groups(args, players, careers)

        exported = 0
        skipped = 0
        team_card_id_cache: dict[tuple[str, str], str] = {}
        for (team, level_id, level_title), link_ids in sorted(groups.items(), key=lambda item: item[0]):
            if len(link_ids) < args.min_players:
                skipped += 1
                continue
            out_file = output_file_for(args, team, level_id, level_title)
            if args.skip_existing and out_file.exists():
                exported += 1
                print(f"[{exported}] exists {out_file.relative_to(args.output)}", flush=True)
                continue

            cohort_players = [players[link_id] for link_id in link_ids]
            cohort_careers = {link_id: careers[link_id] for link_id in link_ids if link_id in careers}
            sankey = build_forward_sankey_with_out_of_sport(
                cohort_players,
                cohort_careers,
                team,
                str(args.start_season),
                level_id,
                args.max_seasons_forward,
            )
            if not sankey.nodes:
                skipped += 1
                continue

            node_urls = await node_urls_for(
                client,
                sankey,
                fallback_team_id="",
                fallback_team_abbr=team,
                url_template=args.team_url_template,
                cache=team_card_id_cache,
                concurrency=args.link_concurrency,
            )
            title = f"{team} {season_label(str(args.start_season))} -> 2009 cohort"
            subtitle = f"{len(link_ids)} players · first recorded on this level in {season_label(str(args.start_season))}"
            svg = render_svg(sankey, title, subtitle, args.size, node_urls)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(svg, encoding="utf-8")
            exported += 1
            print(f"[{exported}] {team} ({len(link_ids)} players) -> {out_file.relative_to(args.output)}", flush=True)
            if args.limit_diagrams and exported >= args.limit_diagrams:
                break

    print(f"Done. Exported {exported} birth-year SVGs to {args.output}. Skipped {skipped}.", flush=True)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export starting-team Sankeys for a birth-year cohort.")
    parser.add_argument("--birth-year", type=int, default=2009, help="Birth year to export")
    parser.add_argument("--start-season", default="2020", help="First stats season, e.g. 2020 for 2019-20")
    parser.add_argument("--start-level", action="append", default=["146"], help="Starting level id; default 146 (E2)")
    parser.add_argument("--source", choices=["all-players", "start-level", "current-rosters"], default="all-players")
    parser.add_argument("--current-season", default="2026", help="Current roster season, e.g. 2026 for 2025-26")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Output directory")
    parser.add_argument("--cache-file", type=Path, default=DEFAULT_OUT / "career-cache.json", help="Career JSON cache")
    parser.add_argument("--team-query", default="", help="Restrict current teams by team search")
    parser.add_argument("--level", action="append", help="Restrict current teams by level id; repeat for multiple")
    parser.add_argument("--group", default="U18", help="Restrict current teams by level group; default: U18")
    parser.add_argument("--all-current-levels", action="store_true", help="Scan all current levels instead of only --group")
    parser.add_argument("--limit-teams", type=int, default=0, help="Stop after N scanned current teams")
    parser.add_argument("--limit-diagrams", type=int, default=0, help="Stop after N exported diagrams")
    parser.add_argument("--max-pages", type=int, default=0, help="Max player-search pages per starting level")
    parser.add_argument("--initials", default="", help="Initials to scan for --source all-players, e.g. ABC")
    parser.add_argument("--max-pages-per-initial", type=int, default=0, help="Max all-player pages per initial")
    parser.add_argument("--min-players", type=int, default=2, help="Minimum cohort players required for a diagram")
    parser.add_argument("--max-players-per-team", type=int, default=300, help="Max roster rows per current team")
    parser.add_argument("--max-seasons-forward", type=int, default=10, help="Max seasons forward from start season")
    parser.add_argument("--career-concurrency", type=int, default=32, help="Concurrent player career lookups")
    parser.add_argument("--birth-concurrency", type=int, default=16, help="Concurrent player basic-data lookups")
    parser.add_argument("--link-concurrency", type=int, default=16, help="Concurrent team-card link lookups")
    parser.add_argument("--size", type=int, default=1200, help="Square SVG size in pixels")
    parser.add_argument("--skip-existing", action="store_true", help="Skip SVGs that already exist")
    parser.add_argument("--birth-lookup", dest="no_birth_lookup", action="store_false", help="Try player basic-data DOB lookup")
    parser.add_argument("--no-birth-lookup", dest="no_birth_lookup", action="store_true", help="Skip player basic-data DOB lookup")
    parser.set_defaults(no_birth_lookup=True)
    parser.add_argument(
        "--team-url-template",
        default=DEFAULT_TEAM_URL_TEMPLATE,
        help="Team link URL template; use {teamid} where the team id should be inserted",
    )
    return parser.parse_args(list(argv))


if __name__ == "__main__":
    asyncio.run(export_all(parse_args(sys.argv[1:])))
