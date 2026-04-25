"""
Sankey diagram builders for Finnish hockey player flows.

Three modes:
  to_current     – PreviousTeam → FocalTeam  (one step back)
  from_previous  – FocalTeam → NextTeam      (one step forward)
  career_paths   – full year-by-year career Sankey with season columns
"""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


PRACTICE_LEVEL_IDS = {"150"}   # Harjoitusottelut


@dataclass
class PlayerFlow:
    person_id: str
    first_name: str
    last_name: str
    source_team: str
    source_season: str
    target_team: str
    target_season: str
    position: str = ""


@dataclass
class SankeyData:
    nodes: list[str]
    links: list[dict]
    player_flows: list[PlayerFlow]
    focal_team: str
    mode: str
    confirmed_count: int
    total_searched: int
    node_x: list[float] = field(default_factory=list)
    node_y: list[float] = field(default_factory=list)
    node_meta: list[dict] = field(default_factory=list)
    focal_team_display: Optional[str] = None  # full official name when resolved via team_id
    resolved_team_id: Optional[str] = None
    resolved_level_id: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _all_entries(career: dict) -> list[dict]:
    return career.get("Skater", []) + career.get("Goalkeeper", [])


def _seasons_map(career: dict) -> dict[str, list[dict]]:
    """Return {season_number: [entries]} excluding practice games."""
    seasons: dict[str, list[dict]] = defaultdict(list)
    for e in _all_entries(career):
        if e.get("LevelID") in PRACTICE_LEVEL_IDS:
            continue
        s = e.get("SeasonNumber", "")
        if s:
            seasons[s].append(e)
    return seasons


def _primary_team_per_season(career: dict) -> dict[str, dict]:
    """
    For each season in the career, pick the team the player spent time with
    at the most competitive level (lowest LevelWebOrder).
    Returns {season_number: {team, level_id, level_name, team_id}}.
    """
    result: dict[str, tuple[int, dict]] = {}  # {season: (best_web_order, metadata)}
    for e in _all_entries(career):
        if e.get("LevelID") in PRACTICE_LEVEL_IDS:
            continue
        s = e.get("SeasonNumber", "")
        if not s:
            continue
        try:
            web_order = int(e.get("LevelWebOrder", "9999") or "9999")
        except ValueError:
            web_order = 9999
        for t in e.get("LevelTeams", []):
            abbr = t.get("AssAbbrv") or t.get("TeamAbbrv") or ""
            if not abbr:
                continue
            if s not in result or web_order < result[s][0]:
                result[s] = (web_order, {
                    "team": abbr,
                    "level_id": str(e.get("LevelID", "") or ""),
                    "level_name": e.get("LevelName", "") or "",
                    "team_id": str(t.get("TeamID", "") or ""),
                })
    return {s: meta for s, (_, meta) in result.items()}


def _season_label(season_number: str) -> str:
    """'2026' → '2025-26'"""
    try:
        y = int(season_number)
        return f"{y - 1}-{str(y)[2:]}"
    except ValueError:
        return season_number


def _confirm_player_at(career: dict, team: str, level_id: str, season: str) -> bool:
    """True if career has an entry for team at level in season."""
    for e in _all_entries(career):
        if e.get("SeasonNumber") != season:
            continue
        if level_id != "0" and e.get("LevelID") != level_id:
            continue
        for t in e.get("LevelTeams", []):
            abbr = t.get("AssAbbrv") or t.get("TeamAbbrv") or ""
            if abbr == team:
                return True
    return False


def _abbr_level_pairs_for_season(seasons: dict[str, list], season_key: str) -> set[tuple[str, str]]:
    """(AssociationAbbrv, LevelID) pairs for that season — same club can appear on several levels."""
    out: set[tuple[str, str]] = set()
    for e in seasons.get(season_key, []):
        lid = str(e.get("LevelID", "") or "")
        for t in e.get("LevelTeams", []):
            abbr = t.get("AssAbbrv") or t.get("TeamAbbrv") or ""
            if abbr:
                out.add((abbr, lid))
    return out


def _pick_other_abbr_for_season(
    pairs: set[tuple[str, str]],
    focal_team: str,
    focal_level_id: str,
) -> Optional[str]:
    """
    Pick a destination/source abbreviation that is not the same (club, level) line as the focal row.
    When focal_level_id is \"0\", only the club abbreviation is compared (legacy behaviour).
    """
    fl = str(focal_level_id or "0")
    if fl != "0":
        candidates = [abbr for (abbr, lid) in pairs if (abbr, lid) != (focal_team, fl)]
    else:
        candidates = [abbr for (abbr, _) in pairs if abbr != focal_team]
    if not candidates:
        return None
    return sorted(set(candidates))[0]


