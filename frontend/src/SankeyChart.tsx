import { useCallback, useEffect, useRef, useState } from "react";
import type { SankeyNodeMeta, SankeyResponse } from "./api";
import type { Data, Layout } from "plotly.js";

type PlotlyStatic = typeof import("plotly.js");

let Plotly: PlotlyStatic | null = null;
import("plotly.js-dist-min").then((m) => {
  Plotly = m.default as unknown as PlotlyStatic;
});

interface Props {
  data: SankeyResponse;
  weight?: "players" | "games";
  onNodePick?: (label: string, meta?: SankeyNodeMeta) => void;
}

const ACCENT = "#1a5fa8";
const NODE_DEFAULT = "#4a90d9";
const NODE_UNKNOWN = "#9ca3af";
const LINK_ALPHA = 0.38;
const EXPORT_SIZE = 1200;

const NEUTRAL_LABELS = new Set([
  "Unknown / first team", "Unknown", "Left hockey",
  "Stayed / left game", "Still at team / left game",
]);

type ExportFormat = "svg" | "png";

function rgba(hex: string, a: number) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

const isCareerMode = (mode: string) => mode.startsWith("career_");

export default function SankeyChart({ data, weight = "players", onNodePick }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(!!Plotly);
  const [plotSize, setPlotSize] = useState(640);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);

  useEffect(() => {
    if (Plotly) return;
    const iv = setInterval(() => { if (Plotly) { setReady(true); clearInterval(iv); } }, 80);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.round(entry.contentRect.width);
      if (width > 0) setPlotSize(Math.max(320, width));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!plotRef.current || !ready || !Plotly) return;
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

    const trace: Data = {
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

    const layout: Partial<Layout> = {
      font: { family: "system-ui, sans-serif", size: career ? 11 : 13, color: "#111827" },
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      margin: { l: 16, r: 16, t: career ? 30 : 16, b: 16 },
      width: plotSize,
      height: plotSize,
    };

    // Always purge first so switching teams never carries over stale node positions
    Plotly!.purge(plotRef.current);
    const plotEl = plotRef.current as any;
    const handlePlotClick = (event: any) => {
      const point = event?.points?.[0];
      const label = typeof point?.label === "string" ? point.label : "";
      if (label && nodes.includes(label)) {
        const nodeIndex = typeof point?.pointNumber === "number"
          ? point.pointNumber
          : nodes.indexOf(label);
        onNodePick?.(label, data.node_meta?.[nodeIndex]);
      }
    };

    Plotly!.newPlot(plotRef.current, [trace], layout, {
      displayModeBar: false,
      responsive: false,
    }).then(() => {
      if (onNodePick) plotEl.on("plotly_click", handlePlotClick);
    });

    return () => {
      if (plotEl?.removeListener) plotEl.removeListener("plotly_click", handlePlotClick);
      if (plotRef.current && Plotly) Plotly!.purge(plotRef.current);
    };
  }, [data, onNodePick, plotSize, ready, weight]);

  const downloadImage = useCallback(async (format: ExportFormat) => {
    if (!plotRef.current || !Plotly) return;
    setExporting(format);
    try {
      const url = await (Plotly as any).toImage(plotRef.current, {
        format,
        width: EXPORT_SIZE,
        height: EXPORT_SIZE,
      });
      const safeName = [data.focal_team, data.mode, "sankey"]
        .join("-")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      const a = document.createElement("a");
      a.href = url;
      a.download = `${safeName}.${format}`;
      a.click();
    } finally {
      setExporting(null);
    }
  }, [data.focal_team, data.mode]);

  if (!ready) return <div className="chart-placeholder">Loading chart…</div>;
  return (
    <div className="sankey-chart-shell">
      <div className="sankey-chart-toolbar">
        <span className="sankey-chart-note">Click a career node to explore from that team and year</span>
        <div className="sankey-chart-actions">
          <button className="btn-ghost" onClick={() => downloadImage("svg")} disabled={!!exporting}>
            {exporting === "svg" ? "Preparing…" : "Download SVG"}
          </button>
          <button className="btn-ghost" onClick={() => downloadImage("png")} disabled={!!exporting}>
            {exporting === "png" ? "Preparing…" : "Download PNG"}
          </button>
        </div>
      </div>
      <div className="sankey-chart-viewport" ref={viewportRef}>
        <div className="sankey-chart-plot" ref={plotRef} />
      </div>
    </div>
  );
}
