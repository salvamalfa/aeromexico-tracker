import Plotly from "../../lib/plotly";
import type { ChatChart } from "../../types/chat";

export function parseSafeChart(value: unknown): ChatChart | undefined {
  if (!value || typeof value !== "object") return undefined;
  const chart = value as Record<string, unknown>;
  if (chart.type !== "bar" && chart.type !== "line") return undefined;
  if (!Array.isArray(chart.x) || chart.x.length < 1 || chart.x.length > 100 || !Array.isArray(chart.series) || chart.series.length > 8) return undefined;
  const x = chart.x.filter((point): point is string | number =>
    (typeof point === "string" && point.length <= 120) || (typeof point === "number" && Number.isFinite(point)));
  if (x.length !== chart.x.length || chart.series.length < 1) return undefined;
  const series = chart.series.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const candidate = item as Record<string, unknown>;
    if (typeof candidate.name !== "string" || !Array.isArray(candidate.y) || candidate.y.length !== x.length ||
      !candidate.y.every((point) => point === null || (typeof point === "number" && Number.isFinite(point)))) return [];
    return [{ name: candidate.name.slice(0, 80), y: candidate.y as Array<number | null> }];
  });
  if (series.length !== chart.series.length) return undefined;
  return {
    type: chart.type,
    x,
    series,
    ...(typeof chart.title === "string" ? { title: chart.title.slice(0, 150) } : {}),
    ...(typeof chart.unit === "string" ? { unit: chart.unit.slice(0, 80) } : {}),
  };
}

export function renderSafeChart(host: HTMLElement, value: unknown): boolean {
  const chart = parseSafeChart(value);
  if (!chart) return false;
  const data = chart.series.map((series) => ({
    type: chart.type === "bar" ? "bar" : "scatter",
    mode: chart.type === "line" ? "lines+markers" : undefined,
    name: series.name,
    x: chart.x,
    y: series.y,
  }));
  void Plotly.newPlot(host, data as never, {
    title: { text: chart.title ?? "" },
    xaxis: { automargin: true },
    yaxis: { title: { text: chart.unit ?? "" }, automargin: true },
    margin: { l: 58, r: 18, t: chart.title ? 48 : 22, b: 54 },
    paper_bgcolor: "#fff", plot_bgcolor: "#fff", showlegend: chart.series.length > 1,
    height: 280,
  } as never, { responsive: true, displayModeBar: false, staticPlot: true } as never);
  return true;
}

