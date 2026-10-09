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
  multi_turn: "Evalúa la conversación completa: conserva los datos y atiende cada nueva petición.",
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

function labels(values: unknown, catalog: Record<string, string>, fallback: string): string[] {
  if (!Array.isArray(values)) return [];
  return values.flatMap((value) => {
    if (typeof value !== "string") return [];
    const label = catalog[value];
    return label ? [label] : [fallback];
  });
}

function planSummary(data: Record<string, unknown>): HTMLElement | null {
  const plan = record(data.plan);
  if (!plan) return null;
  const metricNames = labels(plan.metric_ids, Object.fromEntries(Object.entries(metrics).map(([key, value]) => [key, value.label])), "Métrica de referencia");
  const entityNames = labels(plan.entity_ids, entities, "Entidad de referencia");
  const periods = Array.isArray(plan.periods)
    ? plan.periods.filter((value): value is string => typeof value === "string")
    : [];
  const details = [
    metricNames.length ? `Indicador: ${[...new Set(metricNames)].join(", ")}` : "",
    entityNames.length ? `Grupo: ${[...new Set(entityNames)].join(", ")}` : "",
    periods.length ? `Periodo: ${[...new Set(periods)].join(", ")}` : "",
  ].filter(Boolean);
  if (!details.length) return null;
  const list = document.createElement("ul");
  list.className = "expected-rows";
  for (const detail of details) {
    const item = document.createElement("li");
    item.textContent = detail;
    list.append(item);
  }
  return list;
}

const criticalFailureLabels: Record<string, string> = {
  "fails language switch or changes facts": "Responde en el idioma solicitado sin cambiar los hechos.",
  "changes the numeric answer": "Mantiene la cifra al simplificar la explicación.",
  "drops 2t26 or metric context": "Conserva el periodo 2T26 y la misma métrica al cambiar de aerolínea.",
};

function appendReviewCriteria(host: HTMLElement, data: Record<string, unknown>): void {
  if (Array.isArray(data.critical_failures) && data.critical_failures.length) {
    const heading = document.createElement("h4");
    heading.textContent = "Criterios de revisión";
    const list = document.createElement("ul");
    list.className = "expected-rows";
    for (const failure of data.critical_failures) {
      if (typeof failure !== "string") continue;
      const item = document.createElement("li");
      item.textContent = criticalFailureLabels[failure.toLocaleLowerCase("en")] ?? failure;
      list.append(item);
    }
    if (list.childElementCount) host.append(heading, list);
  }
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
  appendReviewCriteria(host, data);
  if (!Array.isArray(data.rows) || data.rows.length === 0) {
    const summary = planSummary(data);
    if (summary) {
      const note = document.createElement("p");
      note.className = "expected-guidance";
      note.textContent = "El resultado numérico no está resumido aquí; revisa el detalle de evaluación.";
      host.append(summary, note);
    } else if (status?.toLowerCase() === "multi_turn") {
      const note = document.createElement("p");
      note.className = "expected-guidance";
      note.textContent = "Este caso incluye criterios de conversación; no una referencia numérica.";
      host.append(note);
    } else if (!guidance && host.childElementCount === 0) host.textContent = "El resumen de referencia no está disponible aquí. Consulta el detalle de evaluación.";
    return;
  }
  const rows = document.createElement("ul");
  rows.className = "expected-rows";
  data.rows.forEach((row, index) => rows.append(rowSummary(row, index)));
  host.append(rows);
}
