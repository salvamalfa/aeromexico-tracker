import { afterEach, describe, expect, it, vi } from "vitest";

describe("global reading quarter", () => {
  afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, "", "/"); });
  it("uses only the global quarter and never falls back to an issuer's latest reading", async () => {
    vi.resetModules();
    window.history.replaceState(null, "", "/?readingPeriod=2026Q3&sel_reading=VOLARIS");
    const manifest = { analysis_manifest: [
      { period_id: "2026Q2", approval_event: "old" },
      { period_id: "2026Q3", approval_event: "new" },
      { entity_key: "VOLARIS", period_id: "2026Q2", approval_event: "peer" },
    ] };
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => manifest })));
    const finance = await import("../../state/period");
    const reading = await import("./reading-periods");
    await reading.loadReadingPeriods("data/v1");
    finance.initPeriods(["2026Q1", "2026Q2", "2026Q3"], "2026Q2");
    expect(reading.selectedReading("AEROMEXICO")?.period_id).toBe("2026Q2");
    expect(reading.selectedReading("VOLARIS")?.period_id).toBe("2026Q2");
    finance.initPeriods(["2026Q1", "2026Q2", "2026Q3"], "2026Q3");
    expect(reading.selectedReading("AEROMEXICO")?.period_id).toBe("2026Q3");
    expect(reading.selectedReading("VOLARIS")).toBeUndefined();
    finance.initPeriods(["2026Q1", "2026Q2", "2026Q3"], "2026Q1");
    expect(reading.selectedReading("AEROMEXICO")).toBeUndefined();
  });
  it.each([
    { analysis_manifest: [{ period_id: "../../escape", approval_event: "a" }] },
    { analysis_manifest: [{ period_id: "2026Q3" }] },
    { analysis_manifest: [{ entity_key: null, period_id: "2026Q3", approval_event: "a" }] },
    { analysis_manifest: [{ period_id: "2026Q3", approval_event: "a" }, { period_id: "2026Q3", approval_event: "b" }] },
    {},
  ])("rejects unavailable or malformed publication catalogs", async (manifest) => {
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => manifest })));
    const { loadReadingPeriods } = await import("./reading-periods");
    await expect(loadReadingPeriods("data/v1")).rejects.toThrow();
  });
});
