import { useEffect, useRef, useState } from "react";
import type { SankeyResponse } from "./api";

let Plotly: typeof import("plotly.js-dist-min") | null = null;
import("plotly.js-dist-min").then((m) => {
  Plotly = m.default as typeof import("plotly.js-dist-min");
});

interface Props {
  data: SankeyResponse;
  weight?: "players" | "games";
}

const ACCENT = "#1a5fa8";
const NODE_DEFAULT = "#4a90d9";
const NODE_UNKNOWN = "#9ca3af";
const LINK_ALPHA = 0.38;

const NEUTRAL_LABELS = new Set([
  "Unknown / first team", "Unknown", "Left hockey",
  "Stayed / left game", "Still at team / left game",
]);

function rgba(hex: string, a: number) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

const isCareerMode = (mode: string) => mode.startsWith("career_");

export default function SankeyChart({ data, weight = "players" }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(!!Plotly);

  useEffect(() => {
    if (Plotly) return;
    const iv = setInterval(() => { if (Plotly) { setReady(true); clearInterval(iv); } }, 80);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    if (!ref.current || !ready || !Plotly) return;
    const { nodes, links, focal_team, node_x, node_y, mode } = data;

    const career = isCareerMode(mode);

    const nodeColors = nodes.map((n) => {
      // In career mode the focal team appears in multiple seasons; match by team name part
      const teamPart = career ? n.split(" · ")[1] : n;
      if (teamPart === focal_team) return ACCENT;
      if (NEUTRAL_LABELS.has(n) || NEUTRAL_LABELS.has(teamPart)) return NODE_UNKNOWN;
      return NODE_DEFAULT;
    });

    const hasPositions = career && node_x.length === nodes.length && node_y.length === nodes.length;

    const nodeUnit = weight === "games" ? "gp" : "player(s)";
    const nodeConfig: any = {
      pad: career ? 12 : 18,
      thickness: career ? 16 : 20,
      line: { color: "transparent", width: 0 },
      label: nodes,
      color: nodeColors,
      hovertemplate: `<b>%{label}</b><br>%{value} ${nodeUnit}<extra></extra>`,
    };

    if (hasPositions) {
      nodeConfig.x = node_x;
      nodeConfig.y = node_y;
    }

    const trace: Plotly.Data = {
      type: "sankey",
      orientation: "h",
      arrangement: hasPositions ? "fixed" : "snap",
      node: nodeConfig,
      link: {
        source: links.map((l) => l.source),
        target: links.map((l) => l.target),
        value: links.map((l) => l.value),
        label: links.map((l) => l.label),
        color: links.map(() => rgba(NODE_DEFAULT, LINK_ALPHA)),
        customdata: links.map((l) => l.players.join("<br>")),
        hovertemplate: "<b>%{label}</b><br><br>%{customdata}<extra></extra>",
      } as any,
    };

    // Height: more nodes need more space; career mode is wider
    const height = career
      ? Math.max(560, nodes.length * 22 + 80)
      : Math.max(520, nodes.length * 28 + 80);

    const layout: Partial<Plotly.Layout> = {
      font: { family: "system-ui, sans-serif", size: career ? 11 : 13, color: "#111827" },
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      margin: { l: 16, r: 16, t: career ? 30 : 16, b: 16 },
      height,
    };

    // Always purge first so switching teams never carries over stale node positions
    Plotly!.purge(ref.current);
    Plotly!.newPlot(ref.current, [trace], layout, {
      displayModeBar: false,
      responsive: true,
    });

    return () => { if (ref.current && Plotly) Plotly!.purge(ref.current); };
  }, [data, ready]);

  if (!ready) return <div className="chart-placeholder">Loading chart…</div>;
  return <div ref={ref} style={{ width: "100%", minHeight: 520 }} />;
}
