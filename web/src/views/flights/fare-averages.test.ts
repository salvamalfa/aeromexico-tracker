import { afterEach, describe, expect, it, vi } from "vitest";
import { fareGroupsForRoute, fareHoverLines, fareTooltipColumns, loadFareAverages, setFareAveragesForTest, type FareAverage } from "./fare-averages";
import type { OfficialRoute } from "../../types/official-routes";

const route = { origin: { id: "CITY_MX_MEXICO", point_kind: "city" }, destination: { id: "CITY_MX_MONTERREY", point_kind: "city" } } as OfficialRoute;
const group: FareAverage = { provider: "DOTERS", period_id: "2026Q4", origin: "MEX", destination: "MTY",
  origin_map_id: "CITY_MX_MEXICO", destination_map_id: "CITY_MX_MONTERREY", fare: "Zero", conditions: "Un adulto",
  horizon_months: 1, stay_days: 7, trip_type: "round_trip", observations: 1, paired_cash_points: 1,
  query_date_start: "2026-11-10", query_date_end: "2026-11-10", points_applicability: "applicable", group_id: "test",
  metrics: { cash_final_mxn: { mean: 3107, n: 1 }, points: { mean: 14398, n: 1 },
    redemption_cash_mxn: { mean: null, n: 0 }, redemption_taxes_mxn: { mean: null, n: 0 } } };
afterEach(() => { setFareAveragesForTest(null); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

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
});

describe("quarterly cost tooltip", () => {
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
