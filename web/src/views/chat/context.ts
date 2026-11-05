import { currentPeriodId } from "../../state/period";
import { selection, type EntityKey } from "../shell/carriers";
import { state as flightState } from "../flights/state";
import { entityLabel } from "../executive/entities";
import { state as executiveState } from "../executive/state";
import type { ChatContext } from "../../types/chat";
import { officialState, MAP_CARRIER_LABELS, MAP_REGIONS, MAP_SCOPES } from "../flights/official-routes";

const CARD_SELECTION: Record<string, string> = {
  "market-chart": "market", "market-card": "market", "unit-chart": "unit", "volume-chart": "volume",
  "load-chart": "load", "unit-card": "unit", "volume-card": "volume", "load-card": "load",
  "flight-kpis": "flight-kpis",
  "mix-chart": "mix", "route-flow-map": "map", "flow-map": "map",
  "panel-reading": "reading", "panel-economy": "kpis", "pick-kpis": "kpis",
  "reading-card": "reading",
  "flight-kpi-passengers": "flight-kpis", "flight-kpi-asm_miles": "flight-kpis",
  "flight-kpi-rpm_miles": "flight-kpis", "flight-kpi-load_factor": "flight-kpis",
  "kpi-rask_cents_per_km": "kpis", "kpi-cask_cents_per_km": "kpis", "kpi-ask_km": "kpis",
  "kpi-unit_margin_cents_per_km": "kpis",
};
const SINGLE_SELECTIONS = new Set(["reading", "kpis", "flight-kpis"]);

function activeTab(): "reading" | "economy" | "flights" | "market" | "news" {
  const active = document.querySelector<HTMLButtonElement>('.reader-tabs [role="tab"][aria-selected="true"]');
  const tab = active?.getAttribute("aria-controls")?.replace("panel-", "");
  return tab === "news" || tab === "market" || tab === "economy" || tab === "flights" ? tab : "reading";
}

function tabForCard(card: Element | null): "reading" | "economy" | "flights" | "market" | "news" | undefined {
  const panelId = card?.closest<HTMLElement>('[role="tabpanel"]')?.id;
  const tab = panelId?.replace("panel-", "");
  return tab === "reading" || tab === "news" || tab === "market" || tab === "economy" || tab === "flights" ? tab : undefined;
}

function cardIdFrom(node: Element | null): string | undefined {
  if (!node || node.closest("[data-chat-unavailable]")) return undefined;
  const card = node.closest<HTMLElement>(".chart-card, .panel.chart-panel, .panel.flow-map-panel, .kpi-card, .flight-kpi, .narrative-card");
  if (!card) return node.closest(".flights-view") ? "flights" : undefined;
  if (card.id && card.id !== "map-panel") return card.id;
  if (card.classList.contains("narrative-card")) return "reading-card";
  const graphId = card.querySelector<HTMLElement>(".chart[id]")?.id;
  if (graphId) return graphId;
  const flightKpiId = card.querySelector<HTMLElement>('[id^="flight-kpi-"]')?.id;
  if (flightKpiId) return flightKpiId;
  const kpi = card.dataset.kpi;
  return kpi ? `kpi-${kpi}` : card.classList.contains("flights-shell") ? "flights-shell" : undefined;
}

function selectedEntities(cardId?: string, tab = activeTab()): string | string[] {
  if (tab === "reading") return "INDUSTRY";
  if (tab === "market") return ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"];
  const selector = cardId ? CARD_SELECTION[cardId] :
    activeTab() === "reading" ? "reading" : activeTab() === "economy" ? "kpis" : activeTab() === "market" ? "market" : "flight-kpis";
  if (selector) {
    const picked = selection(selector);
    if (picked.length) return SINGLE_SELECTIONS.has(selector) ? picked[0]! : picked;
  }
  if (selector === "flight-kpis") {
    const picked = selection("flight-kpis");
    if (picked.length) return picked[0]!;
  }
  if (selector === "mix" || selector === "map") {
    const picked = selection(selector);
    if (picked.length) return picked;
  }
  if (cardId?.startsWith("flight-") || cardId === "flights-shell" || activeTab() === "flights") return flightState.mapEntity;
  return "AEROMEXICO";
}

