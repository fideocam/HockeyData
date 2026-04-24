"""
Youth player development pathway analysis.

For every (player, focal_season, org) data point where the player appeared at
the focal level we check what level they played at in the NEXT season and
categorise it into four progression tiers based on LevelWebOrder:

  professional  — WebOrder ≤ 30  (SM-liiga, Mestis, U20 SM/Mestis, elite)
  competitive   — WebOrder 31–60 (U18 SM/Mestis, U16 SM, high junior)
  active        — WebOrder 61–110 (lower junior/amateur divisions)
  recreational  — WebOrder > 110 (recreational leagues, camps, etc.)
  no_record     — no career entry at all in the next season

The "no_record" category is measured from career data transitions, so it
captures players with genuine gaps even if they are currently still registered.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


# ── Level-tier thresholds ────────────────────────────────────────────────────

def _tier(web_order: float) -> str:
    if web_order <= 30:
        return "professional"
    if web_order <= 60:
        return "competitive"
    if web_order <= 110:
        return "active"
    return "recreational"


@dataclass
class OrgProgression:
    org: str
    total: int                  # player-season data points
    professional: int
    competitive: int
    active: int
    recreational: int
    no_record: int
    professional_names: list[str] = field(default_factory=list)
    competitive_names: list[str] = field(default_factory=list)
    active_names: list[str] = field(default_factory=list)
    recreational_names: list[str] = field(default_factory=list)
    no_record_names: list[str] = field(default_factory=list)

    @property
    def continued_rate(self) -> float:
        continued = self.total - self.no_record
        return continued / self.total * 100 if self.total else 0.0

    @property
    def high_level_rate(self) -> float:
        return (self.professional + self.competitive) / self.total * 100 if self.total else 0.0

    @property
    def professional_rate(self) -> float:
        return self.professional / self.total * 100 if self.total else 0.0

    @property
    def competitive_rate(self) -> float:
        return self.competitive / self.total * 100 if self.total else 0.0

    @property
    def active_rate(self) -> float:
        return self.active / self.total * 100 if self.total else 0.0

    @property
    def recreational_rate(self) -> float:
        return self.recreational / self.total * 100 if self.total else 0.0

    @property
    def no_record_rate(self) -> float:
        return self.no_record / self.total * 100 if self.total else 0.0


def analyze_progression(
    players: list[dict],
    careers: dict[str, dict],       # link_id → career dict
    level_id: str,
    season_from: str,               # e.g. "2021"
    season_to: str,                 # e.g. "2024" — we check season_to → season_to+1
    min_data_points: int = 5,
) -> list[OrgProgression]:
    """
    For every (player, season, org) in [season_from, season_to] at *level_id*,
    determine which level tier the player played at in season+1.
    Returns a list sorted by continued_rate (descending).
    """
    from_int = int(season_from)
    to_int = int(season_to)

    org_acc: dict[str, Any] = defaultdict(
        lambda: {
            "total": 0,
            "professional": 0, "competitive": 0,
            "active": 0, "recreational": 0, "no_record": 0,
            "professional_names": [], "competitive_names": [],
            "active_names": [], "recreational_names": [], "no_record_names": [],
        }
    )

    for p in players:
        link_id = p.get("LinkID", "")
        career = careers.get(link_id, {})
        full_name = f"{p.get('LastName', '')} {p.get('FirstName', '')}".strip()

        seen: set[tuple[str, str]] = set()   # (season, org) dedup
        for role in ("Skater", "Goalkeeper"):
            for entry in career.get(role, []):
                s = entry.get("SeasonNumber", "")
                if not s:
                    continue
                try:
                    si = int(s)
                except ValueError:
                    continue
                if not (from_int <= si <= to_int):
                    continue
                if level_id != "0" and entry.get("LevelID") != level_id:
                    continue
                teams = entry.get("LevelTeams") or []
                org = teams[0].get("AssAbbrv") if teams else None
                if not org:
                    continue

                key = (s, org)
                if key in seen:
                    continue
                seen.add(key)

                next_s = str(si + 1)
                tier = _next_season_tier(career, next_s)
                label = f"{full_name} ({s[-2:]}→{next_s[-2:]})"
                acc = org_acc[org]
                acc["total"] += 1
                acc[tier] += 1
                acc[f"{tier}_names"].append(label)

    results: list[OrgProgression] = []
    for org, acc in org_acc.items():
        if acc["total"] < min_data_points:
            continue
        results.append(OrgProgression(
            org=org,
            total=int(acc["total"]),
            professional=int(acc["professional"]),
            competitive=int(acc["competitive"]),
            active=int(acc["active"]),
            recreational=int(acc["recreational"]),
            no_record=int(acc["no_record"]),
            professional_names=list(acc["professional_names"]),
            competitive_names=list(acc["competitive_names"]),
            active_names=list(acc["active_names"]),
            recreational_names=list(acc["recreational_names"]),
            no_record_names=list(acc["no_record_names"]),
        ))

    results.sort(key=lambda r: -(r.professional + r.competitive))
    return results


# ── helpers ───────────────────────────────────────────────────────────────────

def _next_season_tier(career: dict, next_season: str) -> str:
    """
    Find the most competitive (lowest WebOrder) level the player played at
    in next_season and return its tier.  Returns "no_record" if nothing found.
    """
    best_order = float("inf")

    for role in ("Skater", "Goalkeeper"):
        for entry in career.get(role, []):
            if entry.get("SeasonNumber") != next_season:
                continue
            order = _web_order(entry)
            if order < best_order:
                best_order = order

    if best_order == float("inf"):
        return "no_record"
    return _tier(best_order)


def _web_order(entry: dict) -> float:
    try:
        v = float(entry.get("LevelWebOrder", 999))
        # WebOrder == 0 means a generic/unranked entry; treat as very low priority
        return v if v > 0 else 999.0
    except (TypeError, ValueError):
        return 999.0
