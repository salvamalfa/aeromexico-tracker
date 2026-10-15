// Classification of the flights metric; seat or passenger estimates never
// turn an official flight count into an estimated one.
import type { Route } from "../../types/domain";
import { finite } from "./dom";

export type FlightKind = "observed" | "scheduled" | "estimated" | "attributed" | "missing";
export const FLIGHT_KIND_LABEL: Record<FlightKind, string> = {
  observed: "observados", scheduled: "programados", estimated: "estimados",
  attributed: "atribuidos", missing: "sin dato",
};

export function flightKind(route: Route): FlightKind {
  if (!finite(route.departures)) return "missing";
  const status = route.operation_status ?? "";
  if (status === "assigned_slot_not_flown" || status.startsWith("scheduled_")) return "scheduled";
  if (status === "carrier_inferred_market_observed") return "attributed";
  if (status.includes("observed") || (route.source_label ?? "").includes("T-100")) return "observed";
  if (status.startsWith("estimated_") || route.capacity_estimated ||
      (route.source_label ?? "").toLowerCase().includes("aerodatabox")) return "estimated";
  return "observed";
}

export function flightSource(route: Route): string {
  if (flightKind(route) === "estimated" && (route.source_label ?? "").includes("AeroDataBox")) {
    return "AeroDataBox · frecuencias históricas estimadas";
  }
  return route.source_label ?? "Fuente no detallada";
}
