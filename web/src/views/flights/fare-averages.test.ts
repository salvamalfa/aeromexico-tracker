import { afterEach, describe, expect, it } from "vitest";
import { fareGroupsForRoute, fareHoverLines, fareTooltipColumns, setFareAveragesForTest, type FareAverage } from "./fare-averages";
import type { OfficialRoute } from "../../types/official-routes";

const route = { origin: { id: "CITY_MX_MEXICO", point_kind: "city" }, destination: { id: "CITY_MX_MONTERREY", point_kind: "city" } } as OfficialRoute;
const group: FareAverage = { provider: "DOTERS", period_id: "2026Q4", origin: "MEX", destination: "MTY",
  origin_map_id: "CITY_MX_MEXICO", destination_map_id: "CITY_MX_MONTERREY", fare: "Zero", conditions: "Un adulto",
  horizon_months: 1, stay_days: 7, trip_type: "round_trip", observations: 1, paired_cash_points: 1,
  query_date_start: "2026-11-10", query_date_end: "2026-11-10", points_applicability: "applicable", group_id: "test",
  metrics: { cash_final_mxn: { mean: 3107, n: 1 }, points: { mean: 14398, n: 1 },
    redemption_cash_mxn: { mean: null, n: 0 }, redemption_taxes_mxn: { mean: null, n: 0 } } };
afterEach(() => setFareAveragesForTest(null));

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
