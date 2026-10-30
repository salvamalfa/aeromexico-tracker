import { beforeEach, describe, expect, it, vi } from "vitest";
import type { QuarterRecord } from "../../types/domain";
import { state } from "./state";
import { renderMix } from "./mix";
const mocks = vi.hoisted(() => ({ react: vi.fn(), entity: vi.fn(), entities: ["AEROMEXICO"] }));
vi.mock("../../lib/plotly", () => ({ default: { react: mocks.react } }));
vi.mock("./carriers", () => ({ renderEntityMix: mocks.entity }));
vi.mock("../shell/carriers", () => ({ selection: () => mocks.entities }));
const record = { period_label: "2T26", metrics: { passengers: {
  period_start: "2026-04-01", period_end: "2026-06-30",
} } } as QuarterRecord;

describe("separate corporate monthly passenger basis", () => {
  beforeEach(() => {
    mocks.react.mockClear(); mocks.entity.mockClear(); mocks.entities = ["AEROMEXICO"];
    document.body.innerHTML = '<p id="mix-source-inline"></p><label id="passenger-basis-control" hidden></label><select id="passenger-period"><option value="quarter">Trimestral</option><option value="month">Mensual</option></select><div id="mix-chart"></div>';
    window.matchMedia = vi.fn().mockReturnValue({ matches: false });
    state.passengerPeriod = "quarter"; state.passengerBasis = "afac";
    state.corporatePeerMonthlyPassengers = {};
    state.monthlyPassengers = { records: ["04", "05", "06"].map((month) => ({ date: `2026-${month}-01`, domestic: 10, international: 5, total_segment_sum: 15 })) };
    state.corporateMonthlyPassengers = { entity: "AEROMEXICO", source_url: "https://ir.aeromexico.com/node/9131/html",
      source_sha256: "a".repeat(64), captured_at: "2026-10-28T22:09:43+00:00", documentary_date: "2026-10-06", scope: "company",
      records: [{ period_id: "2025M09", date: "2025-09-01", domestic: 1276000, international: 617000,
        total_segment_sum: 1893000, reported_total: 1892000, reconciliation_delta: -1000 },
      { period_id: "2026M09", date: "2026-09-01", domestic: 1226000, international: 627000,
        total_segment_sum: 1853000, reported_total: 1853000, reconciliation_delta: 0 }] };
  });
  it("keeps AFAC as the existing default", () => {
    renderMix(record);
    expect(mocks.react.mock.calls[0]![1][2].y).toEqual([45]);
    expect(document.getElementById("mix-source-inline")?.textContent).toContain("AFAC · pasajeros transportados");
  });
  it("plots reported totals and isolated months without a false quarterly aggregate or gap line", () => {
    state.passengerBasis = "corporate";
    renderMix(record);
    const traces = mocks.react.mock.calls[0]![1];
    expect(traces[2].y).toEqual([1892000, 1853000]);
    expect(traces[2].x).toEqual(["2025-09-01", "2026-09-01"]);
    expect(traces[2].mode).toBe("markers");
    expect(traces[2].hovertemplate).toContain("redondeados");
    expect(state.passengerPeriod).toBe("month");
    expect(document.querySelector<HTMLOptionElement>('option[value="quarter"]')?.disabled).toBe(true);
    expect(document.querySelector<HTMLAnchorElement>("#mix-source-inline a")?.href).toBe("https://ir.aeromexico.com/node/9131/html");
    expect(document.getElementById("mix-source-inline")?.textContent).toContain("captura 2026-10-28");
    expect(document.getElementById("mix-source-inline")?.textContent).toContain("No equivale a AFAC");
  });
  it("uses only AFAC in a multi-airline comparison even after the corporate option was selected", () => {
    state.passengerBasis = "corporate"; mocks.entities = ["AEROMEXICO", "VOLARIS"];
    renderMix(record);
    expect(mocks.react).not.toHaveBeenCalled();
    expect(mocks.entity).toHaveBeenCalledWith(mocks.entities, record, "quarter");
    expect(document.getElementById("passenger-basis-control")?.hidden).toBe(true);
  });
  it("omits incomplete AFAC quarters instead of turning July and August into Q3", () => {
    for (const month of ["07", "08"]) state.monthlyPassengers!.records.push({ date: `2026-${month}-01`, domestic: 3, international: 2, total_segment_sum: 5 });
    renderMix(record);
    expect(mocks.react.mock.calls[0]![1][2].x).toEqual(["2026-04-01"]);
    expect(mocks.react.mock.calls[0]![1][2].y).toEqual([45]);
  });
  it("shows an empty-state explanation when the only quarter has fewer than three months", () => {
    state.monthlyPassengers!.records = state.monthlyPassengers!.records.slice(0, 2);
    renderMix(record);
    expect(mocks.react.mock.calls[0]![1]).toEqual([]);
    expect(mocks.react.mock.calls[0]![2].annotations[0].text).toContain("tres meses completos");
  });
  it("rejects a complete-looking quarter whose regional count is null", () => {
    state.monthlyPassengers!.records[1]!.international = null as unknown as number;
    renderMix(record);
    expect(mocks.react.mock.calls[0]![1]).toEqual([]);
  });
  it("rejects three records that repeat one month", () => {
    state.monthlyPassengers!.records[1]!.date = "2026-04-01";
    renderMix(record);
    expect(mocks.react.mock.calls[0]![1]).toEqual([]);
  });
  it.each(["VIVA_AEROBUS", "VOLARIS"] as const)("shows %s corporate bookings alone and leaves AFAC comparisons intact", (entity) => {
    mocks.entities = [entity]; state.passengerBasis = "corporate";
    state.corporatePeerMonthlyPassengers[entity] = {
      ...state.corporateMonthlyPassengers!, entity, scope: "booked_flight_segments_not_observed_flown_passengers_itinerary_and_charter",
      reporting_status: "preliminar", entity_attribution: "Universo corporativo; no censo de operadores AFAC",
    };
    renderMix(record);
    expect(mocks.entity).not.toHaveBeenCalled();
    expect(mocks.react.mock.calls[0]![1][2].y).toEqual([1892000, 1853000]);
    expect(mocks.react.mock.calls[0]![2].shapes).toEqual([]);
    expect(mocks.react.mock.calls[0]![2].yaxis.title.text).toBe("Tramos de pasajero reservados");
    expect(document.getElementById("mix-source-inline")?.textContent).toContain("no pasajeros transportados");
    expect(document.getElementById("mix-source-inline")?.textContent).toContain("comparativo anual reportados en la misma edición");
    expect(document.getElementById("passenger-basis-control")?.hidden).toBe(false);
    state.passengerBasis = "afac"; renderMix(record);
    expect(mocks.entity).toHaveBeenCalledWith([entity], record, "month");
  });
  it("falls back to the retained AFAC chart when no corporate payload is present", () => {
    state.passengerBasis = "corporate"; state.corporateMonthlyPassengers = null;
    renderMix(record);
    expect(mocks.react.mock.calls[0]![1][2].y).toEqual([45]);
    expect(document.getElementById("passenger-basis-control")?.hidden).toBe(true);
  });
});
