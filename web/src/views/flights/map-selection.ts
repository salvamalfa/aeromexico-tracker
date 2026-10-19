import type { PeriodNetworkDocument, Route } from "../../types/domain";
import { finite } from "./dom";

export const MAP_CARRIERS = ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"] as const;
export function mapCarriers(key: string): string[] {
  return key === "INDUSTRY" ? [...MAP_CARRIERS] : [...new Set(key.split("+"))];
}

export function mergeCarrierNetworks(networks: PeriodNetworkDocument[]): PeriodNetworkDocument {
  if (!networks.length) throw new Error("No hay redes para la selección");
  const groups = new Map<string, Route[]>();
  for (const network of networks) for (const route of network.routes) {
    groups.set(route.market_key, [...groups.get(route.market_key) ?? [], route]);
  }
  const routes = [...groups].map(([market_key, parts]) => {
    const components = parts.flatMap((r) => r.flight_components ?? []);
    const seen = new Set<string>();
    for (const c of components) {
      const key = [c.carrier_key, c.origin_iata, c.destination_iata, c.period_id, c.kind === "scheduled"].join("|");
      if (seen.has(key)) throw new Error("Componente de vuelo duplicado entre aerolíneas");
      seen.add(key);
    }
    const counts = parts.map((r) => r.departures).filter(finite);
    const kinds = new Set(components.filter((c) => c.kind !== "scheduled").map((c) => c.kind));
    const partial = parts.some((r) => r.operation_status?.includes("partial_frequencies"));
    const estimatedOnly = parts.every((r) => r.operation_status?.startsWith("estimated_"));
    const directionKeys = [...new Set(parts.flatMap((r) => (r.directions ?? []).map((d) => `${d.origin_iata}|${d.destination_iata}`)))];
    return {
      ...parts[0]!, market_key, departures: counts.length ? counts.reduce((a, b) => a + b, 0) : null,
      flight_components: components,
      source_label: [...new Set(parts.map((r) => r.source_label).filter(Boolean))].join(" · "),
      operation_status: estimatedOnly || (kinds.size === 1 && kinds.has("estimated")) ? "estimated_from_retained_frequencies" + (partial ? "_partial_frequencies" : "")
        : kinds.size === 1 && kinds.has("observed") ? "operated_observed" : "mixed_observed_estimated_cells",
      previous: { ...parts[0]!.previous, departures: null },
      directions: directionKeys.map((key) => {
        const [origin_iata, destination_iata] = key.split("|") as [string, string];
        const values = parts.flatMap((r) => r.directions ?? []).filter((d) => d.origin_iata === origin_iata && d.destination_iata === destination_iata)
          .map((d) => d.departures).filter(finite);
        return { origin_iata, destination_iata, departures: values.length ? values.reduce((a, b) => a + b, 0) : null };
      }),
    } satisfies Route;
  });
  const sources = [...new Set(networks.flatMap((n) => Object.keys(n.coverage_by_source ?? {})))];
  return { ...networks[0]!, routes,
    airports: [...new Map(networks.flatMap((n) => n.airports).map((a) => [a.iata, a])).values()],
    coverage_by_source: Object.fromEntries(sources.map((s) => [s, [...new Set(networks.flatMap((n) => n.coverage_by_source?.[s] ?? []))].sort()])),
  };
}
