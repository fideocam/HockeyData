import { useState } from "react";
import { api } from "./api";
import type { PlayerNetworkResponse, PlayerNetworkRow } from "./api";

function seasonLabel(season: string) {
  const end = Number(season);
  if (!Number.isFinite(end)) return season;
  return `${end - 1}-${String(end).slice(2)}`;
}

function NetworkTable({ title, rows }: { title: string; rows: PlayerNetworkRow[] }) {
  return (
    <section className="network-card">
      <h3>{title}</h3>
      {!rows.length ? (
        <p className="muted">No game-roster matches found.</p>
      ) : (
        <table className="flow-table network-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Player</th>
              <th>Best same-season level</th>
              <th>Score</th>
              <th>Games</th>
              <th>Teams / seasons</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={`${row.person_id}-${row.link_id}`}>
                <td className="count-cell">{i + 1}</td>
                <td>
                  <strong>{row.name}</strong>
                  {row.best_teams.length ? <div className="muted">{row.best_teams.join(", ")}</div> : null}
                </td>
                <td>
                  {row.level_name || "Unknown"}
                  {row.best_season ? <div className="muted">Best season: {seasonLabel(row.best_season)}</div> : null}
                  {row.ranking_reasons.length ? (
                    <div className="muted">{row.ranking_reasons.join(" · ")}</div>
                  ) : null}
                </td>
                <td className="count-cell">{row.score}</td>
                <td className="count-cell">{row.encounter_games}</td>
                <td>
                  <div>{row.encounter_teams.join(", ")}</div>
                  <div className="muted">{row.encounter_seasons.map(seasonLabel).join(", ")}</div>
                  {row.sample_games.length ? (
                    <div className="muted">
                      e.g. {row.sample_games[0].date} {row.sample_games[0].home}-{row.sample_games[0].away}
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export default function PlayerNetworkView() {
  const [query, setQuery] = useState("");
  const [seasonsBack, setSeasonsBack] = useState(20);
  const [maxGames, setMaxGames] = useState(250);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PlayerNetworkResponse | null>(null);

  async function submit() {
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.playerNetwork(query.trim(), seasonsBack, maxGames));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <section className="filter-panel">
        <div className="filter-row">
          <div className="filter-group filter-group--team">
            <label className="filter-label" htmlFor="player-network-query">
              Player name or roster LinkID
            </label>
            <input
              id="player-network-query"
              className="teamid-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
              placeholder="e.g. Pyry Lammi or player roster LinkID"
              disabled={loading}
            />
          </div>
          <div className="filter-group">
            <label className="filter-label" htmlFor="network-seasons">Seasons back</label>
            <input
              id="network-seasons"
              className="teamid-input"
              type="number"
              min={1}
              max={20}
              value={seasonsBack}
              onChange={(e) => setSeasonsBack(Number(e.target.value))}
            />
          </div>
          <div className="filter-group">
            <label className="filter-label" htmlFor="network-max-games">Max games</label>
            <input
              id="network-max-games"
              className="teamid-input"
              type="number"
              min={1}
              max={250}
              value={maxGames}
              onChange={(e) => setMaxGames(Number(e.target.value))}
            />
          </div>
          <div className="filter-group filter-group--submit">
            <label className="filter-label">&nbsp;</label>
            <button className="btn-primary" onClick={submit} disabled={loading || !query.trim()}>
              {loading ? <><span className="btn-spinner" /> Analyzing…</> : "Find best players"}
            </button>
          </div>
        </div>
        <p className="filter-hint">
          Fetches the searched player’s team seasons, scans actual game rosters, and compares every player
          from those games by their best career season at the highest league or national-team level.
        </p>
      </section>

      {error && (
        <div className="error-banner">
          <strong>Error:</strong> {error}
        </div>
      )}

      {loading && (
        <div className="loading-state">
          <div className="loading-spinner" />
          <div>
            <p className="loading-title">Scanning game rosters and player careers…</p>
            <p className="loading-sub">This can take a while for players with many teams or national-team games.</p>
          </div>
        </div>
      )}

      {result && !loading && (
        <div className="result">
          <div className="result-header">
            <div className="result-title-block">
              <h2>Best players connected to {result.player.name}</h2>
              <div className="result-chips">
                <span className="chip chip--blue">{result.player.association || "Player"}</span>
                <span className="chip">{result.summary.scanned_games} games scanned</span>
                <span className="chip">{result.summary.scanned_team_seasons} team seasons</span>
              </div>
            </div>
          </div>
          <p className="filter-hint">{result.summary.method}</p>
          <div className="network-grid">
            <NetworkTable title="Highest-level players played with" rows={result.best_with} />
            <NetworkTable title="Highest-level players played against" rows={result.best_against} />
          </div>
        </div>
      )}
    </>
  );
}
