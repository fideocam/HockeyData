"""
Client for the leijonat.fi API.

Key endpoints (POST, public, no auth):
  Search players:   /modules/mod_searchplayersstats/helper/searchplayers.php
  Player career:    /modules/mod_playercardmain/helper/getseasonstatsdata.php
  Search teams:     /modules/mod_searchteams/helper/search.php  (GET params)
"""

import random
import re
from typing import Any, Optional
from urllib.parse import quote

import httpx

BASE_URL = "https://www.leijonat.fi"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    # Joukkuekortti APIs behave more reliably when the referer matches the team-card area.
    "Referer": "https://www.leijonat.fi/index.php/joukkueet",
}

_TEAM_ID_IN_URL = re.compile(
    r"(?:[?#&]|%3[Ff]|%26)(?:teamid|TeamID)=(\d{4,24})(?:\b|&|#|$)",
    re.IGNORECASE,
)


def extract_team_id(raw: str) -> Optional[str]:
    """
    Parse a joukkuekortti team id from pasted text: full URL, query string, or bare digits.
    Handles HTML-escaped &amp; in copied links.
    """
    if not raw:
        return None
    s = raw.strip().replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    s = s.replace("&amp;", "&").replace("&AMP;", "&")
    m = _TEAM_ID_IN_URL.search(s)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{4,24}", s):
        return s
    return None


def _safe_json(resp: httpx.Response) -> Any:
    text = resp.text.strip()
    if not text or text in ("{}", "[]", "null"):
        return None
    try:
        return resp.json()
    except ValueError:
        return None


