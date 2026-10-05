interface MetricDisplay {
  label: string;
  unit: string;
  scale: number;
  rounding: number;
}

const metrics: Record<string, MetricDisplay> = {
  company_passengers: { label: "Pasajeros reportados por compañía", unit: "pasajeros", scale: 1, rounding: 0 },
  afac_passengers: { label: "Pasajeros AFAC", unit: "pasajeros", scale: 1, rounding: 0 },
  afac_market_passengers: { label: "Pasajeros de todas las aerolíneas mexicanas AFAC", unit: "pasajeros", scale: 1, rounding: 0 },
  ask_km: { label: "ASK", unit: "mil millones de ASK-km", scale: 1e-9, rounding: 2 },
  load_factor: { label: "Factor de ocupación", unit: "%", scale: 100, rounding: 1 },
  rask_cents_per_km: { label: "RASK", unit: "¢ USD / ASK-km", scale: 1, rounding: 2 },
  cask_cents_per_km: { label: "CASK", unit: "¢ USD / ASK-km", scale: 1, rounding: 2 },
  unit_margin_cents_per_km: { label: "Margen unitario RASK−CASK", unit: "¢ USD / ASK-km", scale: 1, rounding: 2 },
  market_share: { label: "Participación de pasajeros AFAC", unit: "%", scale: 100, rounding: 1 },
  market_share_change_qoq_pp: { label: "Cambio de participación trimestral", unit: "pp", scale: 1, rounding: 1 },
  market_share_change_yoy_pp: { label: "Cambio interanual de participación", unit: "pp", scale: 1, rounding: 1 },
};

const entities: Record<string, string> = {
  AEROMEXICO: "Aeroméxico",
  AEROMEXICO_CONNECT: "Aeroméxico Connect",
  VOLARIS: "Volaris",
  VIVA_AEROBUS: "Viva",
  INDUSTRY: "Industria (tres compañías)",
  MEXICAN_CARRIERS: "Todas las aerolíneas mexicanas AFAC",
};
const entityLabels = new Map(Object.values(entities).map((label) => [label.toLocaleLowerCase("es"), label]));
const metricLabels = new Map(Object.values(metrics).map((metric) => [metric.label.toLocaleLowerCase("es"), metric]));

const statusCopy: Record<string, string> = {
  answered: "Se espera una respuesta con datos.",
  complete: "Se espera una respuesta con datos.",
  supported: "Se espera una respuesta con datos.",
  clarify: "Debe pedir una aclaración antes de dar una cifra.",
  clarification: "Debe pedir una aclaración antes de dar una cifra.",
  needs_clarification: "Debe pedir una aclaración antes de dar una cifra.",
  refused: "Debe rechazar de forma segura solicitudes sensibles o instrucciones que intenten cambiar sus límites.",
  refuse: "Debe rechazar de forma segura solicitudes sensibles o instrucciones que intenten cambiar sus límites.",
  unsupported: "Debe explicar que la solicitud está fuera del alcance o rechazarla.",
  rejected: "Debe explicar que la solicitud está fuera del alcance o rechazarla.",
  out_of_scope: "Debe explicar que la solicitud está fuera del alcance o rechazarla.",
};

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function firstString(row: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) if (typeof row[key] === "string") return row[key] as string;
  return null;
}

function formatValue(value: unknown, metric: MetricDisplay): string {
  if (value === null || value === undefined) return "No disponible (N/D)";
  if (typeof value !== "number" || !Number.isFinite(value)) return "Valor no numérico; consulta el detalle.";
  const scaled = value * metric.scale;
  const number = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: metric.rounding,
    maximumFractionDigits: metric.rounding,
  }).format(scaled);
  return `${number} ${metric.unit}`;
}

function rowSummary(row: unknown, index: number): HTMLElement {
  const item = document.createElement("li");
  const data = record(row);
  if (!data) {
    item.textContent = `Fila ${index + 1}: consulta el detalle de evaluación.`;
    return item;
  }
  const metricId = firstString(data, ["metric", "metric_id", "metricId", "metric_label", "metricLabel", "id"]);
  const metric = metricId ? metrics[metricId] ?? metricLabels.get(metricId.toLocaleLowerCase("es")) : undefined;
  const entityId = firstString(data, ["entity", "entity_id", "entityId", "entity_label", "entityLabel"]);
  const entity = entityId
    ? entities[entityId] ?? entityLabels.get(entityId.toLocaleLowerCase("es"))
    : undefined;
  const period = firstString(data, ["period", "period_id", "periodId"]);
  const metricName = metric?.label ?? "Métrica sin etiqueta del catálogo";
  const entityName = entity ?? "Entidad sin etiqueta del catálogo";
  const value = formatValue(data.value, metric ?? { label: "", unit: "", scale: 1, rounding: 2 });
  item.textContent = `${metricName} · ${entityName}${period ? ` · ${period}` : ""}: ${value}`;
  return item;
}

export function renderExpectedSummary(host: HTMLElement, expected: unknown): void {
  host.replaceChildren();
  const data = record(expected);
  if (!data) {
    host.textContent = "La referencia no contiene una tabla numérica. Consulta el detalle de evaluación.";
    return;
  }
  const status = firstString(data, ["status", "disposition", "outcome"]);
  const guidance = status ? statusCopy[status.toLowerCase()] : undefined;
  if (guidance) {
    const note = document.createElement("p");
    note.className = "expected-guidance";
    note.textContent = guidance;
    host.append(note);
  }
  if (!Array.isArray(data.rows) || data.rows.length === 0) {
    if (!guidance) host.textContent = "La referencia no contiene filas publicadas. Consulta el detalle de evaluación.";
    return;
  }
  const rows = document.createElement("ul");
  rows.className = "expected-rows";
  data.rows.forEach((row, index) => rows.append(rowSummary(row, index)));
  host.append(rows);
}
