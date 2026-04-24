import { useState, useEffect, useRef } from "react";
import { api } from "./api";
import type { Level, RetentionResponse, RetentionOrg } from "./api";
import LevelPicker from "./LevelPicker";

let Plotly: typeof import("plotly.js-dist-min") | null = null;
import("plotly.js-dist-min").then((m) => {
  Plotly = m.default as typeof import("plotly.js-dist-min");
});

const SEASON_YEARS = Array.from({ length: 20 }, (_, i) => {
  const end = 2025 - i;
  return { value: String(end), label: `${end - 1}–${String(end).slice(2)}` };
});

type SortKey = "high_level_rate" | "continued_rate" | "professional_rate" | "total";

const TIERS: { key: keyof RetentionOrg; label: string; color: string; rateKey: keyof RetentionOrg }[] = [
  { key: "professional",  label: "Professional / Elite",  color: "#1a5fa8", rateKey: "professional_rate" },
  { key: "competitive",   label: "Competitive junior/amateur", color: "#38bdf8", rateKey: "competitive_rate" },
  { key: "active",        label: "Active (lower divisions)", color: "#86efac", rateKey: "active_rate" },
  { key: "recreational",  label: "Recreational / camps", color: "#fde68a", rateKey: "recreational_rate" },
  { key: "no_record",     label: "No next-season record", color: "#d1d5db", rateKey: "no_record_rate" },
];

interface Props { levels: Level[] }

function seasonLabel(s: string) {
  const end = parseInt(s);
  return `${end - 1}–${String(end).slice(2)}`;
}

function buildPlotData(orgs: RetentionOrg[], sortKey: SortKey) {
  const sorted = [...orgs].sort((a, b) => {
    const va = a[sortKey] as number, vb = b[sortKey] as number;
    return va - vb;
  });
  const names = sorted.map((o) => o.org);
  const totals = sorted.map((o) => o.total);

  const makeCustom = (o: RetentionOrg, names: string[], pct: number, tierLabel: string) =>
    `<b>${o.org}</b> — ${o.total} observations<br>` +
    `${tierLabel}: ${pct.toFixed(1)}%<br><br>` +
    (names as string[]).slice(0, 15).join("<br>") +
    ((names as string[]).length > 15 ? `<br>…+${(names as string[]).length - 15} more` : "");

  const traces = TIERS.map((tier) => ({
    type: "bar",
    orientation: "h",
    name: tier.label,
    x: sorted.map((o) => o[tier.rateKey] as number),
    y: names,
    marker: { color: tier.color },
    customdata: sorted.map((o) =>
      makeCustom(o, o[`${tier.key}_names` as keyof RetentionOrg] as string[], o[tier.rateKey] as number, tier.label)
    ),
    hovertemplate: "%{customdata}<extra></extra>",
  }));

  const height = Math.max(380, sorted.length * 36 + 130);

  const layout: object = {
    barmode: "stack",
    height,
    margin: { l: 90, r: 56, t: 20, b: 50 },
    xaxis: { title: "% of observations", range: [0, 100], ticksuffix: "%" },
    yaxis: { automargin: true, tickfont: { size: 12 } },
    font: { family: "system-ui, sans-serif", size: 13 },
    legend: { orientation: "h", y: -0.18, x: 0 },
    plot_bgcolor: "#fff", paper_bgcolor: "#fff",
    hoverlabel: { align: "left", namelength: 0 },
    annotations: totals.map((t, i) => ({
      x: 101, y: names[i], text: `n=${t}`,
      xanchor: "left", showarrow: false,
      font: { size: 11, color: "#6b7280" },
      xref: "x", yref: "y",
    })),
  };

  return { traces, layout };
}