export function buildChatContext(cardElement?: Element | null): ChatContext {
  const visualTab = activeTab();
  const focusedCard = cardElement ?? document.activeElement;
  const cardTab = tabForCard(focusedCard);
  const cardId = cardTab && cardTab !== visualTab ? undefined : cardIdFrom(focusedCard);
  // Resolve the map by its card, including inside the merged Mercado tab.
  // AFAC city totals have no airline attribution. Never inherit the market chart's three entities.
  const officialMapCard = cardId === "route-flow-map" || cardId === "flow-map";
  if (officialMapCard || (!cardId && !focusedCard?.closest("[data-chat-unavailable]") && (visualTab === "flights" || visualTab === "market"))) {
    const us = officialState.scope === "us";
    return { tab: "market", ...(officialMapCard ? { card_id: cardId } : {}), period: currentPeriodId() ?? officialState.period,
      ...(us ? { entity: [...officialState.carriers] } : {}),
      filters: { map_scope: officialState.scope,
        ...(officialState.scope === "international" && officialState.region ? { map_region: officialState.region } : {}),
        ...(us ? { map_carriers: [...officialState.carriers] } : {}),
        ...(officialState.document ? { map_dataset_version: officialState.document.dataset_version } : {}),
        map_grain: us ? "airport_pair" : "city_pair", map_months: [...(officialState.network?.observed_months ?? [])] } };
  }
  // The merged Mercado tab preserves the existing data contracts: map and
  // financial flight cards are `flights`; the AFAC participation chart is `market`.
  const tab = cardId === "market-card" || cardId === "market-chart" ? "market" : visualTab;
  const newsCompany = document.querySelector<HTMLSelectElement>("#news-company")?.value;
  const newsEntities: Record<string,string> = { "Aeroméxico":"AEROMEXICO", "Volaris":"VOLARIS", "Viva":"VIVA_AEROBUS" };
  const newsMonth = document.querySelector<HTMLSelectElement>("#news-month")?.value;
  const period = tab === "flights"
    ? currentPeriodId() ?? flightState.quarters[flightState.periodIndex]?.period_id ?? ""
    : tab === "news" ? newsMonth?.replace("-","M") || "" : currentPeriodId() ?? "";
  const picked = tab === "news" ? newsCompany ? newsEntities[newsCompany] : "INDUSTRY" : selectedEntities(cardId, tab);
  const context: ChatContext = { tab, period, ...(picked !== undefined ? {entity:picked} : {}) };
  if (cardId) context.card_id = cardId;
  const filters: NonNullable<ChatContext["filters"]> = {};
  if (tab === "market" || cardId === "market-card" || cardId === "market-chart") {
    const segment = document.querySelector<HTMLSelectElement>("#market-segment")?.value;
    if (segment === "total" || segment === "domestic" || segment === "international") filters.segment = segment;
    if (Array.isArray(picked)) filters.entities = picked as NonNullable<ChatContext["filters"]>["entities"];
  }
  if (tab === "flights") {
    filters.network_mode = flightState.networkMode;
    const modelMonth = (month: string) => /^(\d{4})-(\d{2})$/.test(month) ? month.replace("-", "M") : month;
    if (flightState.networkMode === "domestic") filters.domestic_months = [...flightState.selectedDomesticMonths].sort().map(modelMonth);
    if (flightState.selectedRegion) filters.region = flightState.selectedRegion;
    if ((!cardId || cardId === "route-flow-map" || cardId === "flow-map") && flightState.networkMode === "international" &&
        (!flightState.selectedRegion || flightState.selectedRegion === "norteamerica") && flightState.evidenceView === "north_america_observed") {
      filters.flight_evidence = "north_america_observed";
    }
    if (cardId === "route-flow-map" || cardId === "flow-map") {
      const entities = selection("map"); if (entities.length) filters.entities = entities;
    }
    if (cardId === "mix-chart") {
      const entities = selection("mix"); if (entities.length) filters.entities = entities;
      const quarter = period.match(/^(\d{4})Q([1-4])$/);
      if (flightState.passengerPeriod === "month" && quarter) {
        filters.start = modelMonth(`${quarter[1]}-${String((Number(quarter[2]) - 1) * 3 + 1).padStart(2, "0")}`);
        filters.end = modelMonth(`${quarter[1]}-${String(Number(quarter[2]) * 3).padStart(2, "0")}`);
      }
    }
  }
  if (cardId === "unit-chart") {
    const range = document.querySelector<HTMLSelectElement>("#unit-range")?.value;
    if (range === "all" || range === "12" || range === "8" || range === "4") filters.range = range;
    const entities = selection("unit"); if (entities.length) filters.entities = entities;
  } else if (cardId === "volume-chart") {
    const entities = selection("volume"); if (entities.length) filters.entities = entities;
  } else if (cardId === "load-chart") {
    const entities = selection("load"); if (entities.length) filters.entities = entities;
  }
  if (Object.keys(filters).length) context.filters = filters;
  return context;
}

