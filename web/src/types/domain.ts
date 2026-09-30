// Hand-written domain types for the shapes web/src/views/** works with in
// memory (fetched JSON plus derived/aggregated structures such as the
// domestic multi-month aggregate built by views/flights/domestic.ts).
// The raw per-file JSON shapes are also covered, more strictly, by the
// generated types in web/src/types/generated/ (from contracts/web/*.schema.json);
// these hand-written types describe the superset actually touched by the
// view code, including fields the schema calls optional/estimated.
//
// Deliberately permissive (many optional fields, dynamic-key helpers cast
// through `AnyRecord`) rather than a line-by-line mirror of the schema:
// the views read a JSON payload of unknown exact shape at runtime, and the
// contract test in gen-types.test.ts is what actually guards the schema
// boundary.

export type AnyRecord = Record<string, unknown>;

export interface Airport {
  iata: string;
  city: string;
  name?: string;
  lat: number;
  lon: number;
}

export interface RouteDirection {
  origin_iata: string;
  destination_iata: string;
  departures?: number | null;
  passengers?: number | null;
  passengers_low?: number | null;
  passengers_high?: number | null;
  seats?: number | null;
  load_factor?: number | null;
  capacity_estimated?: boolean;
  period_id?: string;
  support_observed_in_period?: boolean;
  support_source_periods?: string;
}

export interface Route {
  market_key: string;
  origin: Airport;
  destination: Airport;
  // Industria only: passengers of each airline on this route.
  carrier_breakdown?: Record<string, number>;
  passengers?: number | null;
  passengers_low?: number | null;
  passengers_high?: number | null;
  passengers_estimated?: boolean;
  seats?: number | null;
  seats_low?: number | null;
  seats_high?: number | null;
  departures?: number | null;
  capacity_estimated?: boolean;
  load_factor?: number | null;
  load_factor_low?: number | null;
  load_factor_high?: number | null;
  load_factor_status?: string;
  months_covered?: number | null;
  months_selected?: number | null;
  capacity_months_covered?: number;
  support_repair_applied?: boolean;
  source_label?: string;
  coverage_note?: string;
  operation_status?: string;
  monthly?: RouteDirection[];
  previous?: {
    passengers?: number | null;
    seats?: number | null;
    departures?: number | null;
  };
  directions?: RouteDirection[];
}

export interface Network {
  mode?: string;
  period_label?: string;
  routes: Route[];
  airports: Airport[];
  world_geometry?: WorldGeometry;
  expected_months?: string[];
  observed_months?: string[];
  agent_eligible?: boolean;
}

export interface WorldGeometry {
  geojson: {
    type: string;
    features: Array<{ id: string; [key: string]: unknown }>;
  };
  /** Pinned Natural Earth topology Plotly uses for the base map (no CDN fetch). */
  topojson?: object;
}

export interface MetricValue {
  value: number | null;
}

export interface QuarterRecord {
  period_id: string;
  period_label: string;
  metrics: {
    passengers: MetricValue & { period_start: string; period_end: string };
    asm_miles: MetricValue;
    rpm_miles: MetricValue;
    load_factor: MetricValue;
    [key: string]: unknown;
  };
}

export interface EntityPeriods {
  label: string;
  domestic_monthly: string[];
  international: string[];
}

export interface AvailablePeriods {
  domestic: string[];
  domestic_monthly: string[];
  international: string[];
  // Dashboard v2 (fase 3): Industria/Volaris/Viva map files.
  entities?: Record<string, EntityPeriods>;
}

export interface FlightsMetadata {
  title: string;
  pilot_period: string;
  default_period: string;
  cutoff_date: string;
  approved_evidence_fingerprint: string;
  review_status: string;
  scope: string;
}

export interface MonthlyPassengerPoint {
  date: string;
  domestic: number;
  international: number;
  total_segment_sum: number;
}

