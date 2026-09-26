// National multi-month aggregation and the month multi-select switch.
// Ported from src/dashboard/assets/flights.js.

import { $, esc, finite } from "./dom.js";
import { DOMESTIC_MONTH_NAMES, monthsInQuarter, state } from "./state.js";
import { renderNetworkPeriod } from "./network.js";

// Describe el periodo nacional mostrado, p. ej. "abril–junio 2026 ·
// 3 meses seleccionados" o, si el trimestre solo tiene datos para parte de
// sus meses de calendario, agrega "· cobertura parcial: 2 de 3 meses".
export function domesticPeriodLabel(monthIds, quarterId) {
  const sorted = [...monthIds].sort();
  const n = sorted.length;
  const monthName = (id) => DOMESTIC_MONTH_NAMES[Number(id.slice(5, 7)) - 1];
  let base;
  if (n === 0) base = "Sin meses con datos";
  else if (n === 1) base = `${monthName(sorted[0])} ${sorted[0].slice(0, 4)}`;
  else base = `${monthName(sorted[0])}–${monthName(sorted[n - 1])} ${sorted[0].slice(0, 4)}`;
  const noun = n === 1 ? "mes seleccionado" : "meses seleccionados";
  let label = `${base} · ${n} ${noun}`;
  const available = monthsInQuarter(quarterId).length;
  if (available > 0 && available < 3) label += ` · cobertura parcial: ${available} de 3 meses`;
  return label;
}

// Combina los meses nacionales seleccionados en un agregado de Grupo
// Aeroméxico: pasajeros, vuelos y asientos suman; la ocupación se calcula
// con los totales (nunca promediando porcentajes mensuales); una ruta sin
// datos en alguno de los meses conserva los que sí tiene sin rellenar con
// cero, y su ocupación solo se muestra cuando la cobertura de pasajeros y
// de capacidad coincide exactamente en los mismos meses.
export function aggregateDomesticMonths(monthIds) {
  const sorted = [...monthIds].sort();
  const monthNetworks = sorted.map((id) => state.domesticMonthlyNetworks.get(id)).filter(Boolean);
  if (!monthNetworks.length) return null;
  // El punto de cobertura por ruta siempre se mide contra los meses de
  // calendario del trimestre completo (igual que en Internacional), no
  // contra la selección manual actual: así no cambia de color solo
  // porque el usuario deselecciona un mes.
  const quarterMonths = monthsInQuarter(state.domesticMonthsQuarterId);
  const quarterCoverage = new Map();
  for (const monthId of quarterMonths) {
    const monthNetwork = state.domesticMonthlyNetworks.get(monthId);
    if (!monthNetwork) continue;
    for (const route of monthNetwork.routes || []) {
      if (!finite(route.passengers)) continue;
      quarterCoverage.set(route.market_key, (quarterCoverage.get(route.market_key) || 0) + 1);
    }
  }
  const byMarket = new Map();
  const airportsByIata = new Map();
  for (const monthNetwork of monthNetworks) {
    for (const airport of monthNetwork.airports || []) airportsByIata.set(airport.iata, airport);
    for (const route of monthNetwork.routes || []) {
      if (!finite(route.passengers)) continue;
      let agg = byMarket.get(route.market_key);
      if (!agg) {
        agg = {
          market_key: route.market_key, origin: route.origin, destination: route.destination,
          passengers: 0, passengers_low: 0, passengers_high: 0, monthsCovered: 0,
          seats: 0, departures: 0, capacityMonthsCovered: 0,
          source_label: route.source_label, monthly: [], repaired: false,
        };
        byMarket.set(route.market_key, agg);
      }
      agg.passengers += route.passengers;
      agg.passengers_low += finite(route.passengers_low) ? route.passengers_low : route.passengers;
      agg.passengers_high += finite(route.passengers_high) ? route.passengers_high : route.passengers;
      agg.monthsCovered += 1;
      agg.repaired = agg.repaired || Boolean(route.support_repair_applied);
      if (route.capacity_estimated && finite(route.seats) && finite(route.departures)) {
        agg.seats += route.seats;
        agg.departures += route.departures;
        agg.capacityMonthsCovered += 1;
      }
      agg.monthly.push(...(route.monthly || []));
    }
  }
  const routes = [...byMarket.values()].map((agg) => {
    const capacityComplete = agg.capacityMonthsCovered > 0 && agg.capacityMonthsCovered === agg.monthsCovered;
    const loadFactor = capacityComplete && agg.seats > 0 ? agg.passengers / agg.seats : null;
    const plausible = finite(loadFactor) && loadFactor <= 1;
    agg.monthly.sort((a, b) => a.period_id.localeCompare(b.period_id) || a.origin_iata.localeCompare(b.origin_iata));
    return {
      market_key: agg.market_key, origin: agg.origin, destination: agg.destination,
      passengers: agg.passengers, passengers_low: agg.passengers_low, passengers_high: agg.passengers_high,
      passengers_estimated: true,
      seats: capacityComplete ? agg.seats : null,
      departures: capacityComplete ? agg.departures : null,
      capacity_estimated: capacityComplete,
      load_factor: plausible ? loadFactor : null,
      load_factor_status: !capacityComplete ? "capacity_incomplete" : (plausible ? "estimated" : "inconsistent_inputs"),
      months_covered: quarterCoverage.get(agg.market_key) || 0, months_selected: quarterMonths.length,
      capacity_months_covered: agg.capacityMonthsCovered,
      support_repair_applied: agg.repaired,
      source_label: agg.source_label,
      monthly: agg.monthly,
      previous: { passengers: null, seats: null, departures: null },
      directions: [],
    };
  }).sort((a, b) => b.passengers - a.passengers || a.market_key.localeCompare(b.market_key));
  return {
    mode: "estimated_domestic",
    period_label: domesticPeriodLabel(sorted, state.domesticMonthsQuarterId),
    expected_months: sorted,
    observed_months: sorted,
    routes,
    airports: [...airportsByIata.values()].sort((a, b) => a.iata.localeCompare(b.iata)),
    agent_eligible: false,
  };
}

export function renderMonthSwitch() {
  const host = $("network-month-switch");
  if (!host) return;
  const monthsHere = monthsInQuarter(state.domesticMonthsQuarterId);
  host.hidden = state.networkMode !== "domestic" || monthsHere.length === 0;
  if (host.hidden) { host.innerHTML = ""; return; }
  host.innerHTML = monthsHere.map((periodId) => {
    const label = state.domesticMonthlyNetworks.get(periodId)?.period_label || periodId;
    return `<button type="button" data-domestic-month="${esc(periodId)}" aria-pressed="${String(state.selectedDomesticMonths.has(periodId))}">${esc(label)}</button>`;
  }).join("");
  host.querySelectorAll("button").forEach((button) => button.addEventListener("click", async () => {
    const id = button.dataset.domesticMonth;
    if (state.selectedDomesticMonths.has(id)) {
      if (state.selectedDomesticMonths.size === 1) return; // conserva al menos un mes seleccionado
      state.selectedDomesticMonths.delete(id);
    } else {
      state.selectedDomesticMonths.add(id);
    }
    await renderNetworkPeriod(state.quarters[state.periodIndex].period_id);
  }));
}
