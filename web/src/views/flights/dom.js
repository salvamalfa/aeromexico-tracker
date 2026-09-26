// Small DOM and formatting helpers shared by the Vuelos view modules.
// Ported verbatim from src/dashboard/assets/flights.js (kept behaviourally
// identical; see docs/etapas/vuelos-pasajeros-traspaso-20260913.md).

export const $ = (id) => document.getElementById(id);

export const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[char]);

export const finite = (value) => typeof value === "number" && Number.isFinite(value);

export const integer = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 });
export const decimal = new Intl.NumberFormat("es-MX", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const percent = new Intl.NumberFormat("es-MX", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const dateLabel = (iso) => new Intl.DateTimeFormat("es-MX", { month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${iso.slice(0, 7)}-01T00:00:00Z`));

export function metricDisplay(key, value) {
  if (!finite(value)) return "No disponible";
  if (key === "load_factor") return percent.format(value);
  if (key === "passengers") return `${(value / 1e6).toFixed(3)} M`;
  return `${(value / 1e9).toFixed(3)} mil M`;
}

export function priorPeriod(periodId, years = 0) {
  const year = Number(periodId.slice(0, 4));
  const quarter = Number(periodId.slice(-1));
  if (years) return `${year - years}Q${quarter}`;
  return quarter === 1 ? `${year - 1}Q4` : `${year}Q${quarter - 1}`;
}

export function deltaDisplay(current, previous, points = false) {
  if (!finite(current) || !finite(previous) || (!points && previous === 0)) {
    return { text: "No disponible", className: "delta-na" };
  }
  const delta = points ? (current - previous) * 100 : (current / previous - 1) * 100;
  const text = points ? `${delta >= 0 ? "+" : ""}${delta.toFixed(1)} pp` : `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%`;
  return { text, className: delta > 0.005 ? "delta-up" : delta < -0.005 ? "delta-down" : "delta-na" };
}

export function setDelta(id, change) {
  const node = $(id);
  node.textContent = change.text;
  node.className = change.className;
}

export function formatRouteMetric(key, value) {
  if (!finite(value)) return "N/D";
  if (key === "load_factor") return percent.format(value);
  return integer.format(value);
}