def _find_previous_team(
    career: dict, focal_team: str, focal_season: str, focal_level_id: str = "0",
) -> tuple[str, str]:
    seasons = _seasons_map(career)
    sorted_s = sorted(seasons.keys(), key=lambda s: int(s) if s.isdigit() else 0, reverse=True)
    focal_idx = next((i for i, s in enumerate(sorted_s) if s == focal_season), None)
    start = (focal_idx + 1) if focal_idx is not None else 0
    fl = str(focal_level_id or "0")

    for i in range(start, len(sorted_s)):
        s = sorted_s[i]
        pairs = _abbr_level_pairs_for_season(seasons, s)
        abbr = _pick_other_abbr_for_season(pairs, focal_team, fl)
        if abbr is not None:
            return abbr, s
        # If level-specific scan found nothing (only focal line at that level), fall back to abbr-only.
        if fl != "0":
            abbr = _pick_other_abbr_for_season(pairs, focal_team, "0")
            if abbr is not None:
                return abbr, s
    return "Unknown / first team", ""


def _find_next_team(
    career: dict, focal_team: str, focal_season: str, focal_level_id: str = "0",
) -> tuple[str, str]:
    seasons = _seasons_map(career)
    sorted_s = sorted(seasons.keys(), key=lambda s: int(s) if s.isdigit() else 0)
    focal_idx = next((i for i, s in enumerate(sorted_s) if s == focal_season), None)
    start = (focal_idx + 1) if focal_idx is not None else len(sorted_s)
    fl = str(focal_level_id or "0")

    for i in range(start, len(sorted_s)):
        s = sorted_s[i]
        pairs = _abbr_level_pairs_for_season(seasons, s)
        abbr = _pick_other_abbr_for_season(pairs, focal_team, fl)
        if abbr is not None:
            return abbr, s
        if fl != "0":
            abbr = _pick_other_abbr_for_season(pairs, focal_team, "0")
            if abbr is not None:
                return abbr, s
    return "Stayed / left game", ""


def _confirm_or_assoc(player: dict, career: dict, team: str, level_id: str, season: str) -> bool:
    if _confirm_player_at(career, team, level_id, season):
        return True
    # Leijonat search returns many club-registered players who are not on this level in
    # the focal season. Association-only fallback is only safe when no level filter.
    if str(level_id or "0") != "0":
        return False
    return player.get("Association") == team


def _roster_cohort_ok(link_id: str, cohort_link_ids: Optional[frozenset[str]]) -> bool:
    if cohort_link_ids is None:
        return True
    return link_id in cohort_link_ids


# ── Simple one-step Sankeys ───────────────────────────────────────────────────

def build_to_current_sankey(
    players: list[dict], careers: dict[str, dict],
    focal_team: str, season: str, level_id: str = "0",
    player_weights: dict[str, int] | None = None,
    cohort_link_ids: Optional[frozenset[str]] = None,
) -> SankeyData:
    flows: list[PlayerFlow] = []
    confirmed = 0
    for p in players:
        link_id = p.get("LinkID", "")
        career = careers.get(link_id, {})
        if not _roster_cohort_ok(link_id, cohort_link_ids):
            continue
        if cohort_link_ids is None and not _confirm_or_assoc(p, career, focal_team, level_id, season):
            continue
        confirmed += 1
        prev_team, prev_s = _find_previous_team(career, focal_team, season, level_id)
        flows.append(PlayerFlow(
            person_id=p.get("PersonID", ""), first_name=p.get("FirstName", ""),
            last_name=p.get("LastName", ""), source_team=prev_team, source_season=prev_s,
            target_team=focal_team, target_season=season, position=p.get("Position", ""),
        ))
    return _simple_flows_to_sankey(
        flows, focal_team, "to_current", confirmed, len(players), player_weights
    )


