#!/usr/bin/env python3
"""
Export national-team Sankey diagrams as TV-ready SVG and PNG files.

Defaults:
  - season 2026 (2025-26)
  - career paths into each national team
  - 1920x1080 HDTV dimensions
  - output folder exports/national_team_tv_2025_26

Examples:
  python3 scripts/export_national_team_tv.py --team-query FIN
  python3 scripts/export_national_team_tv.py --limit 5
  python3 scripts/export_national_team_tv.py --mode career-out --width 1920 --height 1080
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Iterable

import httpx

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from export_sankey_svgs import (  # noqa: E402
    DEFAULT_TEAM_URL_TEMPLATE,
    build_sankey,
    discover_teams,
    get_team_main_data,
    level_group,
    level_name,
    node_urls_for,
    output_file_for,
    render_png,
    render_svg,
    roster_context,
    safe_component,
    season_label,
)

DEFAULT_OUT = ROOT / "exports" / "national_team_tv_2025_26"
NATIONAL_LEVEL_IDS = {"127", "128", "130", "131", "132", "133", "134"}


def should_export_national(meta: dict, args: argparse.Namespace) -> bool:
    level_id = str(meta.get("LevelID") or "0")
    if level_id not in NATIONAL_LEVEL_IDS:
        return False
    if args.level and level_id not in set(args.level):
        return False
    if args.group and level_group(level_id).lower() != args.group.lower():
        return False
    return True


def output_files_for(args: argparse.Namespace, team_id: str, team_name: str, level_id: str) -> tuple[Path, Path]:
    base_svg = output_file_for(args, team_id, team_name, level_id)
    return base_svg.with_suffix(".svg"), base_svg.with_suffix(".png")


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
                if not meta or not should_export_national(meta, args):
                    skipped += 1
                    continue

                level_id = str(meta.get("LevelID") or "0")
                team_name_for_path = str(meta.get("TeamName") or team_id).strip()
                svg_file, png_file = output_files_for(args, team_id, team_name_for_path, level_id)
                if args.skip_existing and svg_file.exists() and png_file.exists():
                    exported += 1
                    print(f"[{exported}] exists {svg_file.relative_to(args.output)} + PNG", flush=True)
                    if args.limit and exported >= args.limit:
                        break
                    continue

                print(f"Exporting {team_name_for_path} ({args.width}x{args.height})...", flush=True)
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
                subtitle = f"{level_name(level_id)} · {sankey.confirmed_count} players · {args.mode} · HDTV {args.width}x{args.height}"
                svg = render_svg(
                    sankey,
                    title,
                    subtitle,
                    node_urls=node_urls,
                    width=args.width,
                    height=args.height,
                )
                png = render_png(sankey, title, subtitle, width=args.width, height=args.height)

                svg_file, png_file = output_files_for(args, team_id, team_name, level_id)
                svg_file.parent.mkdir(parents=True, exist_ok=True)
                svg_file.write_text(svg, encoding="utf-8")
                png_file.write_bytes(png)

                exported += 1
                rel = svg_file.relative_to(args.output)
                print(f"[{exported}] {team_name} -> {rel} + {rel.with_suffix('.png')}", flush=True)
                if args.limit and exported >= args.limit:
                    break
            except Exception as exc:
                skipped += 1
                print(f"skip {team_id}: {exc}", flush=True)

    print(f"Done. Exported {exported} TV-ready national diagrams to {args.output}. Skipped {skipped}.", flush=True)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export national-team Sankeys to HDTV-ready SVG and PNG.")
    parser.add_argument("--season", default="2026", help="Season end year, e.g. 2026 for 2025-26")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Output directory")
    parser.add_argument("--mode", choices=["career-in", "career-out", "to-current", "from-previous"], default="career-in")
    parser.add_argument("--level", action="append", help="Export only this national level id; repeat for multiple")
    parser.add_argument("--group", help="Export only one national level group, e.g. U18, U20, Women")
    parser.add_argument("--team-query", default="", help="Export only teams returned by this team search")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N exported teams")
    parser.add_argument("--max-players", type=int, default=300, help="Max roster players per team")
    parser.add_argument("--career-concurrency", type=int, default=32, help="Concurrent player career lookups per team")
    parser.add_argument("--link-concurrency", type=int, default=16, help="Concurrent team-card link lookups")
    parser.add_argument("--width", type=int, default=1920, help="Output image width")
    parser.add_argument("--height", type=int, default=1080, help="Output image height")
    parser.add_argument("--skip-existing", action="store_true", help="Skip when both SVG and PNG already exist")
    parser.add_argument(
        "--team-url-template",
        default=DEFAULT_TEAM_URL_TEMPLATE,
        help="Team link URL template; use {teamid} where the team id should be inserted",
    )
    return parser.parse_args(list(argv))


if __name__ == "__main__":
    asyncio.run(export_all(parse_args(sys.argv[1:])))