export default function RetentionView({ levels }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [plotlyReady, setPlotlyReady] = useState(!!Plotly);

  const [levelId, setLevelId] = useState("82");
  const [seasonFrom, setSeasonFrom] = useState("2021");
  const [seasonTo, setSeasonTo] = useState("2024");
  const [minDataPoints, setMinDataPoints] = useState(5);
  const [sortKey, setSortKey] = useState<SortKey>("high_level_rate");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RetentionResponse | null>(null);

  useEffect(() => {
    if (Plotly) return;
    const iv = setInterval(() => { if (Plotly) { setPlotlyReady(true); clearInterval(iv); } }, 80);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    if (!chartRef.current || !plotlyReady || !Plotly || !result) return;
    const { traces, layout } = buildPlotData(result.orgs, sortKey);
    (Plotly as any).react(chartRef.current, traces, layout, { responsive: true, displayModeBar: false });
  }, [result, sortKey, plotlyReady]);

  async function analyze() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.retention(levelId, seasonFrom, seasonTo, minDataPoints);
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  const rangeValid = !isNaN(parseInt(seasonFrom)) && !isNaN(parseInt(seasonTo)) &&
    parseInt(seasonFrom) <= parseInt(seasonTo);

  return (
    <div className="retention-view">
      <section className="controls-card">
        <div className="filter-row">
          <div className="filter-group">
            <label className="filter-label">Youth level</label>
            <LevelPicker levels={levels} value={levelId} onChange={setLevelId} disabled={loading} />
          </div>
          <div className="filter-group">
            <label className="filter-label" htmlFor="ret-from">From season</label>
            <select id="ret-from" value={seasonFrom}
              onChange={(e) => setSeasonFrom(e.target.value)} disabled={loading}>
              {SEASON_YEARS.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <label className="filter-label" htmlFor="ret-to">To season</label>
            <select id="ret-to" value={seasonTo}
              onChange={(e) => setSeasonTo(e.target.value)} disabled={loading}>
              {SEASON_YEARS.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <label className="filter-label" htmlFor="min-dp">Min observations</label>
            <input id="min-dp" type="number" min={1} max={100} value={minDataPoints}
              onChange={(e) => setMinDataPoints(Math.max(1, parseInt(e.target.value) || 1))}
              disabled={loading} className="num-input" />
          </div>
          <div className="filter-group filter-group--submit">
            <label className="filter-label">&nbsp;</label>
            <button className="btn-primary" onClick={analyze} disabled={loading || !rangeValid}>
              {loading ? <><span className="btn-spinner" /> Analyzing…</> : "Analyze"}
            </button>
          </div>
        </div>

        <p className="filter-hint">
          For every player found at this youth level in the selected seasons, checks
          what level tier they played at the <em>following</em> season.
          Organisations whose players reach higher tiers develop youth more successfully.{" "}
          <strong>Professional</strong> = SM-liiga / Mestis / U20 top.{" "}
          <strong>No next-season record</strong> = career gap or left Finnish hockey.
          This analysis may take 20–40 s — two passes of search are run.
        </p>
      </section>

      {loading && (
        <div className="ret-status">
          <span className="btn-spinner" style={{ marginRight: 8 }} />
          Fetching players and career histories — please wait…
        </div>
      )}

      {error && <div className="error-box">{error}</div>}

      {result && !loading && (
        <section className="results-card">
          <div className="ret-header">
            <div>
              <h2 className="results-title">
                Where did youth players go — {seasonLabel(result.season_from)} to{" "}
                {seasonLabel(result.season_to)}
              </h2>
              <p className="ret-subtitle">
                {result.total_orgs} organisations · {result.total_players_fetched} players fetched
                {result.capped && (
                  <span className="ret-warn"> · search capped</span>
                )}
              </p>
            </div>

            <div className="sort-group">
              <span className="filter-label">Sort by</span>
              <div className="weight-toggle">
                {(
                  [
                    ["high_level_rate", "Pro + competitive"],
                    ["continued_rate", "Any continuation"],
                    ["professional_rate", "Professional only"],
                    ["total", "# Observations"],
                  ] as [SortKey, string][]
                ).map(([key, label]) => (
                  <button
                    key={key}
                    className={`weight-btn ${sortKey === key ? "active" : ""}`}
                    onClick={() => setSortKey(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div ref={chartRef} className="ret-chart" />
        </section>
      )}
    </div>
  );
}
