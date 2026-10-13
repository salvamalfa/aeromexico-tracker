import { afterEach, describe, expect, it, vi } from "vitest";

describe("executive period deep links", () => {
  afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, "", "/"); });
  it("reads an available requested period and rejects unavailable or malformed requests", async () => {
    vi.resetModules();
    const payload = { metadata: { default_period: "2026Q2" }, records: [{ period_id: "2026Q1" }, { period_id: "2026Q2" }], views: { "2026Q1": {}, "2026Q2": {} } };
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => payload })));
    const { loadExecutive, state } = await import("./state");
    const { currentPeriodId } = await import("../../state/period");
    window.history.replaceState(null, "", "/?entity=VIVA_AEROBUS&period=2026Q1");
    await loadExecutive();
    expect(currentPeriodId()).toBe("2026Q1"); expect(state.periodIndex).toBe(0);
    for (const requested of ["2026Q3", "../../escape", "<script>"]) {
      window.history.replaceState(null, "", `/?period=${encodeURIComponent(requested)}`);
      await loadExecutive(); expect(currentPeriodId()).toBe("2026Q2");
    }
  });
});
