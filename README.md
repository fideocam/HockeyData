# HockeyData – Finnish Hockey Player Flow Sankey Diagrams

Visualises how Finnish hockey players move between clubs, using live data from [leijonat.fi](https://www.leijonat.fi/pelaajat).

---

## How to use the tool (where players came from or went)

Open the app (**http://localhost:5173** after [Quick start](#quick-start)), stay on the **Player flows** tab, then work through the controls from top to bottom.

### 1. Pick what you want to know: diagram type

| Mode | What it answers |
|------|-----------------|
| **← One step back** | For each player on the roster in the season you chose, **which team they played for the season before**. |
| **One step forward →** | For players who were on that roster in that season, **which team they played for the season after**. |
| **◀◀ Full career in** | **Every season** on the way *into* that team: multi-column Sankey, one column per year, paths leading up to your focal team and season. |
| **Full career out ▶▶** | **Every season** *after* that team: paths showing where players went over the following years. |

Use **one step** modes for a quick picture (incoming vs outgoing class). Use **full career** modes when you care about junior paths, loans, or several hops before or after the focal club.

### 2. Set season, league level, and team

1. **Season** — The year is the **end** of the Finnish season (e.g. **2026** = 2025–26). The roster and movements are interpreted in that league year.
2. **Level / League** — Same idea as on leijonat (Liiga, U18 III-divisioona, etc.). The team search **narrows suggestions** to teams that fit that level so you are less likely to pick a junior or senior line by mistake. **All levels** turns that filter off.
3. **Team** — Type a club name or abbreviation and pick from the list. Short codes (e.g. `EVU`) also pull in other teams from the same association when the text search alone is incomplete.

If your team does not appear in search, paste a [joukkuekortti](https://www.leijonat.fi/index.php/joukkueet) URL or numeric **`teamid`** under **Joukkuekortti team**, click **Lookup** to fill abbreviation and level from the card, then **Build diagram**.

### 3. Build and read the diagram

Click **Build diagram**. Fetching many careers can take **5–30 seconds**.

- **Sankey links** — Thickness shows how many players (or games—see below) move along that path.
- **Hover a link** — In simple modes you see **which players** are in that flow. In career modes you see names for that segment of the path.
- **One step modes only** — Choose **# Players** vs **Games played** for link width, and use **Show table** for a sortable list of previous or next teams with player names.

The headline under the chart restates the question (e.g. where players **came from** vs **went after**) for the team and season you selected.

### 4. Youth retention (other tab)

**Youth retention** is a separate analysis: it aggregates where players from a youth level went across two seasons, not a single-team Sankey. Use **Player flows** for “where did *this team’s* players come from or go?”.

---

## What it does (summary)

Given a team (abbreviation or exact joukkuekortti team id) and a season, the tool builds an interactive **Sankey diagram** (and optional table) from official career histories so you can see **incoming** and **outgoing** movement at a glance, or full **multi-year** paths.

## Requirements

- Python 3.9+
- Node.js 18+

## Quick start

```bash
# Install Python deps
pip3 install -r backend/requirements.txt

# Install frontend deps
cd frontend && npm install && cd ..

# Start everything
chmod +x start.sh && ./start.sh
```

Then open **http://localhost:5173** in your browser. The API serves at **http://localhost:8000** (interactive docs: **/docs**).

## API (reference)

| Endpoint | Description |
|----------|-------------|
| `GET /api/levels` | League levels (id, name, group) for the level picker |
| `GET /api/search-teams?q=…` | Team search (merged association browse for short codes) |
| `GET /api/team-from-id?teamid=…` | Resolve joukkuekortti team id → name, abbreviation, level |
| `GET /api/sankey/to-current?team=…&season=…&level=…` | One step **into** roster: previous season’s team per player |
| `GET /api/sankey/from-previous?team=…&season=…&level=…` | One step **out** of roster: next season’s team per player |
| `GET /api/sankey/career-paths?…&direction=to_current` (or `from_previous`) | Multi-season career Sankey |
| `GET /api/retention?…` | Youth retention aggregation (separate from team flows) |
| `GET /api/player-career?link_id=…` | Raw career JSON for one player (advanced) |

Optional query parameter on Sankey routes: **`team_id`** — joukkuekortti numeric id for an exact roster when text search is ambiguous.

## Season numbers

| Season | Value |
|--------|--------|
| 2025–26 | `2026` |
| 2024–25 | `2025` |
| 2023–24 | `2024` |

## Notes

- Team abbreviations should match leijonat usage (`HIFK`, `TPS`, `JYP`, etc.). Unknown clubs: use **joukkuekortti** `teamid`.
- Career history is fetched in parallel (large rosters capped per API defaults).
- Concurrency batching limits load on leijonat.fi; data is **live**, not cached locally.
