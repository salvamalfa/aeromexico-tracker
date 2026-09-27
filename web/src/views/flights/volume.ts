// One concise, source-specific network total above the route ranking.

import { $, esc, finite, integer } from "./dom";
import { monthsInQuarter, state } from "./state";
import { SCHEDULED_STATUSES } from "./coverage";
import type { Route } from "../../types/domain";

export function renderNetworkVolume(): void {
  const host = $("network-volume");
  if (!host) return;
  const routes: Route[] = state.routes || [];
  host.hidden = routes.length === 0 && state.presenceOnlyRouteCount === 0;
  if (host.hidden) {
    host.innerHTML = "";
    return;
  }

  const periodId = state.quarters[state.periodIndex]?.period_id ?? "";
  const period = state.quarters[state.periodIndex]?.period_label || state.network?.period_label || "";
  if (state.network?.mode === "estimated_domestic") {
    const passengers = routes.reduce((sum, route) => sum + (finite(route.passengers) ? route.passengers : 0), 0);
    const months = monthsInQuarter(periodId).length;
    const coverage = months > 0 && months < 3 ? ` · ${months}/3 meses` : "";
    host.innerHTML = `<div class="network-volume-main"><small>Total pasajeros</small><div class="network-volume-inline"><strong>${routes.length ? integer.format(passengers) : "N/D"}</strong><span>estimados · ${esc(period)}${coverage}</span></div></div>`;
    return;
  }

  // Keep observed Aerovías flights distinct from estimated, inferred and
  // scheduled operations. Route evidence remains labeled in the ranking.
  const observed = routes.filter((route) =>
    finite(route.departures) && !route.passengers_estimated &&
    !SCHEDULED_STATUSES.includes(route.operation_status ?? "") &&
    route.operation_status !== "carrier_inferred_market_observed"
  );
  const flights = observed.reduce((sum, route) => sum + (route.departures ?? 0), 0);
  host.innerHTML = `<div class="network-volume-main"><small>Total vuelos</small><div class="network-volume-inline"><strong>${observed.length ? integer.format(flights) : "N/D"}</strong><span>observados · ${esc(period)}</span></div></div>`;
}
