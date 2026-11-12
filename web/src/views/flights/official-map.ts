import type { MapCarrier, MapRegion, MapScope, OfficialRoute } from "../../types/official-routes";
import { currentPeriodId } from "../../state/period";
import { fareListColumns, fareTooltipColumns, hasFarePeriod } from "./fare-averages";
import { esc, integer } from "./dom";
import { mapPeriodLabel } from "./map-periods";
import { state as flights } from "./state";
import { bindSourceInfo, closeSourceInfoWithin } from "../market/source-info";
import { drawOfficialMap } from "./official-map-chart";
import { geographicRoutes, incidentOfficialRoutes, loadOfficialRoutes, MAP_CARRIERS, MAP_CARRIER_LABELS,
  MAP_REGIONS, MAP_SCOPES, officialRouteTitle, officialState, parseMapSelection, previousComparisonMonths, routeHasGeometry,
  searchOfficialPoints, selectOfficialNetwork, syncMapUrl, visibleOfficialRoutes } from "./official-routes";

const el = (id: string) => document.getElementById(id);
let searchTimer: ReturnType<typeof setTimeout> | undefined;
function setSearchOpen(open: boolean, restoreFocus = false): void {
  clearTimeout(searchTimer);
  const box = el("official-map-search-box"), toggle = el("official-map-search-toggle");
  const input = el("official-map-search") as HTMLInputElement | null;
  if (box) box.hidden = !open;
  if (toggle) { toggle.setAttribute("aria-expanded", String(open)); toggle.setAttribute("aria-label", open ? "Cerrar búsqueda" : "Buscar ruta"); }
  if (open) input?.focus();
  else { if (input) input.value = ""; el("official-map-search-results")?.replaceChildren(); if (restoreFocus) toggle?.focus(); }
}
function monthsLabel(months: string[]): string { return months.length ? months.map(mapPeriodLabel).join(", ") : "Sin meses disponibles"; }
function comparisonLabel(route: OfficialRoute): string {
  const c = route.comparison;
  if (c.yoy_pct === null) return c.reason ?? "Sin periodo comparable";
  return `${c.yoy_pct >= 0 ? "+" : ""}${c.yoy_pct.toFixed(1)} % frente a ${monthsLabel(previousComparisonMonths(route))} (${integer.format(c.previous_departures!)} vuelos)`;
}

export function officialRouteDetails(route: OfficialRoute): string {
  const point = (id: string) => [route.origin, route.destination].find(p => p.id === id)?.label ?? id;
  return `<div class="official-route-detail"><dl><div><dt>Meses disponibles</dt><dd>${esc(monthsLabel(route.monthly.map(m => m.period_id)))}</dd></div>
    ${route.monthly.map(m => `<div><dt>${esc(mapPeriodLabel(m.period_id))}</dt><dd>${integer.format(m.departures)} vuelos</dd></div>`).join("")}
    ${route.directions.map(d => `<div><dt>${esc(point(d.origin_id))} → ${esc(point(d.destination_id))}</dt><dd>${integer.format(d.departures)} vuelos</dd></div>`).join("")}
    <div><dt>Comparación interanual</dt><dd>${esc(comparisonLabel(route))}</dd></div>
    ${route.operators.map(o => `<div><dt>${esc(o.label)}</dt><dd>${integer.format(o.departures)} vuelos</dd></div>`).join("")}
    ${!routeHasGeometry(route) ? '<div><dt>Ubicación</dt><dd>No disponible; incluida en el total y la lista.</dd></div>' : ""}
    </dl>${fareTooltipColumns(route, officialState.period, officialState.scope === "us" ? officialState.carriers : undefined)}</div>`;
}

function focusNode(id: string): void {
  officialState.selectedNode = id; officialState.selectedRoute = null; renderRouteList(); void redrawOfficialMap();
  if (window.matchMedia("(max-width:900px)").matches) el("airport-tooltip")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}
function focusRoute(id: string): void {
  if (!officialState.routes.some(route => route.route_key === id)) return;
  officialState.selectedRoute = officialState.selectedRoute === id ? null : id;
  renderRouteList(); void redrawOfficialMap();
}

