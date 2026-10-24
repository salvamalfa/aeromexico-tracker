import { afterEach, describe, expect, it, vi } from "vitest";

describe("independent reading periods", () => {
  afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, "", "/"); });
  it("selects only approved readings without changing financial periods or records", async () => {
    vi.resetModules();
    document.body.innerHTML = '<select id="reading-period"></select>';
    const manifest = { analysis_manifest: [
      { period_id: "2026Q2", approval_event: "old" },
      { period_id: "2026Q3", approval_event: "new" },
      { entity_key: "VOLARIS", period_id: "2026Q2", approval_event: "peer" },
    ] };
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => manifest })));
    const finance = await import("../../state/period");
    finance.initPeriods(["2026Q1", "2026Q2"], "2026Q2");
    const { state } = await import("./state");
    state.records = [{ period_id: "2026Q2" }] as typeof state.records;
    const before = JSON.stringify(state.records);
    const reading = await import("./reading-periods");
    await reading.loadReadingPeriods("data/v1");
    expect(reading.selectedReading("AEROMEXICO")?.period_id).toBe("2026Q3");
    reading.selectReadingPeriod("2026Q2");
    expect(reading.selectedReading("AEROMEXICO")?.period_id).toBe("2026Q2");
    reading.selectReadingPeriod("2027Q1");
    expect(reading.selectedReading("AEROMEXICO")?.period_id).toBe("2026Q2");
    expect(reading.selectedReading("VOLARIS")?.period_id).toBe("2026Q2");
    expect(finance.currentPeriodId()).toBe("2026Q2");
    expect(JSON.stringify(state.records)).toBe(before);
    expect(document.querySelectorAll("option")).toHaveLength(1);
  });
  it.each([
    { analysis_manifest: [{ period_id: "../../escape", approval_event: "a" }] },
    { analysis_manifest: [{ period_id: "2026Q3" }] },
    { analysis_manifest: [{ period_id: "2026Q3", approval_event: "a" }, { period_id: "2026Q3", approval_event: "b" }] },
    {},
  ])("rejects unavailable or malformed publication catalogs", async (manifest) => {
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => manifest })));
    const { loadReadingPeriods } = await import("./reading-periods");
    await expect(loadReadingPeriods("data/v1")).rejects.toThrow();
  });
});