export interface MonthlyPassengerSeries {
  records: MonthlyPassengerPoint[];
}

export interface QuartersDocument {
  metadata: FlightsMetadata;
  quarters: QuarterRecord[];
  monthly_passengers: MonthlyPassengerSeries;
  route_network: { world_geometry: WorldGeometry };
  available_periods: AvailablePeriods;
}

export interface PeriodNetworkDocument {
  mode: string;
  period_label: string;
  routes: Route[];
  airports: Airport[];
  expected_months?: string[];
  observed_months?: string[];
  agent_eligible?: boolean;
}

// -- Executive / economy payload -------------------------------------

export interface Comparison {
  available: boolean;
  display: string;
  direction: "up" | "down" | "na" | string;
}

export interface Kpi {
  key: string;
  label: string;
  display_value: string;
  qoq: Comparison;
  yoy: Comparison;
  vs_industry?: Comparison;
}

export interface ExecutiveRecord {
  period_id: string;
  period_label: string;
  rask_cents_per_km: number;
  cask_cents_per_km: number;
  unit_margin_cents_per_km: number;
  ask_km: number;
  load_factor_reported: number;
  passengers: number;
  [key: string]: unknown;
}

export interface ExecutiveView {
  period_id: string;
  period_label: string;
  kpis: Kpi[];
  margin_qoq: Comparison;
  margin_yoy: Comparison;
  margin_vs_industry?: Comparison;
}

export interface ExecutiveMetadata {
  default_period: string;
  [key: string]: unknown;
}

export interface EntityMeta {
  key: string;
  label: string;
  is_aggregate: boolean;
  carriers: string[];
  note: string;
}

export interface EntityRecord extends ExecutiveRecord {
  load_factor: number;
  load_factor_basis: "reported" | "calculated";
  cask_ex_fuel_cents_per_km: number | null;
  rpk_km: number | null;
}

export interface EntityBlock {
  key: string;
  label: string;
  note: string;
  first_period: string;
  last_period: string;
  quarter_count: number;
  records: EntityRecord[];
  views: Record<string, ExecutiveView>;
}

export interface ExecutiveDocument {
  metadata: ExecutiveMetadata;
  records: ExecutiveRecord[];
  views: Record<string, ExecutiveView>;
  entities?: Record<string, EntityBlock>;
  entity_list?: EntityMeta[];
}

// -- Market (market.json, src/dashboard/market.py) --------------------

export interface MarketShare {
  passengers: number | null;
  share: number | null;
  share_change_qoq_pp?: number | null;
  share_change_yoy_pp?: number | null;
}

export interface MarketSegment {
  mexican_carriers_passengers: number;
  carriers: Record<string, MarketShare>;
  industry: MarketShare;
}

export type MarketSegmentKey = "total" | "domestic" | "international";

export interface MarketPeriod {
  period_id: string;
  period_label: string;
  segments: Record<MarketSegmentKey, MarketSegment>;
}

export interface MarketDocument {
  schema_version: string;
  metadata: {
    first_period: string;
    last_period: string;
    default_quarter: string;
    industry_note: string;
    industry_share_latest: number | null;
    method_note: string;
    [key: string]: unknown;
  };
  carriers: string[];
  months: MarketPeriod[];
  quarters: MarketPeriod[];
}

export interface AnalysisCitation {
  label: string;
  href: string;
  title: string;
  value: string;
}

export interface AnalysisSummaryItem {
  claim_id: string;
  text: string;
  lead?: string | null;
  emphasis?: string[];
}

export interface AnalysisSection {
  title: string;
  paragraphs: string[];
  claim_ids: string[];
}

export interface AnalysisClaim {
  claim_id: string;
  citations: AnalysisCitation[];
}

export interface AnalysisDocument {
  period_id: string;
  thesis: string;
  summary_items: AnalysisSummaryItem[];
  context: string[];
  sections: AnalysisSection[];
  claims: AnalysisClaim[];
}
