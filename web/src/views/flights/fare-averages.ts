// Public, contracted means. Individual quotes, book IDs and flight times never arrive here.
import { addObservationPeriods, currentPeriodId } from "../../state/period";
import type { OfficialPoint, OfficialRoute } from "../../types/official-routes";
import { esc } from "./dom";
import { fetchPublicationManifest } from "../../lib/publication-manifest";

export interface Mean { mean: number | null; n: number }
export interface FareAverage {
  provider: "AMR" | "DOTERS" | "VOLARIS"; period_id: string;
  origin: string; destination: string; origin_map_id: string | null; destination_map_id: string | null;
  fare: string; conditions: string; horizon_months: number; stay_days: number | null; trip_type: string;
  observations: number; paired_cash_points: number; query_date_start: string; query_date_end: string;
  points_applicability: string; group_id: string;
  metrics: Record<"cash_final_mxn" | "points" | "redemption_cash_mxn" | "redemption_taxes_mxn", Mean>;
}
interface FareAverages { schema_version: string; periods: string[]; groups: FareAverage[] }
let document: FareAverages | null = null;
const providers = { AMR: "Aeroméxico", DOTERS: "Viva / Doters", VOLARIS: "Volaris" };
const money = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });
const number = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 1 });
const periodLabel = (id: string) => `${id.slice(-1)}T${id.slice(2, 4)}`;
const display = (value: Mean, points = false) => value.mean === null ? "N/D" : points ? number.format(value.mean) : money.format(value.mean);

export async function loadFareAverages(dataRoot: string): Promise<void> {
  document = null;
  try {
    // Older immutable releases do not advertise this optional product. Avoid
    // requesting a missing asset: browsers report a 404 even when fetch is caught.
    if (import.meta.env.VITE_LOCAL_FARES !== "true") {
      const base = new URL(`${dataRoot.replace(/\/$/, "")}/`, window.document.baseURI);
      const manifestUrl = new URL("../../publication_manifest.json", base);
      const manifest = await fetchPublicationManifest(manifestUrl) as { files?: { path: string }[] };
      const productUrl = new URL("fare-averages.json", base);
      const manifestBase = new URL(".", manifestUrl).href;
      if (!productUrl.href.startsWith(manifestBase)) return;
      const productPath = productUrl.href.slice(manifestBase.length);
      if (!Array.isArray(manifest.files) || !manifest.files.some(file => file.path === productPath)) return;
    }
    const response = await fetch(`${dataRoot}/fare-averages.json`);
    if (!response.ok) return; // An older immutable release can have no quote product yet.
    const value = await response.json() as FareAverages;
    if (value.schema_version !== "fare_averages_v1" || !Array.isArray(value.groups) || !Array.isArray(value.periods)) return;
    document = value;
    addObservationPeriods(value.periods, new URLSearchParams(window.location.search).get("period"));
  } catch { document = null; }
}
export function setFareAveragesForTest(value: FareAverages | null): void { document = value; }
export function hasFarePeriod(period: string): boolean { return document?.periods.includes(period) ?? false; }
function matches(point: OfficialPoint, airport: string, mapId: string | null): boolean {
  return point.point_kind === "airport" ? point.iata === airport : point.id === mapId;
}
export function fareGroupsForRoute(route: OfficialRoute, period = currentPeriodId()): FareAverage[] {
  return document?.groups.filter(group => group.period_id === period && (
    matches(route.origin, group.origin, group.origin_map_id) && matches(route.destination, group.destination, group.destination_map_id)
    || matches(route.destination, group.origin, group.origin_map_id) && matches(route.origin, group.destination, group.destination_map_id))) ?? [];
}
function groupLabel(group: FareAverage): string {
  return `${providers[group.provider]} · ${group.origin}→${group.destination} · ${group.fare} · +${group.horizon_months} mes${group.horizon_months === 1 ? "" : "es"} · ${group.stay_days === null ? "sólo ida" : `regreso +${group.stay_days} días`}`;
}
export function fareTooltipColumns(route: OfficialRoute, period = currentPeriodId()): string {
  const groups = fareGroupsForRoute(route, period);
  const heading = `Costo medio · consultas ${period ? periodLabel(period) : "N/D"}`;
  const dateStart = groups.map(group => group.query_date_start).sort()[0] ?? "";
  const dateEnd = groups.map(group => group.query_date_end).sort().at(-1) ?? "";
  if (!groups.length) return `<div class="fare-route-averages"><h4>${esc(heading)}</h4><p>Sin observaciones verificadas para esta ruta y trimestre de consulta.</p></div>`;
  return `<div class="fare-route-averages"><h4>${esc(heading)}</h4><div class="fare-average-scroll"><table><thead><tr><th>Proveedor / tarifa</th><th>Dinero · MXN</th><th>Puntos</th><th>Base</th></tr></thead><tbody>${groups.map(group => `<tr><th scope="row">${esc(groupLabel(group))}<details><summary>Condiciones</summary><small>${esc(group.conditions)}</small><small>Pago final canje: ${group.provider === "VOLARIS" ? "No aplica" : display(group.metrics.redemption_cash_mxn)} · n=${group.metrics.redemption_cash_mxn.n}. Impuestos canje: ${group.provider === "VOLARIS" ? "No aplica" : display(group.metrics.redemption_taxes_mxn)} · n=${group.metrics.redemption_taxes_mxn.n}.</small></details></th><td>${display(group.metrics.cash_final_mxn)}</td><td>${group.provider === "VOLARIS" ? "No aplica" : display(group.metrics.points, true)}</td><td>Dinero n=${group.metrics.cash_final_mxn.n}<br>Puntos n=${group.metrics.points.n}<br>Pares n=${group.paired_cash_points}</td></tr>`).join("")}</tbody></table></div><p>Media aritmética de observaciones verificadas; no de todos los vuelos. Consulta ${esc(dateStart)}–${esc(dateEnd)}. Los faltantes no se convierten en cero.</p></div>`;
}
export function fareHoverLines(route: OfficialRoute, period = currentPeriodId()): string {
  const groups = fareGroupsForRoute(route, period);
  if (!groups.length) return "";
  return `<br><b>Medias de consultas ${esc(periodLabel(period!))}</b><br>Dinero MXN | Puntos | base` + groups.map(group =>
    `<br>${esc(groupLabel(group))}<br>${display(group.metrics.cash_final_mxn)} | ${group.provider === "VOLARIS" ? "No aplica" : display(group.metrics.points, true)} | n dinero=${group.metrics.cash_final_mxn.n}, puntos=${group.metrics.points.n}`).join("");
}