export function isEntityKeyList(value: unknown): value is EntityKey[] {
  return Array.isArray(value) && value.every((item) => ["INDUSTRY", "AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"].includes(String(item)));
}

export function describeChatContext(context: ChatContext): string {
  const tabLabels = { reading: "Lectura ejecutiva", economy: "Economía unitaria", flights: "Mercado", market: "Mercado", news: "Noticias" };
  const cardLabels: Record<string, string> = {
    "market-chart": "Participación de pasajeros", "market-card": "Participación de pasajeros",
    "unit-chart": "Economía unitaria", "volume-chart": "Pasajeros y RASK", "load-chart": "Ocupación y RASK",
    "route-flow-map": "Mapa de rutas", "flow-map": "Mapa de rutas", "mix-chart": "Mezcla por segmento",
  };
  const period = context.tab === "reading" && /^\d{4}Q[1-4]$/.test(context.period)
    ? `${context.period.slice(-1)}T${context.period.slice(2, 4)}`
    : executiveState.records.find((record) => record.period_id === context.period)?.period_label ??
    flightState.byPeriod.get(context.period)?.period_label ?? context.period;
  if (context.filters?.map_scope) {
    const f = context.filters;
    const mapPeriod = /^\d{4}Q[1-4]$/.test(context.period) ? `${context.period.slice(-1)}T${context.period.slice(2, 4)}` : period;
    const scope = MAP_SCOPES[f.map_scope!];
    const region = f.map_region ? ` · ${MAP_REGIONS[f.map_region]}` : "";
    const carriers = f.map_scope === "us" ? (f.map_carriers ?? []).map(key => MAP_CARRIER_LABELS[key]).join(", ") : "Todas las aerolíneas";
    return `Mapa de rutas · ${mapPeriod} · ${scope}${region} · ${carriers} · ${f.map_grain === "city_pair" ? "ciudades" : "aeropuertos"} · ${f.map_months?.length ?? 0}/3 meses`;
  }
  const entities = (Array.isArray(context.entity) ? context.entity : context.entity ? [context.entity] : []).map((entity) =>
    ["INDUSTRY", "AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"].includes(entity)
      ? entityLabel(entity as EntityKey)
      : entity
  ).join(", ") || "Sin aerolínea preseleccionada";
  const card = context.card_id ? cardLabels[context.card_id] : undefined;
  const evidence = context.filters?.flight_evidence === "north_america_observed" ? " · Norteamérica: sólo vuelos observados" : "";
  return `${tabLabels[context.tab]} · ${period || "periodo disponible"} · ${entities}${card ? ` · ${card}` : ""}${evidence}`;
}
