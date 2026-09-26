// Mutable view state + lazy fetch/cache for per-period network files.
//
// The integrated page embeds every period's network in one JSON blob; this
// standalone page instead loads flights/quarters.json first (metadata,
// quarters, monthly_passengers, world geometry, and the
// `available_periods` manifest added for this front-end — see
// src/web_export/flights.py) and fetches each domestic/international
// period file only when it is actually shown.

export const DOMESTIC_MONTH_NAMES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
export const ESTIMATE_INFO_TITLE = "Estimación AFAC + AeroDataBox; conserva rango de sensibilidad";
export const DEFAULT_AIRPORT = "MEX";

export const state = {
  dataRoot: "public/data/v1",
  metadata: null,
  quarters: [],
  byPeriod: new Map(),
  monthlyPassengers: null,
  worldGeometry: null,
  availablePeriods: { domestic: [], domestic_monthly: [], international: [] },

  periodIndex: 0,
  importance: "passengers",
  selectedDomesticMonths: new Set(),
  domesticMonthsQuarterId: null,
  networkMode: "domestic",
  passengerPeriod: "quarter",
  selectedMarket: null,
  selectedRegion: null,
  pinnedAirport: null,
  hoveredAirport: null,
  hoveredAirportAt: 0,
  flowMapRendered: false,
  selectAirportFromSearch: null,

  // network / routes currently on screen (recomputed by renderNetworkPeriod).
  network: null,
  routes: [],

  // period_id -> network JSON, filled in on demand by ensure*().
  domesticNetworks: new Map(),
  domesticMonthlyNetworks: new Map(),
  internationalNetworks: new Map(),
};

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`No se pudo cargar ${path} (HTTP ${response.status})`);
  return response.json();
}

export function initState(quartersDoc) {
  state.metadata = quartersDoc.metadata;
  state.quarters = quartersDoc.quarters;
  state.byPeriod = new Map(state.quarters.map((item) => [item.period_id, item]));
  state.monthlyPassengers = quartersDoc.monthly_passengers;
  state.worldGeometry = quartersDoc.route_network.world_geometry;
  state.availablePeriods = quartersDoc.available_periods;
  state.periodIndex = Math.max(0, state.quarters.findIndex((item) => item.period_id === state.metadata.default_period));
  const startQuarter = state.quarters[state.periodIndex].period_id;
  state.selectedDomesticMonths = new Set(monthsInQuarter(startQuarter));
  state.domesticMonthsQuarterId = startQuarter;
  state.networkMode = domesticAvailableForQuarter(startQuarter) ? "domestic" : "international";
}

// Meses nacionales que le pertenecen por calendario a un trimestre dado
// (ver flights.js::monthsInQuarter). Solo depende del manifiesto, nunca
// hace falta esperar un fetch para saberlo.
export function monthsInQuarter(quarterId) {
  return state.availablePeriods.domestic_monthly.filter((periodId) =>
    `${periodId.slice(0, 4)}Q${Math.floor((Number(periodId.slice(5, 7)) - 1) / 3) + 1}` === quarterId
  );
}

export function domesticAvailableForQuarter(quarterId) {
  return monthsInQuarter(quarterId).length > 0 || state.availablePeriods.domestic.includes(quarterId);
}

export async function ensureDomesticMonths(monthIds) {
  await Promise.all(monthIds.map(async (id) => {
    if (state.domesticMonthlyNetworks.has(id)) return;
    state.domesticMonthlyNetworks.set(id, await fetchJson(`${state.dataRoot}/flights/domestic/${id}.json`));
  }));
}

export async function ensureDomesticQuarter(periodId) {
  if (state.domesticNetworks.has(periodId)) return;
  if (!state.availablePeriods.domestic.includes(periodId)) return;
  state.domesticNetworks.set(periodId, await fetchJson(`${state.dataRoot}/flights/domestic/${periodId}.json`));
}

export async function ensureInternational(periodId) {
  if (state.internationalNetworks.has(periodId)) return;
  if (!state.availablePeriods.international.includes(periodId)) return;
  state.internationalNetworks.set(periodId, await fetchJson(`${state.dataRoot}/flights/international/${periodId}.json`));
}

export async function loadQuarters(dataRoot) {
  if (dataRoot) state.dataRoot = dataRoot;
  const quartersDoc = await fetchJson(`${state.dataRoot}/flights/quarters.json`);
  initState(quartersDoc);
}