def build_from_previous_sankey(
    players: list[dict], careers: dict[str, dict],
    focal_team: str, season: str, level_id: str = "0",
    player_weights: dict[str, int] | None = None,
    cohort_link_ids: Optional[frozenset[str]] = None,
) -> SankeyData:
    flows: list[PlayerFlow] = []
    confirmed = 0
    for p in players:
        link_id = p.get("LinkID", "")
        career = careers.get(link_id, {})
        if not _roster_cohort_ok(link_id, cohort_link_ids):
            continue
        if cohort_link_ids is None and not _confirm_or_assoc(p, career, focal_team, level_id, season):
            continue
        confirmed += 1
        next_team, next_s = _find_next_team(career, focal_team, season, level_id)
        flows.append(PlayerFlow(
            person_id=p.get("PersonID", ""), first_name=p.get("FirstName", ""),
            last_name=p.get("LastName", ""), source_team=focal_team, source_season=season,
            target_team=next_team, target_season=next_s, position=p.get("Position", ""),
        ))
    return _simple_flows_to_sankey(
        flows, focal_team, "from_previous", confirmed, len(players), player_weights
    )


def _simple_flows_to_sankey(
    flows: list[PlayerFlow], focal_team: str, mode: str,
    confirmed_count: int, total_searched: int,
    player_weights: dict[str, int] | None = None,
) -> SankeyData:
    edge: dict[tuple[str, str], list[PlayerFlow]] = defaultdict(list)
    for f in flows:
        edge[(f.source_team, f.target_team)].append(f)

    all_teams = {t for pair in edge for t in pair}
    other = sorted(all_teams - {focal_team})
    nodes = other + [focal_team] if mode == "to_current" else [focal_team] + other
    idx = {n: i for i, n in enumerate(nodes)}

    use_games = bool(player_weights)

    links = []
    for (src, tgt), plist in sorted(edge.items(), key=lambda x: -len(x[1])):
        n_players = len(plist)

        if use_games:
            total_games = sum(max(1, player_weights.get(p.person_id, 0)) for p in plist)
            value = total_games
            label = f"{src} → {tgt}: {total_games} gp ({n_players} player{'s' if n_players != 1 else ''})"
        else:
            value = n_players
            label = f"{src} → {tgt}: {n_players} player{'s' if n_players != 1 else ''}"

        player_lines = []
        for p in plist:
            name = f"{p.last_name} {p.first_name}".strip()
            pos = f" ({p.position})" if p.position else ""
            if use_games:
                gp = player_weights.get(p.person_id, 0) if player_weights else 0
                player_lines.append(f"{name}{pos} — {gp} gp")
            else:
                player_lines.append(f"{name}{pos}")

        links.append({
            "source": idx[src], "target": idx[tgt],
            "value": max(1, value),   # Plotly requires value > 0
            "label": label,
            "players": player_lines,
        })

    return SankeyData(
        nodes=nodes, links=links, player_flows=flows,
        focal_team=focal_team, mode=mode,
        confirmed_count=confirmed_count, total_searched=total_searched,
    )


# ── Career-path multi-step Sankey ─────────────────────────────────────────────

