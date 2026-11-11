// Local-only, private fare book observations. Production never fetches this endpoint.
import { addObservationPeriods, currentPeriodId, subscribe } from "../../state/period";
import "./local-fares.css";

export interface FareRow {
  provider: "AMR" | "DOTERS" | "VOLARIS";
  query_date: string; period_id: string; captured_at: string | null;
  origin: string; destination: string; departure_date: string; return_date: string | null;
  outbound_departure_time: string | null; return_departure_time: string | null;
  outbound_arrival_time: string | null; return_arrival_time: string | null;
  outbound_flight: string | null; return_flight: string | null;
  fare: string | null; conditions: string | null; notes: string | null;
  cash_final_mxn: number | null; points: number | null; redemption_cash_mxn: number | null;
  redemption_carrier_mxn: number | null; redemption_taxes_mxn: number | null;
  cash_carrier_mxn: number | null; cash_taxes_mxn: number | null;
  evidence: string | null; status: string;
  sources: Array<{ spreadsheet_id: string; sheet_name: string; row: number }>;
}
interface FareDocument { schema_version: string; private: boolean; rows: FareRow[]; periods: string[]; quarantine_count: number }
const money = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });
const integer = new Intl.NumberFormat("es-MX");
const providerLabels = { AMR: "Aeroméxico", DOTERS: "Viva / Doters", VOLARIS: "Volaris" };
const labels: Record<string, string> = { ok: "Completa", partial_redemption: "Canje pendiente",
  legacy_unverified: "Histórica sin final verificado", login_required: "Requiere sesión",
  access_blocked: "Acceso bloqueado", no_availability: "Sin disponibilidad", error: "Error" };
const cash = (value: number | null) => value === null ? "N/D" : money.format(value);
const cell = (value: string) => { const td = document.createElement("td"); td.textContent = value; return td; };

export function pointsLabel(row: Pick<FareRow, "provider" | "points">): string {
  return row.provider === "VOLARIS" ? "No aplica" : row.points === null ? "N/D" : integer.format(row.points);
}
export function selectedFares(rows: FareRow[], period: string | undefined): FareRow[] {
  return rows.filter(row => row.period_id === period).sort((a, b) =>
    b.query_date.localeCompare(a.query_date) || a.provider.localeCompare(b.provider) || a.origin.localeCompare(b.origin));
}
function detail(row: FareRow): HTMLDetailsElement {
  const details = document.createElement("details"), summary = document.createElement("summary");
  summary.textContent = labels[row.status] ?? row.status; details.append(summary);
  const lines = [
    `Consulta: ${row.captured_at ?? row.query_date}.`,
    `Ida: ${row.outbound_flight ?? "N/D"}, ${row.outbound_departure_time ?? "N/D"} → ${row.outbound_arrival_time ?? "N/D"}.`,
    `Regreso: ${row.return_flight ?? "N/D"}, ${row.return_departure_time ?? "N/D"} → ${row.return_arrival_time ?? "N/D"}.`,
    `Tarifa: ${row.fare ?? "N/D"}. ${row.conditions ?? ""}`,
    `Dinero: componente ${cash(row.cash_carrier_mxn)}; impuestos ${cash(row.cash_taxes_mxn)}.`,
    `Canje: componente ${cash(row.redemption_carrier_mxn)}; impuestos ${cash(row.redemption_taxes_mxn)}.`,
  ];
  for (const line of lines) { const p = document.createElement("p"); p.textContent = line; details.append(p); }
  if (row.provider !== "VOLARIS" && row.redemption_cash_mxn === null) {
    const p = document.createElement("p"); p.textContent = "Pago final del canje sin confirmar. Los componentes no acreditan un total."; details.append(p);
  }
  for (const source of row.sources) {
    const a = document.createElement("a");
    a.href = `https://docs.google.com/spreadsheets/d/${encodeURIComponent(source.spreadsheet_id)}/edit`;
    a.target = "_blank"; a.rel = "noopener noreferrer";
    a.textContent = `${source.sheet_name}, fila ${source.row}`; details.append(a, document.createTextNode(" "));
  }
  return details;
}

export async function mountLocalFares(): Promise<void> {
  const panel = document.createElement("section"); panel.id = "panel-fares"; panel.className = "local-fares";
  panel.setAttribute("aria-label", "Precios y puntos locales");
  panel.innerHTML = '<div class="section-heading"><h2>Precios y puntos</h2></div><p id="fare-scope"></p><p id="fare-summary" role="status"></p><div class="fare-table-scroll"><table><thead><tr><th>Proveedor</th><th>Ruta</th><th>Viaje</th><th>Final dinero · MXN</th><th>Puntos</th><th>Pago final canje · MXN</th><th>Estado y detalle</th></tr></thead><tbody id="fare-body"></tbody></table></div>';
  // Remains within Mercado: no new navigation or second date selector.
  document.getElementById("panel-flights")?.append(panel);
  const summary = panel.querySelector<HTMLElement>("#fare-summary")!;
  let payload: FareDocument;
  try {
    const response = await fetch("/__local-fares.json", { cache: "no-store" });
    if (!response.ok) throw new Error("No se pudieron leer las cotizaciones locales.");
    payload = await response.json() as FareDocument;
    if (payload.schema_version !== "local_fare_quotes_v1" || payload.private !== true || !Array.isArray(payload.rows)) {
      throw new Error("Formato local incompatible.");
    }
  } catch (error) { summary.textContent = String(error); return; }
  function render(): void {
    const period = currentPeriodId();
    const rows = selectedFares(payload.rows, period);
    panel.querySelector<HTMLElement>("#fare-scope")!.textContent =
      `Consultas realizadas en ${period ?? "el trimestre seleccionado"}. Las fechas del viaje se conservan por separado.`;
    const verified = rows.filter(row => ["ok", "partial_redemption"].includes(row.status) && row.cash_final_mxn !== null);
    summary.textContent = rows.length ? `Precios finales verificados: ${verified.length} · Observaciones: ${rows.length}. Registros en revisión: ${payload.quarantine_count}.`
      : "Sin capturas para este trimestre. Las cotizaciones de otros trimestres siguen conservadas.";
    const tbody = panel.querySelector<HTMLElement>("#fare-body")!; tbody.replaceChildren();
    for (const row of rows) {
      const tr = document.createElement("tr");
      tr.append(cell(providerLabels[row.provider]), cell(`${row.origin} → ${row.destination}`),
        cell(`${row.departure_date} / ${row.return_date ?? "Sólo ida"}`), cell(cash(row.cash_final_mxn)),
        cell(pointsLabel(row)), cell(row.provider === "VOLARIS" ? "No aplica" : cash(row.redemption_cash_mxn)));
      const td = document.createElement("td"); td.append(detail(row)); tr.append(td); tbody.append(tr);
    }
  }
  addObservationPeriods(payload.periods);
  subscribe(render); render();
}
