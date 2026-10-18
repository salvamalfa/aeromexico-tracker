import { afterEach, expect, it, vi } from "vitest";
import type { MarketDocument } from "../../types/domain";
import { initPeriods } from "../../state/period";
import { entityState } from "./entities";
import Plotly from "../../lib/plotly";
import { mountMarketControls, renderMarket } from "./market";
vi.mock("../../lib/plotly", () => ({ default: { react: vi.fn() } }));
function period(period_id: string, total: number) {
  const segment = { mexican_carriers_passengers: total, carriers: {
    AEROMEXICO: { passengers: total / 2, share: 0.5 },
    VOLARIS: { passengers: total / 4, share: 0.25 },
    VIVA_AEROBUS: { passengers: total / 4, share: 0.25 },
  }, industry: { passengers: total, share: 1 } };
  return { period_id, period_label: period_id, segments: { total: segment, domestic: segment, international: segment } };
}
afterEach(() => { entityState.market = null; vi.clearAllMocks(); });
it("uses the global quarter for totals, comparisons and the plotted history after segment changes", () => {
  document.body.innerHTML = '<div id="market-chart"></div><span id="market-source"></span><div id="market-kpis"></div><table><tbody id="market-comparison"></tbody></table><select id="market-segment"><option>total</option><option>international</option></select>';
  entityState.market = {
    schema_version: "market_v1", carriers: ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"],
    metadata: { default_quarter: "2026Q2", first_period: "2025M01", last_period: "2026M06", industry_note: "", industry_share_latest: 1, method_note: "" },
    quarters: [period("2025Q1", 100), period("2026Q1", 120), period("2026Q2", 150)],
    months: [period("2026M03", 40), period("2026M04", 50), period("2026M06", 50)],
  } as MarketDocument;
  initPeriods(["2026Q1", "2026Q2"], "2026Q1");
  mountMarketControls(); renderMarket(undefined);
  expect(document.querySelector("#market-kpis strong")?.textContent).toBe("120");
  expect(document.querySelector("#market-comparison tr td:nth-child(3)")?.textContent).toBe("20%");
  let [, traces, layout] = vi.mocked(Plotly.react).mock.calls.at(-1)!;
  expect(traces[0]).toMatchObject({ x: ["2026-03-01"] });
  expect(layout?.shapes?.[0]?.x0).toBe("2026-01-01");
  const segment = document.querySelector<HTMLSelectElement>("#market-segment")!;
  segment.value = "international"; segment.dispatchEvent(new Event("change"));
  expect(document.querySelector("#market-kpis strong")?.textContent).toBe("120");
  initPeriods(["2026Q1", "2026Q2"], "2026Q2"); renderMarket("2026Q2");
  expect(document.querySelector("#market-kpis strong")?.textContent).toBe("150");
  [, traces, layout] = vi.mocked(Plotly.react).mock.calls.at(-1)!;
  expect(traces[0]).toMatchObject({ x: ["2026-03-01", "2026-04-01", "2026-06-01"] });
  expect(layout?.shapes?.[0]?.x1).toBe("2026-07-01");
  expect(document.querySelector("#market-kpis")?.textContent).toContain("N/D");
});