def build_career_paths_sankey(
    players: list[dict],
    careers: dict[str, dict],
    focal_team: str,
    focal_season: str,
    level_id: str = "0",
    direction: str = "to_current",   # "to_current" or "from_previous"
    max_seasons_back: int = 10,
    cohort_link_ids: Optional[frozenset[str]] = None,
) -> SankeyData:
    """
    Multi-step Sankey: each column = one season, each node = a team in that season.
    Tracks where players went (or came from) over their full career.

    direction="to_current"    → show career UP TO focal_season (past → present)
    direction="from_previous" → show career FROM focal_season onward (present → future)
    """
    # player_id → {name, path: [(season_num_str, team_abbr, level_id)]}
    player_data: dict[str, dict] = {}
    node_metadata_by_key: dict[tuple[str, str, str], dict] = {}
    confirmed = 0

    for p in players:
        link_id = p.get("LinkID", "")
        career = careers.get(link_id, {})
        if not _roster_cohort_ok(link_id, cohort_link_ids):
            continue
        if cohort_link_ids is None and not _confirm_or_assoc(p, career, focal_team, level_id, focal_season):
            continue
        confirmed += 1

        season_team = _primary_team_per_season(career)

        try:
            focal_yr = int(focal_season)
        except ValueError:
            focal_yr = 9999

        if direction == "to_current":
            limit_s = [s for s in season_team if s.isdigit() and int(s) <= focal_yr]
            # Also cap at max_seasons_back
            if limit_s:
                min_show = focal_yr - max_seasons_back
                limit_s = [s for s in limit_s if int(s) >= min_show]
        else:
            limit_s = [s for s in season_team if s.isdigit() and int(s) >= focal_yr]

        path = sorted(
            [
                (s, season_team[s]["team"], season_team[s].get("level_id", ""))
                for s in limit_s
                if season_team.get(s, {}).get("team")
            ],
            key=lambda x: int(x[0]),
        )

        if path:
            for s, team_abbr, level_id in path:
                meta = season_team.get(s, {})
                node_metadata_by_key[(s, team_abbr, level_id)] = {
                    "season": s,
                    "season_label": _season_label(s),
                    "team": team_abbr,
                    "level_id": level_id,
                    "level_name": meta.get("level_name", ""),
                    "team_id": meta.get("team_id", ""),
                }
            pid = p.get("PersonID", link_id)
            player_data[pid] = {
                "name": f"{p.get('LastName', '')} {p.get('FirstName', '')}".strip(),
                "path": path,
            }

    if not player_data:
        return SankeyData(
            nodes=[], links=[], player_flows=[], focal_team=focal_team,
            mode=f"career_{direction}", confirmed_count=0, total_searched=len(players),
        )

    # ── Build nodes ──
    node_set: set[tuple[str, str, str]] = set()
    for pd in player_data.values():
        for (s, t, level_id) in pd["path"]:
            node_set.add((s, t, level_id))

    all_seasons_sorted = sorted(
        {s for s, _, _ in node_set},
        key=lambda s: int(s) if s.isdigit() else 0,
    )

    # Sort nodes by (season, team, level)
    sorted_nodes = sorted(node_set, key=lambda x: (int(x[0]) if x[0].isdigit() else 0, x[1], x[2]))
    node_labels = [f"{_season_label(s)} · {t}" for s, t, _ in sorted_nodes]
    node_to_idx = {(s, t, level_id): i for i, (s, t, level_id) in enumerate(sorted_nodes)}
    node_meta = [node_metadata_by_key.get(key, {}) for key in sorted_nodes]

    # ── X positions: one column per season ──
    n_seasons = len(all_seasons_sorted)
    if n_seasons > 1:
        season_x = {
            s: 0.02 + 0.96 * i / (n_seasons - 1)
            for i, s in enumerate(all_seasons_sorted)
        }
    else:
        season_x = {all_seasons_sorted[0]: 0.5} if all_seasons_sorted else {}

    # ── Y positions: distribute nodes within each season column ──
    season_nodes: dict[str, list[int]] = defaultdict(list)
    for i, (s, t, level_id) in enumerate(sorted_nodes):
        season_nodes[s].append(i)

    node_x: list[float] = [0.0] * len(sorted_nodes)
    node_y: list[float] = [0.5] * len(sorted_nodes)

    for s, idxs in season_nodes.items():
        x = season_x.get(s, 0.5)
        n = len(idxs)
        for rank, idx in enumerate(idxs):
            node_x[idx] = x
            node_y[idx] = 0.05 + 0.9 * rank / max(n - 1, 1) if n > 1 else 0.5

    # ── Build links ──
    edge_data: dict[tuple[int, int], list[str]] = defaultdict(list)

    for pd in player_data.values():
        path = pd["path"]
        for i in range(len(path) - 1):
            s0, t0, level0 = path[i]
            s1, t1, level1 = path[i + 1]
            # Only link if seasons are consecutive (gap ≤ 1 year)
            try:
                if int(s1) - int(s0) > 2:
                    continue
            except ValueError:
                continue
            src_idx = node_to_idx.get((s0, t0, level0))
            tgt_idx = node_to_idx.get((s1, t1, level1))
            if src_idx is not None and tgt_idx is not None and src_idx != tgt_idx:
                edge_data[(src_idx, tgt_idx)].append(pd["name"])

    links = []
    for (src, tgt), names in sorted(edge_data.items(), key=lambda x: -len(x[1])):
        links.append({
            "source": src, "target": tgt, "value": len(names),
            "label": f"{node_labels[src]} → {node_labels[tgt]}: {len(names)} player(s)",
            "players": names,
        })

    return SankeyData(
        nodes=node_labels, links=links, player_flows=[],
        focal_team=focal_team, mode=f"career_{direction}",
        confirmed_count=confirmed, total_searched=len(players),
        node_x=node_x, node_y=node_y, node_meta=node_meta,
    )
