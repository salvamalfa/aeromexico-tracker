// Classification of the flights metric; seat or passenger estimates never
// turn an official flight count into an estimated one.
import type { Route } from "../../types/domain";
import { finite } from "./dom";

export type FlightKind = "observed" | "scheduled" | "estimated" | "attributed" | "mixed" | "missing";
export const FLIGHT_KIND_LABEL: Record<FlightKind, string> = {
  observed: "observados", scheduled: "programados", estimated: "estimados",
  attributed: "atribuidos", mixed: "observados + estimados", missing: "sin dato",
};

export function flightKind(route: Route): FlightKind {
  if (!finite(route.departures)) return "missing";
  if (route.flight_components?.length) {
    const active = route.flight_components.filter((c) => c.kind !== "scheduled");
    const kinds = new Set((active.length ? active : route.flight_components).map((c) => c.kind));
    if (kinds.size > 1) return "mixed";
    return [...kinds][0]!;
  }
  const status = route.operation_status ?? "";
  if (status === "assigned_slot_not_flown" || status.startsWith("scheduled_")) return "scheduled";
  if (status === "carrier_inferred_market_observed") return "attributed";
  if (status.startsWith("estimated_")) return "estimated";
  if (status.includes("observed") || (route.source_label ?? "").includes("T-100")) return "observed";
  if (route.capacity_estimated ||
      (route.source_label ?? "").toLowerCase().includes("aerodatabox")) return "estimated";
  return "observed";
}

export function flightSource(route: Route): string {
  if (flightKind(route) === "estimated" && (route.source_label ?? "").includes("AeroDataBox")) {
    return "AeroDataBox · frecuencias históricas estimadas";
  }
  return route.source_label ?? "Fuente no detallada";
}

// Components, rather than a market-wide status, drive sums and labels.
export function flightTotals(route: Route): Partial<Record<FlightKind, number>> {
  if (!route.flight_components?.length) return finite(route.departures) ? { [flightKind(route)]: route.departures } : {};
  const totals: Partial<Record<FlightKind, number>> = {};
  for (const component of route.flight_components) {
    totals[component.kind] = (totals[component.kind] ?? 0) + component.departures;
  }
  return totals;
}

export function flightBreakdown(route: Route): string {
  return Object.entries(flightTotals(route)).map(([kind, count]) =>
    `${new Intl.NumberFormat("es-MX", { maximumFractionDigits: 1 }).format(count)} ${FLIGHT_KIND_LABEL[kind as FlightKind]}`).join(" · ");
}
