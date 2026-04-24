"""
HockeyData API — FastAPI backend for Finnish hockey Sankey diagrams.
"""

import asyncio
from dataclasses import asdict
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from leijonat_client import (
    extract_team_id,
    get_player_career,
    get_player_season_stats,
    get_team_main_data,
    get_team_season_roster,
    roster_row_link_id,
    search_players,
    search_teams,
)
from retention_builder import OrgProgression, analyze_progression
from sankey_builder import (
    build_career_paths_sankey,
    build_from_previous_sankey,
    build_to_current_sankey,
)

app = FastAPI(title="HockeyData", description="Finnish hockey Sankey diagram API")


@app.get("/")
async def root():
    """Avoid a bare 404 when someone opens the API host in a browser."""
    return {
        "service": "HockeyData API",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
        "api": {
            "levels": "GET /api/levels",
            "search_teams": "GET /api/search-teams?q=HIFK",
            "team_from_id": "GET /api/team-from-id?teamid=<joukkuekortti-id-or-full-url>",
            "sankey_to_current": "GET /api/sankey/to-current?team=HIFK&season=2026&level=64",
            "sankey_from_previous": "GET /api/sankey/from-previous?team=HIFK&season=2026&level=64",
            "sankey_career_paths": "GET /api/sankey/career-paths?team=HIFK&season=2026&level=64&direction=to_current",
            "retention": "GET /api/retention?level=…&season_from=…&season_to=…&min_data_points=…",
        },
        "note": "All hockey data routes are under /api/… — see /docs for parameters.",
    }


@app.get("/api")
async def api_index():
    return await root()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client: Optional[httpx.AsyncClient] = None

LEVELS = [
    # Men
    {"id": "64",  "name": "Liiga",                  "group": "Men"},
    {"id": "65",  "name": "Mestis",                 "group": "Men"},
    {"id": "66",  "name": "Suomi-sarja",             "group": "Men"},
    {"id": "67",  "name": "II-divisioona",           "group": "Men"},
    {"id": "68",  "name": "III-divisioona",          "group": "Men"},
    {"id": "69",  "name": "IV-divisioona",           "group": "Men"},
    {"id": "70",  "name": "V-divisioona",            "group": "Men"},
    {"id": "71",  "name": "Harrastesarjat",          "group": "Men"},
    {"id": "72",  "name": "Seniorisarjat",           "group": "Men"},
    {"id": "73",  "name": "Auroraliiga",             "group": "Men"},
    # Women
    {"id": "74",  "name": "Naisten Mestis",          "group": "Women"},
    {"id": "75",  "name": "Naisten Suomi-sarja",     "group": "Women"},
    {"id": "113", "name": "N20 SM-turnaus",          "group": "Women"},
    {"id": "117", "name": "N16 SM",                  "group": "Women"},
    {"id": "119", "name": "N15 tytöt",               "group": "Women"},
    {"id": "120", "name": "N12 tytöt",               "group": "Women"},
    {"id": "121", "name": "N10-tytöt",               "group": "Women"},
    {"id": "133", "name": "National Team Women",     "group": "Women"},
    {"id": "134", "name": "National Team Women U18", "group": "Women"},
    # U20
    {"id": "77",  "name": "U20 SM-sarja",            "group": "U20"},
    {"id": "78",  "name": "U20 Mestis",              "group": "U20"},
    {"id": "79",  "name": "U20 Suomi-sarja",         "group": "U20"},
    {"id": "154", "name": "U20 II-divisioona",       "group": "U20"},
    {"id": "128", "name": "National Team U20",       "group": "U20"},
    # U18
    {"id": "81",  "name": "U18 SM-sarja",            "group": "U18"},
    {"id": "82",  "name": "U18 Mestis",              "group": "U18"},
    {"id": "83",  "name": "U18 Suomi-sarja",         "group": "U18"},
    {"id": "84",  "name": "U18 II-divisioona",       "group": "U18"},
    {"id": "151", "name": "U18 III-divisioona",      "group": "U18"},
    {"id": "130", "name": "National Team U18",       "group": "U18"},
    # U16
    {"id": "88",  "name": "U16 SM-sarja",            "group": "U16"},
    {"id": "89",  "name": "U16 Mestis",              "group": "U16"},
    {"id": "90",  "name": "U16 Suomi-sarja",         "group": "U16"},
    {"id": "152", "name": "U16 II-divisioona",       "group": "U16"},
    {"id": "131", "name": "National Team U17",       "group": "U16"},
    {"id": "132", "name": "National Team U16",       "group": "U16"},
    # U15
    {"id": "93",  "name": "U15 Sininen/A",           "group": "U15"},
    {"id": "94",  "name": "U15 Valkoinen/B",         "group": "U15"},
    {"id": "95",  "name": "U15 Keltainen/C",         "group": "U15"},
    # U14
    {"id": "97",  "name": "U14 Sininen/A",           "group": "U14"},
    {"id": "98",  "name": "U14 Valkoinen/B",         "group": "U14"},
    {"id": "99",  "name": "U14 C",                   "group": "U14"},
    # U13
    {"id": "101", "name": "U13 Sininen",             "group": "U13"},
    {"id": "102", "name": "U13 Valkoinen",           "group": "U13"},
    # U12 – U11
    {"id": "145", "name": "U12 sarja",               "group": "U12–U11"},
    {"id": "146", "name": "U11 sarja",               "group": "U12–U11"},
    # National Teams
    {"id": "127", "name": "National Team (Leijonat)", "group": "National"},
    {"id": "123", "name": "Pohjola-leiri",            "group": "National"},
    {"id": "135", "name": "Kartoitustapahtumat",      "group": "National"},
    {"id": "153", "name": "Soveltava jääkiekko",      "group": "Other"},
    {"id": "139", "name": "Liiton harrasteturnaukset", "group": "Other"},
]


