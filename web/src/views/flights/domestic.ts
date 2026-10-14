// National month-to-quarter aggregation.
// Ported from src/dashboard/assets/flights.js.

import { finite } from "./dom";
import { DOMESTIC_MONTH_NAMES, monthsInQuarter, state } from "./state";
import type { Airport, PeriodNetworkDocument, Route } from "../../types/domain";

// Describe el periodo nacional mostrado, p. ej. "abril–junio 2026 ·
// 3 meses seleccionados" o, si el trimestre solo tiene datos para parte de
// sus meses de calendario, agrega "· cobertura parcial: 2 de 3 meses".
export function domesticPeriodLabel(monthIds: string[], quarterId: string | null): string {
  const sorted = [...monthIds].sort();
  const n = sorted.length;
  const monthName = (id: string) => DOMESTIC_MONTH_NAMES[Number(id.slice(5, 7)) - 1];
  let base: string;
  if (n === 0) base = "Sin meses con datos";
  else if (n === 1) base = `${monthName(sorted[0]!)} ${sorted[0]!.slice(0, 4)}`;
  else base = `${monthName(sorted[0]!)}–${monthName(sorted[n - 1]!)} ${sorted[0]!.slice(0, 4)}`;
  const noun = n === 1 ? "mes seleccionado" : "meses seleccionados";
  let label = `${base} · ${n} ${noun}`;
  const available = monthsInQuarter(quarterId).length;
  if (available > 0 && available < 3) label += ` · cobertura parcial: ${available} de 3 meses`;
  return label;
}

// Official scheduling months are aggregated independently from performed flights.
// A missing metric stays N/D; it is never supplied by a historical seed.
export function aggregateDomesticMonths(monthIds: string[]): PeriodNetworkDocument | null {
  const sorted = [...monthIds].sort();
  const networks = sorted.map((id) => state.domesticMonthlyNetworks.get(id));
  if (!networks.length || networks.some((network) => !network)) return null;
  const markets = new Set(networks.flatMap((network) => network!.routes.map((route) => route.market_key)));
  const routes: Route[] = [];
  const airports = new Map<string, Airport>();
  for (const market of markets) {
    const parts = networks.map((network) => network!.routes.find((route) => route.market_key === market));
    const base = parts.find((route) => route)!;
    const sum = (key: "passengers" | "seats" | "departures"): number | null =>
      parts.every((route) => route && finite(route[key]))
        ? parts.reduce((total, route) => total + route![key]!, 0) : null;
    const route: Route = {
      ...base, passengers: sum("passengers"), seats: sum("seats"), departures: sum("departures"),
      load_factor: null, previous: { passengers: null, seats: null, departures: null },
      months_covered: parts.filter(Boolean).length, months_selected: 3,
      coverage_note: "Meses programados: " + sorted.map((id) => id.slice(5)).join(", ") +
        " · AICM · ejecución sin verificar",
      directions: [], monthly: [],
    };
    routes.push(route);
    for (const airport of [route.origin, route.destination]) airports.set(airport.iata, airport);
  }
  return {
    mode: "scheduled_domestic", period_label: domesticPeriodLabel(sorted, state.domesticMonthsQuarterId),
    expected_months: sorted, observed_months: [], availability: "partial", routes,
    airports: [...airports.values()], agent_eligible: false,
    eligibility_reason: "Programación AICM; ejecución sin verificar y cobertura nacional parcial.",
  };
}
