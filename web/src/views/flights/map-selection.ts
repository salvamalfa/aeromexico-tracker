import type { PeriodNetworkDocument, Route } from "../../types/domain";
import { finite } from "./dom";

export const MAP_CARRIERS = ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"] as const;
export function mapCarriers(key: string): string[] {
  return key === "INDUSTRY" ? [...MAP_CARRIERS] : [...new Set(key.split("+"))];
}

type Movements = NonNullable<Route["recorded_movements"]>;
function mergeMovements(measures: Movements[], market: string): Movements | undefined {
  if (!measures.length) return undefined;
  const first = measures[0]!, components: Movements["components"] = [];
  const grains = new Set<string>(), evidence = new Set<string>();
  for (const measure of measures) {
    if (!measure.components.length || measure.provisional !== true ||
        measure.official_classification_confirmed !== false || measure.agent_eligible !== false ||
        measure.flight_type_code !== "S" || measure.traffic_code !== "I" ||
        measure.definition !== first.definition || measure.source_label !== first.source_label) {
      throw new Error("Movimientos de Aerocivil sin alcance y procedencia compatibles");
    }
    let subtotal = 0;
    for (const cell of measure.components) {
      if (!Number.isSafeInteger(cell.operations) || cell.operations < 0 ||
          !/^[a-f0-9]{64}$/.test(cell.source_hash) || !cell.source_locator ||
          [cell.origin_iata, cell.destination_iata].sort().join("<>") !== market) {
        throw new Error("Movimientos de Aerocivil sin conteo o procedencia válidos");
      }
      const grain = JSON.stringify([cell.operator_icao, cell.commercial_designator_as_reported,
        cell.origin_iata, cell.destination_iata, cell.period_id]);
      const original = JSON.stringify([cell.source_hash, cell.source_locator]);
      if (grains.has(grain) || evidence.has(original)) {
        throw new Error("Movimientos de Aerocivil duplicados o ediciones superpuestas entre aerolíneas");
      }
      grains.add(grain); evidence.add(original);
      components.push({ ...cell }); subtotal += cell.operations;
    }
    const months = [...new Set(measure.components.map((cell) => cell.period_id))].sort();
    if (!Number.isSafeInteger(subtotal) || subtotal !== measure.count ||
        JSON.stringify(months) !== JSON.stringify([...measure.observed_months].sort())) {
      throw new Error("Movimientos de Aerocivil no reconcilian con sus componentes y meses");
    }
  }
  const count = components.reduce((sum, cell) => sum + cell.operations, 0);
  if (!Number.isSafeInteger(count)) throw new Error("Total de movimientos fuera de precisión segura");
  components.sort((a, b) => {
    const key = (cell: Movements["components"][number]) => JSON.stringify([cell.operator_icao,
      cell.commercial_designator_as_reported, cell.origin_iata, cell.destination_iata, cell.period_id]);
    return key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0;
  });
  return { ...first, count, observed_months: [...new Set(components.map((cell) => cell.period_id))].sort(), components };
}

export function mergeCarrierNetworks(networks: PeriodNetworkDocument[]): PeriodNetworkDocument {
  if (!networks.length) throw new Error("No hay redes para la selección");
  const groups = new Map<string, Route[]>();
  for (const network of networks) for (const route of network.routes) {
    groups.set(route.market_key, [...groups.get(route.market_key) ?? [], route]);
  }
  const routes = [...groups].map(([market_key, parts]) => {
    const movements = parts.flatMap((r) => r.recorded_movements ? [r.recorded_movements] : []);
    const recordedMovements = mergeMovements(movements, market_key);
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
      ...(recordedMovements ? { recorded_movements: recordedMovements } : {}),
      source_label: [...new Set(parts.map((r) => r.source_label).filter(Boolean))].join(" · "),
      operation_status: !counts.length && recordedMovements ? "recorded_movements_provisional"
        : estimatedOnly || (kinds.size === 1 && kinds.has("estimated")) ? "estimated_from_retained_frequencies" + (partial ? "_partial_frequencies" : "")
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