@app.on_event("startup")
async def startup():
    global _client
    _client = httpx.AsyncClient()


@app.on_event("shutdown")
async def shutdown():
    if _client:
        await _client.aclose()


def get_client() -> httpx.AsyncClient:
    if _client is None:
        raise HTTPException(500, "HTTP client not initialized")
    return _client


@app.get("/api/levels")
async def api_levels():
    return LEVELS


@app.get("/api/search-teams")
async def api_search_teams(q: str = Query(..., min_length=1)):
    return await search_teams(get_client(), q)


@app.get("/api/team-from-id")
async def api_team_from_id(teamid: str = Query(..., min_length=1)):
    """
    Resolve a joukkuekortti team id (?teamid= on leijonat.fi/joukkueet) to name and level.
    Use this when the team search omits a lower-level team (same org, different roster).
    Accepts a bare id or a full pasted URL (query param may be the whole string).
    """
    tid = extract_team_id(teamid.strip())
    if not tid:
        raise HTTPException(
            422,
            "No numeric team id found. Paste the joukkuekortti URL or only the digits after teamid=.",
        )
    meta = await get_team_main_data(get_client(), tid)
    if not meta:
        raise HTTPException(
            404,
            f"No joukkuekortti data from leijonat.fi for team id {tid}.",
        )
    return {
        "teamid": tid,
        "teamName": meta.get("TeamName"),
        "teamAbbrv": meta.get("TeamAbbrv"),
        "levelId": meta.get("LevelID"),
        "associationId": meta.get("AssociationID"),
        "associationName": meta.get("AssociationName"),
        "statGroupName": meta.get("StatGroupName"),
    }


@app.get("/api/search-players")
async def api_search_players(
    team: str = Query(""),
    name: str = Query(""),
    level: str = Query("0"),
):
    return await search_players(get_client(), team_name=team, player_name=name, level=level)


