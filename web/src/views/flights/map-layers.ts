import type { PeriodNetworkDocument, RouteDirection } from "../../types/domain";
import { state } from "./state";
import { mapPeriodLabel } from "./map-periods";

export function calendarQuarter(period: string): string {
  return period.includes("Q") ? period : `${period.slice(0, 4)}Q${Math.floor((Number(period.slice(5)) - 1) / 3) + 1}`;
}

export function officialDomesticNetwork(period: string): PeriodNetworkDocument {
  const network = state.domesticNetworks.get(calendarQuarter(period));
  const empty = { mode: "scheduled_domestic", period_label: mapPeriodLabel(period), expected_months: [], observed_months: [], routes: [], airports: [] };
  if (!network) return empty;
  if (period.includes("Q")) return network;
  const routes = network.routes.flatMap((route) => {
    const monthly = (route.monthly ?? []).filter((item) => item.period_id === period && item.departures != null);
    if (!monthly.length) return [];
    const directions = new Map<string, RouteDirection>();
    for (const item of monthly) {
      const key = `${item.origin_iata}/${item.destination_iata}`;
      const known = directions.get(key) ?? { ...item, departures: 0 };
      known.departures = (known.departures ?? 0) + item.departures!;
      directions.set(key, known);
    }
    return [{ ...route, monthly, directions: [...directions.values()],
      departures: monthly.reduce((sum, item) => sum + item.departures!, 0),
      months_covered: 1, months_selected: 1,
      coverage_note: `${mapPeriodLabel(period)} · ${route.source_label ?? "fuente oficial"}` }];
  });
  const airports = new Set(routes.flatMap((route) => [route.origin.iata, route.destination.iata]));
  return { ...network, routes, airports: network.airports.filter((airport) => airports.has(airport.iata)),
    period_label: mapPeriodLabel(period), expected_months: [period], observed_months: routes.length ? [period] : [],
    coverage_by_source: Object.fromEntries(routes.map((route) => [route.source_label ?? "fuente oficial", [period]])) };
}