function renderSearch(): void {
  const input = el("official-map-search") as HTMLInputElement | null;
  const results = el("official-map-search-results");
  if (!input || !results) return;
  results.replaceChildren();
  for (const { point, count } of searchOfficialPoints(input.value)) {
    const button = document.createElement("button"); button.type = "button";
    button.textContent = `${point.label}${point.iata ? ` · ${point.iata}` : ""} · ${count} rutas`;
    button.addEventListener("click", () => { setSearchOpen(false); focusNode(point.id); el("official-map-back")?.focus(); });
    results.append(button);
  }
  if (input.value.trim() && !results.children.length) results.textContent = "Sin coincidencias en esta selección";
}

export function renderRouteList(): void {
  const host = el("official-route-list"); if (!host) return;
  const selected = officialState.selectedNode;
  const routes = selected ? incidentOfficialRoutes(selected) : visibleOfficialRoutes();
  const node = selected ? officialState.routes.flatMap(r => [r.origin, r.destination]).find(p => p.id === selected) : undefined;
  const title = node ? node.label : officialState.view === "all" ? "Todas las rutas" : officialState.view === "change" ? "Mayores cambios" : "Rutas destacadas";
  const heading = el("official-route-heading"); if (heading) heading.textContent = title;
  const count = el("official-map-route-count");
  if (count) count.textContent = `${routes.length} de ${officialState.routes.length} rutas reportadas`;
  const back = el("official-map-back"); if (back) back.hidden = !selected;
  host.innerHTML = routes.map((route, index) => {
    const months = route.monthly.length, expected = officialState.network?.expected_months.length ?? 3;
    const partial = months < expected;
    const opened = officialState.selectedRoute === route.route_key;
    return `<li class="official-route-item"><button type="button" data-official-route="${esc(route.route_key)}" aria-expanded="${opened}" class="official-route-button">
      <span class="official-route-name"><span class="official-rank${partial ? " official-partial" : ""}" title="${esc(monthsLabel(route.monthly.map(m => m.period_id)))}">${index + 1}</span> ${esc(officialRouteTitle(route))}${officialState.view === "change" ? `<small>${esc(comparisonLabel(route))}</small>` : ""}</span>
      <strong>${integer.format(route.departures)}</strong>
      ${fareListColumns(route, officialState.period, officialState.scope === "us" ? officialState.carriers : undefined)}
      </button>${opened ? officialRouteDetails(route) : ""}</li>`;
  }).join("");
  if (!routes.length) host.innerHTML = `<li class="official-map-empty">${officialState.loading ? "Cargando rutas oficiales…" : officialState.error || "Sin rutas disponibles para esta selección y trimestre."}</li>`;
  host.querySelectorAll<HTMLButtonElement>("[data-official-route]").forEach(button => button.addEventListener("click", () => focusRoute(button.dataset.officialRoute!)));
  const status = el("live-status"); if (status && selected) status.textContent = `${title}: ${routes.length} rutas disponibles en toda la selección.`;
}

function sourceDetails(): void {
  const panel = el("official-map-source-note"), button = el("official-map-source");
  if (!panel || !button) return;
  const network = officialState.network;
  const sources = officialState.document?.sources.filter(source => network?.source_ids.includes(source.id)) ?? [];
  const institution = officialState.scope === "us" ? "BTS" : "AFAC";
  const source = [...sources].sort((a, b) => b.source_period.localeCompare(a.source_period))
    .find(item => institution === "BTS" || /SASE/i.test(item.label)) ?? sources[0];
  panel.replaceChildren();
  panel.append(document.createTextNode("Fuente: "));
  if (source) {
    const link = document.createElement("a"); link.href = source.url; link.textContent = institution;
    link.target = "_blank"; link.rel = "noopener noreferrer"; panel.append(link);
  }
  if (!source) panel.append(document.createTextNode(institution));
  const scope = officialState.scope === "us"
    ? "Operaciones observadas México–EE. UU. de los operadores seleccionados. Clases regulares F y G: pasajeros y carga. Grupo Aeroméxico suma Aerovías y Connect, conservando sus operadores."
    : "Vuelos regulares reportados por AFAC, todas las aerolíneas, pasajeros y carga. Agregados ciudad–ciudad; no se atribuyen a una aerolínea ni a un aeropuerto.";
  const region = officialState.scope === "international" ? " Internacional excluye Estados Unidos. Centroamérica incluye el Caribe." : "";
  const missingGeometry = officialState.routes.filter(route => !routeHasGeometry(route));
  panel.append(document.createTextNode(`. ${scope}${region} ${mapPeriodLabel(network?.period_id ?? officialState.period)}: ${monthsLabel(network?.observed_months ?? [])}. `
    + `Se suman ambos sentidos y sólo los meses disponibles. Un faltante no es cero. La lista incluye ${officialState.routes.filter(route => route.departures === 0).length} rutas con cero explícito; sólo se dibujan vuelos positivos. ${missingGeometry.length} rutas sin ubicación (${integer.format(missingGeometry.reduce((sum, route) => sum + route.departures, 0))} vuelos) permanecen en la lista y el total. Comparaciones sólo con meses equivalentes del año anterior. ${officialState.document?.metadata.geography_attribution ?? ""}`));
  bindSourceInfo(button, panel);
}