async def _fetch_players_and_careers(
    client: httpx.AsyncClient,
    team: str,
    level: str,
    max_players: int,
) -> tuple[list[dict], dict[str, dict]]:
    """
    Leijonat returns ~40 players per search index page. Merge several pages so strict
    level+season confirmation (no loose Association fallback) still finds full rosters.
    """
    # Enough pages to cover typical rosters after filtering; cap total HTTP calls.
    target_candidates = min(600, max(160, max_players * 2))
    num_pages = min(25, max(5, (target_candidates + 39) // 40))
    page_results = await asyncio.gather(
        *[
            search_players(client, team_name=team, player_name="", level=level, index=i)
            for i in range(num_pages)
        ],
        return_exceptions=True,
    )
    merged: dict[str, dict] = {}
    for batch in page_results:
        if isinstance(batch, Exception) or not batch:
            continue
        for p in batch:
            lid = p.get("LinkID")
            if lid and str(lid) not in merged:
                merged[str(lid)] = p
    players = list(merged.values())
    if not players:
        raise HTTPException(404, f"No players found for team '{team}'" +
                            (f" at level {level}" if level != "0" else ""))

    players = players[:target_candidates]

    careers: dict[str, dict] = {}
    batch_size = 20
    for i in range(0, len(players), batch_size):
        batch = players[i: i + batch_size]
        results = await asyncio.gather(
            *[get_player_career(client, p["LinkID"]) for p in batch],
            return_exceptions=True,
        )
        for p, r in zip(batch, results):
            careers[p["LinkID"]] = r if not isinstance(r, Exception) else {"Skater": [], "Goalkeeper": []}

    return players, careers


async def _careers_for_players(client: httpx.AsyncClient, players: list[dict]) -> dict[str, dict]:
    careers: dict[str, dict] = {}
    batch_size = 20
    for i in range(0, len(players), batch_size):
        batch = players[i: i + batch_size]
        results = await asyncio.gather(
            *[get_player_career(client, p["LinkID"]) for p in batch],
            return_exceptions=True,
        )
        for p, r in zip(batch, results):
            careers[p["LinkID"]] = r if not isinstance(r, Exception) else {"Skater": [], "Goalkeeper": []}
    return careers


async def _sankey_player_context(
    client: httpx.AsyncClient,
    team: str,
    team_id: str,
    level: str,
    season: str,
    max_players: int,
) -> tuple[list[dict], dict[str, dict], str, str, Optional[frozenset[str]], Optional[dict]]:
    """
    Returns (players, careers, team_abbr, level_id, cohort_link_ids, team_meta).

    When *team_id* is set, loads the official joukkuekortti roster (exact team),
    bypassing the text search which often omits lower-level teams.
    """
    tid_raw = team_id.strip()
    tid = ""
    if tid_raw:
        tid = extract_team_id(tid_raw) or (tid_raw if tid_raw.isdigit() else "")
        if not tid or not tid.isdigit():
            raise HTTPException(
                422,
                "Could not parse joukkuekortti team id from team_id. Use ?teamid=… digits or a full URL.",
            )
    if tid:
        meta = await get_team_main_data(client, tid)
        if not meta:
            raise HTTPException(404, f"No joukkuekortti data for team id {tid}.")
        assoc = meta.get("AssociationID") or ""
        roster = await get_team_season_roster(client, tid, season, assoc)
        if not roster:
            raise HTTPException(
                404,
                f"No roster returned for team id {tid} in season {season}. "
                "Try another season year.",
            )
        players: list[dict] = []
        for row in roster[:max_players]:
            lid = roster_row_link_id(row.get("PersonID", ""))
            if not lid:
                continue
            players.append({
                "PersonID": lid,
                "LinkID": lid,
                "LastName": row.get("LastName", ""),
                "FirstName": row.get("FirstName", ""),
                "Association": meta.get("TeamAbbrv", ""),
                "Position": "",
            })
        if not players:
            raise HTTPException(404, "Roster contains no valid player identifiers.")
        careers = await _careers_for_players(client, players)
        cohort = frozenset(p["LinkID"] for p in players)
        lvl = str(meta.get("LevelID") or level)
        abbr = str(meta.get("TeamAbbrv") or team.strip() or "?")
        return players, careers, abbr, lvl, cohort, meta

    if not team.strip():
        raise HTTPException(
            400,
            "Enter a team abbreviation or paste a joukkuekortti URL / team id.",
        )
    players, careers = await _fetch_players_and_careers(client, team.strip(), level, max_players)
    return players, careers, team.strip(), level, None, None


def _attach_team_id_meta(sankey, team_id: str, meta: Optional[dict]) -> None:
    """Populate display fields when the cohort was loaded via joukkuekortti team id."""
    if not team_id.strip():
        return
    sankey.resolved_team_id = team_id.strip()
    if meta:
        sankey.focal_team_display = meta.get("TeamName")
        if meta.get("LevelID") is not None:
            sankey.resolved_level_id = str(meta["LevelID"])


def _sankey_response(sankey) -> dict:
    d = asdict(sankey)
    if sankey.confirmed_count == 0:
        raise HTTPException(404,
            f"No confirmed players found for '{sankey.focal_team}'. "
            "Try adjusting the season, level, or team name.")
    out = {
        "nodes": d["nodes"],
        "links": d["links"],
        "focal_team": d["focal_team"],
        "mode": d["mode"],
        "player_count": d["confirmed_count"],
        "searched_count": d["total_searched"],
        "node_x": d["node_x"],
        "node_y": d["node_y"],
        "flows": [asdict(f) for f in sankey.player_flows],
    }
    if sankey.focal_team_display:
        out["focal_team_display"] = sankey.focal_team_display
    if sankey.resolved_team_id:
        out["resolved_team_id"] = sankey.resolved_team_id
    if sankey.resolved_level_id:
        out["resolved_level_id"] = sankey.resolved_level_id
    return out


async def _fetch_game_weights(
    client: httpx.AsyncClient,
    confirmed_flows,
    players: list[dict],
    season: str,
) -> dict[str, int]:
    """
    Fetch games-played for each confirmed player in the focal season.
    Returns {person_id: games_played}.
    """
    # Build personID → linkID map from the search results
    link_by_pid = {p.get("PersonID", ""): p.get("LinkID", "") for p in players}
    confirmed_pids = {f.person_id for f in confirmed_flows}

    fetch_items = [
        (pid, link_by_pid[pid])
        for pid in confirmed_pids
        if pid in link_by_pid and link_by_pid[pid]
    ]

    results = await asyncio.gather(
        *[get_player_season_stats(client, link_id, season) for _, link_id in fetch_items],
        return_exceptions=True,
    )

    weights: dict[str, int] = {}
    for (pid, _), result in zip(fetch_items, results):
        if isinstance(result, Exception):
            weights[pid] = 1
        else:
            gp = result.get("skater_games") or result.get("goalie_games") or 0
            weights[pid] = max(1, int(gp))

    return weights


@app.get("/api/sankey/to-current")
async def api_sankey_to_current(
    team: str = Query("", description="Team abbreviation / search string"),
    team_id: str = Query("", description="Joukkuekortti ?teamid=… (exact roster)"),
    season: str = Query("2026"),
    level: str = Query("0"),
    weight: str = Query("players", description="'players' or 'games'"),
    max_players: int = Query(300),
):
    client = get_client()
    players, careers, team_abbr, lvl, cohort, meta = await _sankey_player_context(
        client, team, team_id, level, season, max_players,
    )
    sankey = build_to_current_sankey(
        players, careers, team_abbr, season, lvl, cohort_link_ids=cohort,
    )
    _attach_team_id_meta(sankey, team_id, meta)

    if weight == "games" and sankey.player_flows:
        game_weights = await _fetch_game_weights(client, sankey.player_flows, players, season)
        sankey = build_to_current_sankey(
            players, careers, team_abbr, season, lvl, game_weights, cohort_link_ids=cohort,
        )
        _attach_team_id_meta(sankey, team_id, meta)

    return _sankey_response(sankey)


@app.get("/api/sankey/from-previous")
async def api_sankey_from_previous(
    team: str = Query(""),
    team_id: str = Query(""),
    season: str = Query(...),
    level: str = Query("0"),
    weight: str = Query("players", description="'players' or 'games'"),
    max_players: int = Query(300),
):
    client = get_client()
    players, careers, team_abbr, lvl, cohort, meta = await _sankey_player_context(
        client, team, team_id, level, season, max_players,
    )
    sankey = build_from_previous_sankey(
        players, careers, team_abbr, season, lvl, cohort_link_ids=cohort,
    )
    _attach_team_id_meta(sankey, team_id, meta)

    if weight == "games" and sankey.player_flows:
        game_weights = await _fetch_game_weights(client, sankey.player_flows, players, season)
        sankey = build_from_previous_sankey(
            players, careers, team_abbr, season, lvl, game_weights, cohort_link_ids=cohort,
        )
        _attach_team_id_meta(sankey, team_id, meta)

    return _sankey_response(sankey)


@app.get("/api/sankey/career-paths")
async def api_sankey_career_paths(
    team: str = Query("", description="Team abbreviation, e.g. 'HIFK'"),
    team_id: str = Query("", description="Joukkuekortti ?teamid=…"),
    season: str = Query("2026", description="Focal season year, e.g. '2026'"),
    level: str = Query("0", description="Level ID to confirm players; '0' = any"),
    direction: str = Query("to_current", description="'to_current' or 'from_previous'"),
    max_players: int = Query(300),
    max_seasons_back: int = Query(10, description="How many seasons back to trace"),
):
    """
    Career-path Sankey: multi-step diagram with one column per season.
    Each node = (season, team); links show year-over-year player movement.
    """
    client = get_client()
    players, careers, team_abbr, lvl, cohort, meta = await _sankey_player_context(
        client, team, team_id, level, season, max_players,
    )
    sankey = build_career_paths_sankey(
        players, careers, team_abbr, focal_season=season,
        level_id=lvl, direction=direction,
        max_seasons_back=max_seasons_back,
        cohort_link_ids=cohort,
    )
    _attach_team_id_meta(sankey, team_id, meta)
    return _sankey_response(sankey)


@app.get("/api/retention")
async def api_retention(
    level: str = Query("0", description="Level ID; '0' = any"),
    season_from: str = Query("2021", description="Start of analysis window (inclusive)"),
    season_to: str = Query("2024", description="End of analysis window — transitions to season_to+1 are measured"),
    min_data_points: int = Query(5, description="Min player-season data points per org to be included"),
    max_pages: int = Query(25, description="Pages × 20 players per pass (two passes run)"),
):
    """
    Multi-season career-continuation analysis.

    Two-pass player discovery:
      Pass 1 — paginate the level-filtered search to find currently registered players.
      Pass 2 — for each org discovered in pass 1, do an additional team-name search
               to surface historical players (those who left the system post-2021).

    For every (player, season, org) data point in [season_from, season_to] we then
    check whether the player has any career entry the following season.
    """
    client = get_client()

    # ── Pass 1: level-filtered pagination ──────────────────────────────────────
    p1_results = await asyncio.gather(
        *[search_players(client, player_name="", level=level, index=i) for i in range(max_pages)],
        return_exceptions=True,
    )

    seen_pids: set[str] = set()
    all_players: list[dict] = []

    def _add_batch(batch):
        if isinstance(batch, Exception) or not batch:
            return
        for p in batch:
            pid = p.get("PersonID", "")
            if pid and pid not in seen_pids:
                seen_pids.add(pid)
                all_players.append(p)

    for batch in p1_results:
        _add_batch(batch)

    if not all_players:
        raise HTTPException(
            status_code=404,
            detail="No players found. Try selecting a specific level.",
        )

    # Fetch careers for pass-1 players
    def _link_ids(players):
        return [p["LinkID"] for p in players if p.get("LinkID")]

    async def _fetch_careers(players):
        ids = _link_ids(players)
        results = await asyncio.gather(
            *[get_player_career(client, lid) for lid in ids],
            return_exceptions=True,
        )
        return {lid: r for lid, r in zip(ids, results)
                if not isinstance(r, Exception) and r}

    careers: dict[str, dict] = await _fetch_careers(all_players)

    # ── Pass 2: per-org team search to add historical players ─────────────────
    # Find orgs that appear at this level in [season_from, season_to]
    from_int, to_int = int(season_from), int(season_to)
    discovered_orgs: set[str] = set()
    for link_id, career in careers.items():
        for role in ("Skater", "Goalkeeper"):
            for entry in career.get(role, []):
                sn = entry.get("SeasonNumber", "")
                if not sn:
                    continue
                try:
                    si = int(sn)
                except ValueError:
                    continue
                if not (from_int <= si <= to_int):
                    continue
                if level != "0" and entry.get("LevelID") != level:
                    continue
                teams = entry.get("LevelTeams") or []
                if teams:
                    discovered_orgs.add(teams[0].get("AssAbbrv", ""))

    discovered_orgs.discard("")

    if discovered_orgs:
        p2_results = await asyncio.gather(
            *[
                search_players(client, team_name=org, level=level, index=i)
                for org in discovered_orgs
                for i in range(5)   # 5 pages per org
            ],
            return_exceptions=True,
        )
        for batch in p2_results:
            _add_batch(batch)

        # Fetch careers for newly discovered players
        new_players = [p for p in all_players if p.get("LinkID") not in careers]
        if new_players:
            new_careers = await _fetch_careers(new_players)
            careers.update(new_careers)

    # ── Analysis ───────────────────────────────────────────────────────────────
    orgs = analyze_progression(
        all_players, careers, level, season_from, season_to, min_data_points
    )

    if not orgs:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No organisations with ≥{min_data_points} data points found. "
                "Try a wider season range, lower threshold, or a different level."
            ),
        )

    def _org_dict(r: OrgProgression) -> dict:
        return {
            "org": r.org,
            "total": r.total,
            "professional": r.professional,
            "competitive": r.competitive,
            "active": r.active,
            "recreational": r.recreational,
            "no_record": r.no_record,
            "continued_rate": round(r.continued_rate, 1),
            "high_level_rate": round(r.high_level_rate, 1),
            "professional_rate": round(r.professional_rate, 1),
            "competitive_rate": round(r.competitive_rate, 1),
            "active_rate": round(r.active_rate, 1),
            "recreational_rate": round(r.recreational_rate, 1),
            "no_record_rate": round(r.no_record_rate, 1),
            "professional_names": r.professional_names,
            "competitive_names": r.competitive_names,
            "active_names": r.active_names,
            "recreational_names": r.recreational_names,
            "no_record_names": r.no_record_names,
        }

    return {
        "level": level,
        "season_from": season_from,
        "season_to": season_to,
        "total_players_fetched": len(all_players),
        "total_orgs": len(orgs),
        "capped": len(all_players) >= max_pages * 20,
        "orgs": [_org_dict(r) for r in orgs],
    }


@app.get("/api/player-career")
async def api_player_career(link_id: str = Query(...)):
    return await get_player_career(get_client(), link_id)


@app.get("/health")
async def health():
    return {"status": "ok"}
