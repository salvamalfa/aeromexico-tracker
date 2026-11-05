// Flight counts remain separate by evidence type. Their source popovers use
// the same accessible interaction as the financial and market cards.
import { $, esc, integer } from "./dom";
import { state } from "./state";
import { mapPeriodLabel } from "./map-periods";
import { flightTotals, FLIGHT_KIND_LABEL, type FlightKind } from "./flight-measure";
import type { Route } from "../../types/domain";
import type { FinancialSource } from "../../lib/financial-sources";
import { bindSourceInfo, closeSourceInfoWithin, AFAC_CATALOG_URL } from "../market/source-info";
import { INFO_ICON, setSourceDetail } from "./kpi-sources";

export function flightSourceReferences(routes: Route[], kind: FlightKind): FinancialSource[] {
  const labels = routes.flatMap(route => route.flight_components?.length
    ? route.flight_components.filter(component => component.kind === kind).map(component => component.source_label)
    : [route.source_label ?? ""]).join(" ");
  const sources: FinancialSource[] = [];
  if (/AeroDataBox/i.test(labels)) sources.push({label:"AeroDataBox",href:"https://doc.aerodatabox.com/docs/openapi-direct-v1.yaml"});
  if (/T-100|BTS/i.test(labels)) sources.push({label:"BTS",href:"https://www.transtats.bts.gov/TableInfo.asp?QO_fu146_anzr=Nv4+Pn44vr45&gnoyr_VQ=FJE"});
  if (/ANAC/i.test(labels)) sources.push({label:"ANAC Brasil",href:"https://www.anac.gov.br/acesso-a-informacao/dados-abertos"});
  if (/CAA/i.test(labels)) sources.push({label:"CAA Reino Unido",href:"https://www.caa.co.uk/data-and-analysis/uk-aviation-market/flight-punctuality/"});
  if (/AICM/i.test(labels)) sources.push({label:"AICM · programación",href:"https://www.aicm.com.mx/archivos/Negocios/Slots/verano/2026/amx.pdf"});
  if (/OMA/i.test(labels)) sources.push({label:"OMA · comunicados",href:"https://noticias.oma.aero/"});
  // AFAC in an estimate's label belongs to passenger modelling; it is not
  // the provider of its estimated flight frequencies.
  if (kind === "attributed" && /AFAC/i.test(labels)) sources.push({label:"AFAC",href:AFAC_CATALOG_URL});
  return sources;
}

function miniCard(key: string, label: string, value: string, note = ""): string {
  return `<div class="network-mini-kpi"><small class="network-mini-label">${esc(label)}<button type="button" class="network-mini-info" id="network-${key}-info" aria-label="Fuente y definición de ${esc(label)}">${INFO_ICON}</button></small><strong>${esc(value)}</strong>${note ? `<span>${esc(note)}</span>` : ""}<div id="network-${key}-source"></div></div>`;
}

export function renderNetworkVolume(): void {
  const host = $("network-volume"); if (!host) return;
  closeSourceInfoWithin(host);
  const routes = state.routes; host.hidden = false;
  const details: {key:string;sources:FinancialSource[];detail:string}[] = [];
  const cards = (["observed", "scheduled", "estimated", "attributed"] as const).flatMap(kind => {
    const matching = routes.filter(route => flightTotals(route)[kind] !== undefined);
    if (!matching.length) return [];
    const total = matching.reduce((sum, route) => sum + (flightTotals(route)[kind] ?? 0), 0);
    const detail = kind === "scheduled" ? "Vuelos programados; no confirma que se hayan realizado."
      : kind === "estimated" ? "Frecuencias históricas estimadas; no acredita vuelos realizados."
      : kind === "attributed" ? "Total del mercado atribuido a la aerolínea; operador sin confirmación exhaustiva."
      : state.evidenceView === "north_america_observed" && state.selectedRegion === "norteamerica"
        ? `México–EE.UU.; ${state.observedNorthAmericaMonths.map(mapPeriodLabel).join(", ") || "meses disponibles"}. Sólo operaciones reportadas; Canadá estimado fuera.`
        : "Suma de operaciones reportadas en las rutas y meses disponibles; cobertura parcial.";
    details.push({key:kind,sources:flightSourceReferences(matching,kind),detail});
    return [miniCard(kind,`Vuelos ${FLIGHT_KIND_LABEL[kind]}`,integer.format(total))];
  });
  const movements = routes.filter(route => route.recorded_movements);
  if (movements.length) {
    const count = movements.reduce((sum, route) => sum + route.recorded_movements!.count, 0);
    const months = [...new Set(movements.flatMap(route => route.recorded_movements!.observed_months))].sort();
    cards.push(miniCard("movements","Movimientos registrados · Aerocivil",integer.format(count),`Provisional · ${months.join(", ")} · fuera de vuelos`));
    details.push({key:"movements",sources:[{label:"Aerocivil Colombia",href:"https://www.datos.gov.co/Transportation/Operaciones-a-reas-acumuladas-en-Colombia/jh8x-n6h6"}],detail:"Movimientos provisionales en el aeropuerto colombiano, no salidas. No se suman a vuelos."});
  }
  cards.push(`<div class="network-mini-kpi network-coverage"><small class="network-mini-label">Cobertura del mapa<button type="button" id="flight-map-coverage-button" class="network-mini-info" aria-label="Cobertura y rutas del mapa">${INFO_ICON}</button></small><strong id="flight-map-coverage" aria-live="polite">No disponible</strong><div id="flight-map-coverage-info"></div></div>`);
  if (!routes.length && state.presenceOnlyRouteCount) {
    cards.unshift(miniCard("missing","Vuelos","N/D"));
    details.push({key:"missing",sources:[],detail:"La fuente confirma presencia sin número de vuelos; un faltante no es cero."});
  }
  host.innerHTML = `<div class="network-mini-kpi-grid">${cards.join("")}</div>`;
  for (const detail of details) {
    const button = document.getElementById(`network-${detail.key}-info`)!;
    const panel = document.getElementById(`network-${detail.key}-source`)!;
    setSourceDetail(panel,detail.sources,detail.detail); bindSourceInfo(button,panel);
  }
}