function renderSummary(): void {
  const network = officialState.network, total = officialState.routes.reduce((sum, route) => sum + route.departures, 0);
  const basis = el("official-map-period-basis");
  if (basis) basis.textContent = network && network.period_id !== officialState.period
    ? `Tráfico de referencia: ${mapPeriodLabel(network.period_id)} · Consultas de precios: ${mapPeriodLabel(officialState.period)}.`
    : `Tráfico: ${mapPeriodLabel(officialState.period)} · Precios: trimestre de consulta seleccionado.`;
  const available = !!network && network.availability !== "unavailable";
  const partial = available && network.availability === "partial";
  const value = el("official-map-total"); if (value) value.textContent = available && officialState.routes.length ? integer.format(total) : "N/D";
  const coverage = el("official-map-months");
  if (coverage) { coverage.textContent = `${network?.observed_months.length ?? 0}/${network?.expected_months.length ?? 3} meses`; coverage.classList.toggle("official-partial", partial); }
  const source = el("official-map-source");
  if (source) { source.classList.toggle("official-partial", partial); source.setAttribute("aria-label", `Fuente y cobertura del mapa${partial ? ": trimestre parcial" : ""}`); }
  sourceDetails();
  const title = el("network-title");
  const text = title?.querySelector(".official-map-title-text"); if (text) text.textContent = `Rutas · ${MAP_SCOPES[officialState.scope]}`;
  const carrierHost = el("official-map-carriers"); if (carrierHost) carrierHost.hidden = officialState.scope !== "us";
  const region = el("official-map-region-control"); if (region) region.hidden = officialState.scope !== "international";
  el("official-map-controls")?.querySelectorAll<HTMLButtonElement>("[data-map-scope]").forEach(button => {
    const active = button.dataset.mapScope === officialState.scope;
    button.setAttribute("aria-checked", String(active)); button.setAttribute("aria-pressed", String(active)); button.tabIndex = active ? 0 : -1;
  });
  const changeAvailable = officialState.routes.some(route => route.comparison.yoy_pct !== null && route.comparison.yoy_pct !== 0);
  if (!changeAvailable && officialState.view === "change") officialState.view = "volume";
  const change = el("map-routes-change") as HTMLButtonElement | null;
  if (change) { change.disabled = !changeAvailable; change.title = changeAvailable ? "Cambio frente a los mismos meses del año anterior" : "Sin meses comparables del año anterior"; }
  for (const [id, view] of [["map-routes-featured", "volume"], ["map-routes-change", "change"], ["map-routes-all", "all"]]) el(id)?.setAttribute("aria-pressed", String(officialState.view === view));
  renderRouteList();
}

let request = 0;
export async function renderOfficialMap(period = currentPeriodId() ?? ""): Promise<void> {
  const current = ++request;
  const signature = `${period}|${officialState.scope}|${officialState.carriers.join(",")}|${officialState.region}`;
  officialState.period = period; officialState.loading = true; officialState.error = "";
  setSearchOpen(false);
  const map = el("route-flow-map"); if (map) map.dataset.mapStatus = "loading";
  officialState.selectedNode = null; officialState.selectedRoute = null;
  officialState.network = null; officialState.routes = [];
  renderSummary(); void redrawOfficialMap();
  try {
    const doc = await loadOfficialRoutes(flights.dataRoot);
    if (current !== request || signature !== `${officialState.period}|${officialState.scope}|${officialState.carriers.join(",")}|${officialState.region}`) return;
    officialState.network = selectOfficialNetwork(doc, period, officialState.scope, officialState.carriers);
    if (!officialState.network && hasFarePeriod(period)) {
      const previous = [...doc.periods].filter(id => id < period).sort().reverse();
      for (const id of previous) {
        const candidate = selectOfficialNetwork(doc, id, officialState.scope, officialState.carriers);
        if (candidate?.routes.length) { officialState.network = candidate; break; }
      }
    }
    officialState.routes = geographicRoutes(officialState.network, officialState.region);
  } catch (error) {
    if (current !== request) return;
    officialState.error = error instanceof Error ? error.message : "No se pudieron cargar las rutas oficiales";
  }
  if (current !== request) return;
  officialState.loading = false; renderSummary(); await redrawOfficialMap();
}

