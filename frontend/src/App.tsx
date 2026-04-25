import { useState, useEffect, useCallback } from "react";
import { api } from "./api";
import type { Level, SankeyNodeMeta, SankeyNodePlayer, SankeyResponse } from "./api";
import SankeyChart from "./SankeyChart";
import TeamSearch from "./TeamSearch";
import LevelPicker from "./LevelPicker";
import RetentionView from "./RetentionView";
import "./App.css";

type AppTab = "flows" | "retention";

type Mode = "to_current" | "from_previous" | "career_to_current" | "career_from_previous";
type Weight = "players" | "games";
type GraphTraversalPick = {
  label: string;
  team: string;
  season: string;
  levelId: string;
  levelName?: string;
  players?: SankeyNodePlayer[];
};

const SEASONS = Array.from({ length: 21 }, (_, i) => {
  const end = 2026 - i;
  const start = end - 1;
  return { value: String(end), label: `${start}–${String(end).slice(2)}` };
});

/** Parse `?teamid=` / `TeamID=` from a joukkuekortti URL or accept a bare numeric id. */
function extractTeamIdFromPaste(raw: string): string | null {
  let t = raw.trim().replace(/[\u200b-\u200d\ufeff\ufffe]/g, "");
  if (!t) return null;
  t = t.replace(/&amp;/gi, "&");
  const m = t.match(/[?&#](?:teamid|TeamID)=(\d{4,24})\b/i);
  if (m) return m[1];
  if (/^\d{4,24}$/.test(t)) return t;
  return null;
}

function parseCareerNodeLabel(label: string): GraphTraversalPick | null {
  const parts = label.split(" · ");
  if (parts.length < 2) return null;

  const seasonLabel = parts[0].trim();
  const teamName = parts.slice(1).join(" · ").trim();
  const match = seasonLabel.match(/^(\d{4})[-–](\d{2}|\d{4})$/);
  if (!match || !teamName) return null;

  const startYear = match[1];
  const endPart = match[2];
  const endYear = endPart.length === 2 ? `${startYear.slice(0, 2)}${endPart}` : endPart;
  return { label, team: teamName, season: endYear, levelId: "0" };
}

function modeForOlderSeason(currentMode: Mode): Mode {
  if (currentMode === "to_current") return "from_previous";
  if (currentMode === "career_to_current") return "career_from_previous";
  return currentMode;
}

const MODE_OPTIONS: { value: Mode; label: string; description: string }[] = [
  {
    value: "to_current",
    label: "← One step back",
    description: "Where did each player come from the previous season?",
  },
  {
    value: "from_previous",
    label: "One step forward →",
    description: "Where did each player go the following season?",
  },
  {
    value: "career_to_current",
    label: "◀◀ Full career in",
    description: "Full year-by-year career paths leading up to this team & season.",
  },
  {
    value: "career_from_previous",
    label: "Full career out ▶▶",
    description: "Full year-by-year career paths after this team & season.",
  },
];

// ── Flow table (for simple modes) ─────────────────────────────────────────────
function FlowTable({ data }: { data: SankeyResponse }) {
  const isTo = data.mode === "to_current";
  const buckets: Record<string, { team: string; players: string[] }> = {};
  for (const f of data.flows) {
    const key = isTo ? f.source_team : f.target_team;
    if (!buckets[key]) buckets[key] = { team: key, players: [] };
    buckets[key].players.push(
      `${f.last_name} ${f.first_name}` + (f.position ? ` (${f.position})` : "")
    );
  }
  const rows = Object.values(buckets).sort((a, b) => b.players.length - a.players.length);

  return (
    <table className="flow-table">
      <thead>
        <tr>
          <th>{isTo ? "Previous team" : "Next team"}</th>
          <th>#</th>
          <th>Players</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.team}>
            <td className="team-cell">{r.team}</td>
            <td className="count-cell">{r.players.length}</td>
            <td className="names-cell">{r.players.join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Main app ──────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState<AppTab>("flows");
  const [levels, setLevels] = useState<Level[]>([]);
  const [mode, setMode] = useState<Mode>("career_to_current");
  const [weight, setWeight] = useState<Weight>("players");
  const [resultKey, setResultKey] = useState(0);
  const [season, setSeason] = useState("2026");
  const [levelId, setLevelId] = useState("64");
  const [team, setTeam] = useState("");
  const [selectedTeamName, setSelectedTeamName] = useState("");
  /** Joukkuekortti TeamID from search row pick — loads official roster instead of player search. */
  const [joukkueTeamIdFromPick, setJoukkueTeamIdFromPick] = useState("");
  const [teamIdOrUrl, setTeamIdOrUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SankeyResponse | null>(null);
  const [showTable, setShowTable] = useState(false);
  const [traversalPick, setTraversalPick] = useState<GraphTraversalPick | null>(null);

  useEffect(() => {
    api.levels(season).then(setLevels).catch(() => {});
  }, [season]);

  const parsedTeamId = extractTeamIdFromPaste(teamIdOrUrl);
  /** Lookup enabled for parsed id or any paste that still contains teamid= (server parses the rest). */
  const canLookupTeamPaste =
    !!parsedTeamId || /[?&#].*teamid\s*=\s*\d/i.test(teamIdOrUrl.trim());
  const canSubmit =
    !loading &&
    (team.trim().length >= 1 || !!parsedTeamId || !!joukkueTeamIdFromPick.trim());
  const selectedLevel = levels.find((l) => l.id === levelId) ?? null;

  const resolveTeamFromId = useCallback(async () => {
    const raw = teamIdOrUrl.trim();
    const id = extractTeamIdFromPaste(raw);
    if (!id && !raw) return;
    setError(null);
    try {
      const m = await api.teamFromId(id ?? raw);
      if (m.teamAbbrv) setTeam(m.teamAbbrv);
      if (m.teamName) setSelectedTeamName(m.teamName);
      if (m.levelId) setLevelId(m.levelId);
      if (m.teamid) setJoukkueTeamIdFromPick(m.teamid);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Lookup failed");
    }
  }, [teamIdOrUrl]);

  const submit = useCallback(async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const t = team.trim();
      const pasted = extractTeamIdFromPaste(teamIdOrUrl)?.trim();
      const tid = pasted || (joukkueTeamIdFromPick.trim() || undefined);
      const traversalCohort = traversalPick?.players?.length ? traversalPick.players : undefined;
      let data: SankeyResponse;
      if (mode === "to_current") {
        data = await api.sankeyToCurrent(t, season, levelId, weight, tid, traversalCohort);
      } else if (mode === "from_previous") {
        data = await api.sankeyFromPrevious(t, season, levelId, weight, tid, traversalCohort);
      } else {
        const dir = mode === "career_to_current" ? "to_current" : "from_previous";
        data = await api.sankeyCareerPaths(t, season, levelId, dir, 10, tid, traversalCohort);
      }
      setResult(data);
      setResultKey((k) => k + 1);
      setShowTable(false);
      setTraversalPick(null);
      if (data.resolved_level_id) setLevelId(data.resolved_level_id);
      setTeam(data.focal_team);
      setSelectedTeamName(data.focal_team_display ?? "");
      if (data.resolved_team_id) setJoukkueTeamIdFromPick(data.resolved_team_id);
    } catch (e: any) {
      setError(e.message ?? "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [team, teamIdOrUrl, joukkueTeamIdFromPick, traversalPick, season, levelId, mode, weight, canSubmit]);

  const selectGraphNode = useCallback((label: string, meta?: SankeyNodeMeta) => {
    const fallback = parseCareerNodeLabel(label);
    const teamFromMeta = meta?.team?.trim();
    const seasonFromMeta = meta?.season?.trim();
    const pick = teamFromMeta && seasonFromMeta
      ? {
          label,
          team: teamFromMeta,
          season: seasonFromMeta,
          levelId: meta?.level_id?.trim() || "0",
          levelName: meta?.level_name?.trim() || undefined,
          players: meta?.players ?? [],
        }
      : fallback;
    if (!pick) return;
    setTeam(pick.team);
    setSeason(pick.season);
    setLevelId(pick.levelId);
    setMode("career_from_previous");
    setJoukkueTeamIdFromPick("");
    setTeamIdOrUrl("");
    setSelectedTeamName(
      pick.levelName ? `${pick.team} (${pick.levelName}) from ${label}` : `${pick.team} from ${label}`
    );
    setTraversalPick(pick);
    setError(null);
  }, []);

  const currentLevel = levels.find((l) => l.id === levelId);
  const seasonLabel = SEASONS.find((s) => s.value === season)?.label ?? season;
  const modeInfo = MODE_OPTIONS.find((m) => m.value === mode)!;
  const isCareer = mode.startsWith("career_");
  const isSimple = !isCareer;

  const resultTitle = (() => {
    if (!result) return "";
    const t = result.focal_team_display ?? result.focal_team;
    switch (mode) {
      case "to_current":        return `Where ${t} players came from (${seasonLabel})`;
      case "from_previous":     return `Where ${t} players went after (${seasonLabel})`;
      case "career_to_current": return `Career paths into ${t} — up to ${seasonLabel}`;
      case "career_from_previous": return `Career paths out of ${t} — from ${seasonLabel}`;
    }
  })();

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div>
            <h1>Finnish Hockey Analytics</h1>
            <p className="subtitle">
              Player movement &amp; youth retention — data from{" "}
              <a href="https://www.leijonat.fi/pelaajat" target="_blank" rel="noreferrer">
                leijonat.fi
              </a>
            </p>
          </div>
        </div>
      </header>

      <div className="app-tabs">
        <button
          className={`app-tab ${tab === "flows" ? "active" : ""}`}
          onClick={() => setTab("flows")}
        >
          Player flows
        </button>
        <button
          className={`app-tab ${tab === "retention" ? "active" : ""}`}
          onClick={() => setTab("retention")}
        >
          Youth retention
        </button>
      </div>

      <main className="main">
        {tab === "retention" && <RetentionView levels={levels} />}

        {tab === "flows" && <>
        {/* ── Filter panel ── */}
        <section className="filter-panel">
          {/* Mode selector */}
          <div className="filter-group">
            <span className="filter-label">Diagram type</span>
            <div className="mode-grid">
              {MODE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  className={`mode-card ${mode === opt.value ? "active" : ""}`}
                  onClick={() => setMode(opt.value)}
                >
                  <span className="mode-card-label">{opt.label}</span>
                  <span className="mode-card-desc">{opt.description}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Controls row */}
          <div className="filter-row">
            <div className="filter-group">
              <label className="filter-label" htmlFor="season-select">Season</label>
              <select
                id="season-select"
                value={season}
                onChange={(e) => {
                  const nextSeason = e.target.value;
                  setSeason(nextSeason);
                  if (Number(nextSeason) < Number(SEASONS[0].value)) {
                    setMode((m) => modeForOlderSeason(m));
                  }
                  setResult(null);
                  setTraversalPick(null);
                }}
              >
                {SEASONS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label className="filter-label">Level / League</label>
              <LevelPicker
                levels={levels}
                value={levelId}
                onChange={setLevelId}
                disabled={loading}
              />
            </div>

            <div className="filter-group filter-group--team">
              <label className="filter-label">
                Team
                <span className="filter-label-hint">
                  {levelId === "0"
                    ? " — one suggestion per age group; pick a row for full roster"
                    : " — best level matches first; older/renamed teams still show"}
                </span>
              </label>
              <TeamSearch
                value={team}
                selectedTeamId={joukkueTeamIdFromPick}
                onChange={({ abbr, joukkueTeamId, teamName }) => {
                  setTeam(abbr);
                  setJoukkueTeamIdFromPick(joukkueTeamId ?? "");
                  setSelectedTeamName(teamName ?? "");
                  setTeamIdOrUrl("");
                  setTraversalPick(null);
                }}
                disabled={loading}
                level={selectedLevel}
              />
              {selectedTeamName && (
                <div className="selected-team-card">
                  <span className="selected-team-label">Selected team</span>
                  <span className="selected-team-name">{selectedTeamName}</span>
                  {team && <span className="selected-team-abbr">{team}</span>}
                </div>
              )}
            </div>

            <div className="filter-group filter-group--teamid">
              <label className="filter-label" htmlFor="team-id-paste">
                Joukkuekortti team
                <span className="filter-label-hint"> — URL or id if search misses your team</span>
              </label>
              <div className="teamid-row">
                <input
                  id="team-id-paste"
                  className="teamid-input"
                  type="text"
                  placeholder="e.g. …/joukkueet?teamid=326852543"
                  value={teamIdOrUrl}
                  onChange={(e) => setTeamIdOrUrl(e.target.value)}
                  disabled={loading}
                  spellCheck={false}
                />
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={resolveTeamFromId}
                  disabled={loading || !canLookupTeamPaste}
                >
                  Lookup
                </button>
              </div>
            </div>

            <div className="filter-group filter-group--submit">
              <label className="filter-label">&nbsp;</label>
              <button className="btn-primary" onClick={submit} disabled={!canSubmit}>
                {loading ? <><span className="btn-spinner" /> Building…</> : "Build diagram"}
              </button>
            </div>
          </div>

          {isSimple && (
            <div className="weight-toggle-row">
              <span className="filter-label">Link width</span>
              <div className="weight-toggle">
                <button
                  className={`weight-btn ${weight === "players" ? "active" : ""}`}
                  onClick={() => setWeight("players")}
                >
                  # Players
                </button>
                <button
                  className={`weight-btn ${weight === "games" ? "active" : ""}`}
                  onClick={() => setWeight("games")}
                >
                  Games played
                </button>
              </div>
            </div>
          )}

          <p className="filter-hint">
            <strong>{modeInfo.description}</strong>{" "}
            Lower-level teams are often missing from the text search — paste a{" "}
            <a href="https://www.leijonat.fi/index.php/joukkueet" target="_blank" rel="noreferrer">
              joukkuekortti
            </a>{" "}
            link or numeric <code className="inline-code">teamid</code> above, then build (Lookup fills level from the card).{" "}
            {isCareer &&
              "Each column is one season; each node is a team. Hover a flow to see player names."}
            {isSimple && weight === "players" &&
              "Link width = number of players. Hover a flow to see who is included."}
            {isSimple && weight === "games" &&
              "Link width = total games played in this team & season. Hover to see per-player detail."}
          </p>
        </section>

        {/* ── Error ── */}
        {error && (
          <div className="error-banner">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* ── Loading ── */}
        {loading && (
          <div className="loading-state">
            <div className="loading-spinner" />
            <div>
              <p className="loading-title">Fetching player careers from leijonat.fi…</p>
              <p className="loading-sub">
                {parsedTeamId || joukkueTeamIdFromPick
                  ? `Loading official roster for team id ${parsedTeamId ?? joukkueTeamIdFromPick}, ${seasonLabel}.`
                  : `Looking up ${team} at ${currentLevel?.name ?? "all levels"}, ${seasonLabel}.`}{" "}
                This can take 5–30 seconds depending on roster size.
              </p>
            </div>
          </div>
        )}

        {/* ── Result ── */}
        {result && !loading && (
          <div className="result">
            <div className="result-header">
              <div className="result-title-block">
                <h2>{resultTitle}</h2>
                <div className="result-chips">
                  <span className="chip chip--blue">
                    {result.focal_team_display ?? result.focal_team}
                  </span>
                  <span className="chip">{seasonLabel}</span>
                  {currentLevel && <span className="chip">{currentLevel.name}</span>}
                  <span className="chip chip--count">
                    {result.player_count} player{result.player_count !== 1 ? "s" : ""}
                  </span>
                  {result.searched_count > result.player_count && (
                    <span className="chip chip--muted">{result.searched_count} searched</span>
                  )}
                </div>
              </div>
              {isSimple && (
                <button className="btn-ghost" onClick={() => setShowTable((v) => !v)}>
                  {showTable ? "Hide table" : "Show table"}
                </button>
              )}
            </div>

            <div className="chart-card">
              {traversalPick && (
                <div className="traversal-card">
                  <div>
                    <span className="traversal-label">Selected from graph</span>
                    <strong>{traversalPick.team}</strong>
                    <span>{SEASONS.find((s) => s.value === traversalPick.season)?.label ?? traversalPick.season}</span>
                    {traversalPick.levelName && <span>{traversalPick.levelName}</span>}
                    {traversalPick.players?.length ? <span>{traversalPick.players.length} players</span> : null}
                  </div>
                  <button className="btn-primary" onClick={submit} disabled={!canSubmit}>
                    {loading ? <><span className="btn-spinner" /> Building…</> : "Build graph from this node"}
                  </button>
                </div>
              )}
              <SankeyChart
                key={resultKey}
                data={result}
                weight={isSimple ? weight : "players"}
                onNodePick={selectGraphNode}
              />
            </div>

            {isSimple && showTable && (
              <div className="table-card">
                <FlowTable data={result} />
              </div>
            )}
          </div>
        )}
        </>}
      </main>
    </div>
  );
}
