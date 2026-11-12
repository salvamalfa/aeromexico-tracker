import { afterEach, describe, expect, it, vi } from "vitest";
import { fareGroupsForRoute, fareHoverLines, fareListColumns, fareProviderAverages, fareTooltipColumns, loadFareAverages, setFareAveragesForTest, type FareAverage } from "./fare-averages";
import type { OfficialRoute } from "../../types/official-routes";
import { addObservationPeriods, currentPeriodId, initPeriods } from "../../state/period";

const route = { origin: { id: "CITY_MX_MEXICO", point_kind: "city" }, destination: { id: "CITY_MX_MONTERREY", point_kind: "city" } } as OfficialRoute;
const group: FareAverage = { provider: "DOTERS", period_id: "2026Q4", origin: "MEX", destination: "MTY",
  origin_map_id: "CITY_MX_MEXICO", destination_map_id: "CITY_MX_MONTERREY", fare: "Zero", conditions: "Un adulto",
  horizon_months: 1, stay_days: 7, trip_type: "round_trip", observations: 1, paired_cash_points: 1,
  query_date_start: "2026-11-10", query_date_end: "2026-11-10", points_applicability: "applicable", group_id: "test",
  metrics: { cash_final_mxn: { mean: 3107, n: 1 }, points: { mean: 14398, n: 1 },
    redemption_cash_mxn: { mean: null, n: 0 }, redemption_taxes_mxn: { mean: null, n: 0 } } };
afterEach(() => { setFareAveragesForTest(null); document.body.replaceChildren(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe("optional published fare product", () => {
  it("does not request an absent asset from an older manifest and clears stale quotes", async () => {
    vi.stubEnv("VITE_LOCAL_FARES", "false");
    setFareAveragesForTest({ schema_version: "fare_averages_v1", periods: ["2026Q4"], groups: [group] });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ analysis_manifest: [] }) });
    vi.stubGlobal("fetch", fetchMock);
    await loadFareAverages("data/v1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]![0])).toContain("publication_manifest.json");
    expect(fareGroupsForRoute(route, "2026Q4")).toEqual([]);
  });
  it("loads the advertised product using its manifest-relative path", async () => {
    vi.stubEnv("VITE_LOCAL_FARES", "false");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ files: [{ path: "data/v1/fare-averages.json" }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ schema_version: "fare_averages_v1", periods: ["2026Q4"], groups: [group] }) });
    vi.stubGlobal("fetch", fetchMock);
    await loadFareAverages("data/v1");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]![0]).toBe("data/v1/fare-averages.json");
    expect(fareGroupsForRoute(route, "2026Q4")).toEqual([group]);
  });
  it("announces newer quote dates without changing the selected financial quarter", async () => {
    vi.stubEnv("VITE_LOCAL_FARES", "false");
    initPeriods(["2026Q3"], "2026Q3");
    document.body.innerHTML = '<p id="fare-period-note" hidden></p>';
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ files: [{ path: "data/v1/fare-averages.json" }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ schema_version: "fare_averages_v1", periods: ["2026Q4"], groups: [{ ...group, query_date_end: "2026-11-11" }] }) });
    vi.stubGlobal("fetch", fetchMock);
    await loadFareAverages("data/v1");
    const note = document.getElementById("fare-period-note")!;
    expect(currentPeriodId()).toBe("2026Q3");
    expect(note.hidden).toBe(false);
    expect(note.textContent).toContain("11/11/2026 (4T26)");
    expect(note.textContent).toContain("Selecciona 4T26");
    addObservationPeriods(["2026Q4"], "2026Q4");
    expect(note.textContent).not.toContain("Selecciona");
  });
});