export async function redrawOfficialMap(): Promise<void> { await drawOfficialMap(focusNode, focusRoute); }

export function mountOfficialMap(): void {
  const host = el("official-map-controls"); if (!host) return;
  Object.assign(officialState, parseMapSelection(new URLSearchParams(window.location.search)));
  const select = el("official-map-region") as HTMLSelectElement | null;
  if (select) { select.value = officialState.region ?? ""; select.addEventListener("change", () => {
    officialState.region = (select.value || null) as MapRegion | null; syncMapUrl(); void renderOfficialMap();
  }); }
  const pick = el("official-map-carriers");
  if (pick) {
    pick.innerHTML = `<summary aria-label="Aerolíneas México–EE. UU."></summary><div class="official-carrier-menu" role="group" aria-label="Aerolíneas México–EE. UU.">${MAP_CARRIERS.map(key => `<label><input type="checkbox" value="${key}">${MAP_CARRIER_LABELS[key]}</label>`).join("")}</div>`;
    const paint = () => {
      pick.querySelector("summary")!.textContent = officialState.carriers.length === 3 ? "Las tres aerolíneas" : officialState.carriers.length === 1 ? MAP_CARRIER_LABELS[officialState.carriers[0]!] : "2 aerolíneas";
      pick.querySelectorAll<HTMLInputElement>("input").forEach(box => { box.checked = officialState.carriers.includes(box.value as MapCarrier); box.disabled = box.checked && officialState.carriers.length === 1; });
    };
    paint(); pick.addEventListener("change", () => {
      const keys = [...pick.querySelectorAll<HTMLInputElement>("input:checked")].map(box => box.value as MapCarrier);
      if (!keys.length) return;
      officialState.carriers = keys; paint(); syncMapUrl(); void renderOfficialMap();
    });
  }
  const scopeButtons = [...host.querySelectorAll<HTMLButtonElement>("[data-map-scope]")];
  scopeButtons.forEach((button, index) => {
    button.addEventListener("click", () => { officialState.scope = button.dataset.mapScope as MapScope; syncMapUrl(); void renderOfficialMap(); });
    button.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? scopeButtons.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + scopeButtons.length) % scopeButtons.length;
      scopeButtons[next]!.click(); scopeButtons[next]!.focus();
    });
  });
  for (const [id, view] of [["map-routes-featured", "volume"], ["map-routes-change", "change"], ["map-routes-all", "all"]] as const) el(id)?.addEventListener("click", () => {
    officialState.view = view; officialState.selectedNode = null; officialState.selectedRoute = null; renderSummary(); void redrawOfficialMap();
  });
  el("official-map-back")?.addEventListener("click", () => { officialState.selectedNode = null; officialState.selectedRoute = null; renderRouteList(); void redrawOfficialMap(); });
  el("official-map-search-toggle")?.addEventListener("click", () => setSearchOpen(el("official-map-search-box")?.hidden ?? true, true));
  el("official-map-search")?.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(renderSearch, 120); });
  el("official-map-search")?.addEventListener("keydown", event => {
    if (event.key === "Enter") { event.preventDefault(); clearTimeout(searchTimer); renderSearch(); el("official-map-search-results")?.querySelector<HTMLButtonElement>("button")?.click(); }
  });
  el("official-map-search-box")?.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setSearchOpen(false, true); }
  });
  // Both selectors preserve their independent selection when their scope is hidden.
  document.addEventListener("pointerdown", event => { if (pick && !pick.contains(event.target as Node)) pick.removeAttribute("open"); });
  window.addEventListener("reader-tab-visible", () => { const card = el("map-panel"); if (card) closeSourceInfoWithin(card); });
  // The chat sidebar changes the canvas width without a window resize.
  const canvas = el("route-flow-map");
  if (canvas && typeof ResizeObserver !== "undefined") {
    let size = "", queued = false;
    new ResizeObserver(() => {
      const next = `${canvas.clientWidth}x${canvas.clientHeight}`;
      if (!canvas.clientWidth || next === size || queued) return;
      size = next; queued = true;
      window.requestAnimationFrame(() => { queued = false; void redrawOfficialMap(); });
    }).observe(canvas);
  }
}