async def _post(client: httpx.AsyncClient, path: str, data: dict) -> Any:
    resp = await client.post(f"{BASE_URL}{path}", data=data, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return _safe_json(resp)


async def _get_json(client: httpx.AsyncClient, path_with_query: str) -> Any:
    """GET helper for endpoints that also accept query parameters (fallback if POST is stripped)."""
    resp = await client.get(f"{BASE_URL}{path_with_query}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return _safe_json(resp)


async def search_players(
    client: httpx.AsyncClient,
    team_name: str = "",
    player_name: str = "",
    level: str = "0",
    index: int = 0,
) -> list[dict]:
    result = await _post(
        client,
        "/modules/mod_searchplayersstats/helper/searchplayers.php",
        {
            "schplrs": player_name,
            "schtms": team_name,
            "schass": "",
            "initial": "",
            "level": level,
            "pid": 0,
            "index": index,
        },
    )
    if result and isinstance(result, dict):
        return result.get("players", [])
    return []


async def get_player_career(client: httpx.AsyncClient, link_id: str) -> dict:
    """
    Full career history. Response keys: 'Skater', 'Goalkeeper'.
    Each entry: {SeasonName, SeasonNumber, LevelWebOrder, LevelName, LevelID,
                 LevelTeams: [{TeamID, AssAbbrv, TeamAbbrv}]}
    """
    result = await _post(
        client,
        "/modules/mod_playercardmain/helper/getseasonstatsdata.php",
        {"lkq": link_id, "filters[All]": 1},
    )
    if result and isinstance(result, dict):
        return result
    return {"Skater": [], "Goalkeeper": []}


async def get_player_season_stats(
    client: httpx.AsyncClient, link_id: str, season: str
) -> dict:
    """
    Returns games played for a player in a given season.
    season = year the season ends, e.g. '2026' for 2025-26.
    Response keys: skater_games (int), goalie_games (int).
    Falls back to 0 when no data.
    """
    result = await _post(
        client,
        f"/modules/mod_playercardallstats/helper/getplayerallstats5.php"
        f"?lkq={link_id}&age=0&season={season}",
        {},
    )

    def _int(val) -> int:
        try:
            return int(val or 0)
        except (TypeError, ValueError):
            return 0

    if result and isinstance(result, dict):
        return {
            "skater_games": _int(result.get("SkaterGames")),
            "goalie_games": _int(result.get("GoaliePlayedGames")),
        }
    # Older seasons return a list; skip for now
    return {"skater_games": 0, "goalie_games": 0}


def _team_main_payload_ok(result: Any) -> bool:
    if not result or not isinstance(result, dict):
        return False
    # Some responses omit TeamName but still include abbreviation / level (accept those).
    return bool(
        result.get("TeamName")
        or result.get("TeamAbbrv")
        or (result.get("LevelID") and result.get("AssociationID"))
    )


async def get_team_main_data(client: httpx.AsyncClient, team_id: str) -> Optional[dict]:
    """
    Joukkuekortti main data for a numeric team id.
    Returns keys like TeamName, TeamAbbrv, LevelID, AssociationID, StatGroupName, …
    Tries POST first, then GET (some proxies strip POST bodies).
    """
    tid = extract_team_id(str(team_id)) or (str(team_id).strip() if str(team_id).strip().isdigit() else "")
    if not tid:
        return None
    path = "/modules/mod_teamcardmain/helper/getteammaindata.php"
    post_r = await _post(client, path, {"teamid": tid})
    if _team_main_payload_ok(post_r):
        return post_r
    get_r = await _get_json(client, f"{path}?teamid={quote(tid, safe='')}")
    if _team_main_payload_ok(get_r):
        return get_r
    return None


def roster_row_link_id(person_field: str) -> str:
    """Roster PersonID values look like '104744…&zwf=…' — lkq is the part before &."""
    if not person_field:
        return ""
    return str(person_field).split("&", 1)[0].strip()


async def get_team_season_roster(
    client: httpx.AsyncClient,
    team_id: str,
    season_number: str,
    association_id: str,
) -> list[dict]:
    """
    Official roster for a joukkuekortti team + season.
    Each row has PersonID (with &zwf suffix), LastName, FirstName, RoleName, …
    """
    result = await _post(
        client,
        "/modules/mod_teamcardseasonstats/helper/getteamseasondata3.php",
        {
            "teamid": str(team_id),
            "seasonnumber": str(season_number),
            "associationid": str(association_id),
        },
    )
    if result and isinstance(result, dict):
        return result.get("Players") or []
    return []


# Short text search (e.g. "evu") often returns only one club-branded team; leijonat also
# supports browse-by-initial, which lists many teams per letter — filter by association.
_ASSOC_CODE_RE = re.compile(r"^[A-Za-zÅÄÖåäö]{2,4}$")


def _team_search_variants(query: str) -> list[str]:
    """
    Leijonat team search is literal about hyphens and suffixes. Generate a small
    set of common alternate forms without turning search into a broad fuzzy match.
    """
    variants: list[str] = []

    def add(value: str) -> None:
        v = re.sub(r"\s+", " ", value).strip()
        if v and v not in variants:
            variants.append(v)

    add(query)

    without_akatemia = re.sub(r"\bakatemia\b", "", query, flags=re.IGNORECASE)
    add(without_akatemia)

    base = re.sub(r"\s+", " ", without_akatemia).strip()
    parts = base.split(" ")
    if len(parts) >= 2:
        # "Karhu Kissat" is not returned by the source, but "Karhu-Kissat" is.
        add(f"{parts[0]}-{parts[1]}")
        add(" ".join([f"{parts[0]}-{parts[1]}", *parts[2:]]))
        # "K Kissat" is a natural way to type the displayed "K-Kissat" abbreviation.
        if len(parts[0]) == 1:
            add(parts[1])

    # Users often type the displayed abbreviation ("K-Kissat"), while the source
    # only finds this club with the full name or the suffix ("Kissat").
    if "-" in query:
        add(query.split("-")[-1])

    return variants


def _is_team_search_row(item: Any) -> bool:
    """Drop non-team JSON (e.g. stray player objects) from search responses."""
    if not isinstance(item, dict):
        return False
    if item.get("PersonID"):
        return False
    tid = item.get("TeamID")
    tname = item.get("TeamName")
    if tid is None or tname is None:
        return False
    if not str(tid).strip() or not str(tname).strip():
        return False
    return True


async def _search_teams_request(
    client: httpx.AsyncClient, schtms: str, initial: str = ""
) -> list[dict]:
    encoded_s = quote(schtms or "", safe="")
    enc_initial = quote(initial or "", safe="")
    path = (
        f"/modules/mod_searchteams/helper/search.php?"
        f"schtms={encoded_s}&initial={enc_initial}&rdm={random.random()}"
    )
    result = await _post(client, path, {})
    if result and isinstance(result, list):
        return [x for x in result if _is_team_search_row(x)]
    return []


async def search_teams(client: httpx.AsyncClient, name: str) -> list[dict]:
    """
    Returns [{TeamID, TeamName, AssociationAbbrv}].
    Search params go in the URL (the site uses GET query + POST body=empty).
    Name is properly URL-encoded to handle Finnish characters (ä, ö, etc.).

    For 2–4 letter association-style queries (e.g. "evu", "TPS"), merges in teams from
    the same association found via the site's initial-letter browse, which text search
    alone often omits (e.g. EVU U18 teams not returned for schtms=evu).
    """
    q = (name or "").strip()
    if not q:
        return []

    merged: dict[str, dict] = {}
    for candidate in _team_search_variants(q):
        rows = await _search_teams_request(client, candidate, "")
        for row in rows:
            tid = str(row.get("TeamID", ""))
            if tid:
                merged[tid] = row

    if _ASSOC_CODE_RE.match(q) and q[0].isalpha():
        initial = q[0].upper()
        extra = await _search_teams_request(client, "", initial)
        want = q.upper()
        for row in extra:
            abbr = (row.get("AssociationAbbrv") or "").strip().upper()
            if abbr == want:
                tid = str(row.get("TeamID", ""))
                if tid:
                    merged[tid] = row

    return list(merged.values())