describe("quarterly cost tooltip", () => {
  it("weights full-precision means by each metric's n, keeps programs apart and filters the actual quarter", () => {
    const first = { ...group, metrics: { ...group.metrics, cash_final_mxn: { mean: 100 / 3, n: 3 }, points: { mean: 1000, n: 1 } }, paired_cash_points: 0 };
    const second = { ...group, horizon_months: 3, metrics: { ...group.metrics, cash_final_mxn: { mean: 200, n: 1 }, points: { mean: 3000, n: 3 } }, paired_cash_points: 0 };
    const amr = { ...group, provider: "AMR" as const, metrics: { ...group.metrics, cash_final_mxn: { mean: 900, n: 1 }, points: { mean: 50000, n: 1 } } };
    const volaris = { ...group, provider: "VOLARIS" as const, metrics: { ...group.metrics, cash_final_mxn: { mean: 500, n: 2 }, points: { mean: null, n: 0 } } };
    setFareAveragesForTest({ schema_version: "fare_averages_v1", periods: ["2026Q4"], groups: [first, second, amr, volaris] });
    const summaries = fareProviderAverages(route, "2026Q4");
    expect(summaries.find(item => item.provider === "DOTERS")).toEqual({ provider: "DOTERS", cash: { mean: 75, n: 4 }, points: { mean: 2500, n: 4 } });
    expect(summaries.find(item => item.provider === "AMR")?.points).toEqual({ mean: 50000, n: 1 });
    expect(summaries.find(item => item.provider === "VOLARIS")?.points).toEqual({ mean: null, n: 0 });
    expect(fareProviderAverages(route, "2026Q3")).toEqual([]);
    expect(fareListColumns(route, "2026Q3")).not.toContain("$75");
    expect(fareProviderAverages(route, "2026Q4", ["VOLARIS"]).map(item => item.provider)).toEqual(["VOLARIS"]);
    expect(fareTooltipColumns(route, "2026Q4", ["VOLARIS"])).not.toContain("Viva / Doters");
    const hover = fareHoverLines(route, "2026Q4");
    expect(hover).toContain("Viva / Doters: $75.00 | 2,500 | n dinero=4, puntos=4");
    expect(hover).toContain("Volaris: $500.00 | No aplica");
  });
  it("matches both directions but preserves the explicit city-airport mapping", () => {
    setFareAveragesForTest({ schema_version: "fare_averages_v1", periods: ["2026Q4"], groups: [group] });
    expect(fareProviderAverages({ ...route, origin: route.destination, destination: route.origin }, "2026Q4")).toEqual(fareProviderAverages(route, "2026Q4"));
    expect(fareProviderAverages({ ...route, origin: { ...route.origin, id: "CITY_MX_SANTA_LUCIA" } }, "2026Q4")).toEqual([]);
  });
  it("adds separate money and points columns with consultation quarter and denominators", () => {
    setFareAveragesForTest({ schema_version: "fare_averages_v1", periods: ["2026Q4"], groups: [group] });
    const html = fareTooltipColumns(route, "2026Q4");
    expect(html).toContain("consultas 4T26");
    expect(html).toContain("<th>Dinero · MXN</th><th>Puntos</th><th>Base</th>");
    expect(html).toContain("$3,107.00"); expect(html).toContain("14,398"); expect(html).toContain("Dinero n=1");
    expect(fareHoverLines(route, "2026Q4")).toContain("Medias de consultas 4T26");
    expect(fareGroupsForRoute(route, "2026Q3")).toEqual([]);
  });
  it("keeps NLU apart from the Mexico city route mapped explicitly to MEX", () => {
    setFareAveragesForTest({ schema_version: "fare_averages_v1", periods: ["2026Q4"], groups: [
      { ...group, origin: "NLU", origin_map_id: "CITY_MX_SANTA_LUCIA" }] });
    expect(fareGroupsForRoute(route, "2026Q4")).toEqual([]);
  });
  it("uses No aplica for Volaris and does not display an unknown amount as zero", () => {
    setFareAveragesForTest({ schema_version: "fare_averages_v1", periods: ["2026Q4"], groups: [
      { ...group, provider: "VOLARIS", metrics: { ...group.metrics,
        points: { mean: null, n: 0 }, cash_final_mxn: { mean: null, n: 0 } } }] });
    const html = fareTooltipColumns(route, "2026Q4");
    expect(html).toContain("No aplica"); expect(html).toContain("<td>N/D</td>"); expect(html).not.toContain("$0.00");
  });
});
