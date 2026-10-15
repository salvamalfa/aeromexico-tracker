// Flight counts only in the map; official aggregate cards remain elsewhere.
import { $, esc, integer } from "./dom";
import { state } from "./state";
import { flightKind, FLIGHT_KIND_LABEL } from "./flight-measure";

function miniCard(label: string, value: string, note: string, title: string): string {
  return `<div class="network-mini-kpi" title="${esc(title)}"><small>${esc(label)}</small><strong>${esc(value)}</strong><span>${esc(note)}</span></div>`;
}

export function renderNetworkVolume(): void {
  const host = $("network-volume");
  if (!host) return;
  const routes = state.routes;
  host.hidden = !routes.length && !state.presenceOnlyRouteCount;
  if (host.hidden) { host.innerHTML = ""; return; }
  const cards = (["observed", "scheduled", "estimated", "attributed"] as const).flatMap((kind) => {
    const matching = routes.filter((route) => flightKind(route) === kind);
    if (!matching.length) return [];
    const total = matching.reduce((sum, route) => sum + route.departures!, 0);
    const label = `Vuelos ${FLIGHT_KIND_LABEL[kind]}`;
    return [miniCard(label, integer.format(total), `${matching.length} rutas`,
      kind === "scheduled" ? "Programación; no confirma ejecución" :
      kind === "estimated" ? "Estimación histórica de frecuencias; no acredita operaciones realizadas" :
      kind === "attributed" ? "Total de mercado atribuido; operador sin confirmación exhaustiva" :
      "Operaciones reportadas por la fuente; cobertura parcial")];
  });
  host.innerHTML = `<div class="network-mini-kpi-grid">${cards.length ? cards.join("") : miniCard("Vuelos", "N/D", "Sin cifra publicada", "Un faltante no se convierte en cero")}</div>
    <span>Histórico conservado · tipos de cifra separados · faltantes N/D${state.presenceOnlyRouteCount ? ` · ${state.presenceOnlyRouteCount} rutas sin número de vuelos` : ""}</span>`;
}
