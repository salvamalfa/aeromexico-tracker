import { describe, expect, it } from "vitest";
import { pointsLabel, selectedFares, type FareRow } from "./local-fares";
import { addObservationPeriods, currentPeriodId, initPeriods, periodCount } from "../../state/period";

describe("local fare semantics", () => {
  it("shows Volaris as inapplicable and preserves unknown points for loyalty providers", () => {
    expect(pointsLabel({ provider: "VOLARIS", points: null })).toBe("No aplica");
    expect(pointsLabel({ provider: "DOTERS", points: null })).toBe("N/D");
    expect(pointsLabel({ provider: "AMR", points: 0 })).toBe("0");
  });
  it("filters by consultation quarter rather than departure date", () => {
    const rows = [{ provider: "DOTERS", query_date: "2026-11-10", period_id: "2026Q4",
      departure_date: "2027-01-10", origin: "MEX" }] as FareRow[];
    expect(selectedFares(rows, "2026Q4")).toHaveLength(1);
    expect(selectedFares(rows, "2027Q1")).toEqual([]);
  });
  it("extends the sole period store without changing the selected financial quarter", () => {
    initPeriods(["2026Q2", "2026Q3"], "2026Q3");
    addObservationPeriods(["2026Q4", "bad", "2026Q4"]);
    expect(currentPeriodId()).toBe("2026Q3");
    expect(periodCount()).toBe(3);
  });
});
