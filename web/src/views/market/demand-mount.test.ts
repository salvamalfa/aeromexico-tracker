import { readFileSync } from "node:fs";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("../../lib/plotly", () => ({ default: { Plots: { resize: () => Promise.resolve() } } }));
vi.mock("../executive/bootstrap", () => ({ mountExecutive: vi.fn().mockResolvedValue(undefined) }));

afterEach(() => {
  vi.unstubAllGlobals();
  delete window.__pageNoAutoMount;
});

it("mounts actual demand markup from the market tab, retries and keeps source/month selection scoped", async () => {
  window.__pageNoAutoMount = true;
  const html = readFileSync("index.html", "utf8");
  document.body.innerHTML = new DOMParser().parseFromString(html, "text/html").body.innerHTML;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { callback(0); return 0; });
  const row = (key: string, passengers: number, period = "2026M09") => ({ key, group: "GOVERNMENT", period_id: period, passengers, yoy_pct: null, previous_period: "2025M09", previous_passengers: null });
  const payload = {
    months: ["2026M08", "2026M09"],
    airports: [row("MEX", 101), row("NLU", 22), row("MEX", 80, "2026M08")],
    afac_airports: [row("MEX", 100)],
    groups: [{ ...row("ASUR", 999), group: "ASUR" }],
    quality_notes: ["Reconstrucción visible autorizada; no se certifican los bytes originales."],
  };
  const fetcher = vi.fn().mockRejectedValueOnce(new Error("temporarily unavailable"))
    .mockResolvedValue({ ok: true, json: async () => payload });
  vi.stubGlobal("fetch", fetcher);
  const { mount } = await import("../../main");
  await mount("/fixture/data/v1");
  expect(fetcher).not.toHaveBeenCalled();
  const click = (id: string) => document.getElementById(id)!.click();
  click("tab-market");
  await vi.waitFor(() => expect(document.getElementById("airport-note")?.textContent).toContain("no disponible"));
  click("tab-reading"); click("tab-market");
  await vi.waitFor(() => expect(document.querySelectorAll("#airport-demand tr")).toHaveLength(2));
  expect(fetcher).toHaveBeenNthCalledWith(2, "/fixture/data/v1/market-demand.json");
  expect(document.querySelector("#airport-demand-card")?.hasAttribute("data-chat-unavailable")).toBe(true);
  expect(document.getElementById("panel-market")?.hidden).toBe(false);
  const source = document.getElementById("airport-source") as HTMLSelectElement;
  const month = document.getElementById("airport-period") as HTMLSelectElement;
  expect(source.labels?.[0]?.textContent).toContain("Base aeroportuaria");
  expect(month.value).toBe("2026M09");
  source.value = "afac"; source.dispatchEvent(new Event("change"));
  expect(document.querySelectorAll("#airport-demand tr")).toHaveLength(1);
  expect(document.getElementById("airport-demand")?.textContent).toContain("100");
  expect(document.getElementById("airport-demand")?.textContent).not.toContain("101");
  expect(document.getElementById("airport-groups")?.textContent).toContain("999");
  expect(document.getElementById("airport-note")?.textContent).toContain("Los grupos conservan sus reportes directos");
  expect(document.getElementById("airport-quality")?.textContent).toContain("Reconstrucción visible autorizada");
  month.value = "2026M08"; month.dispatchEvent(new Event("change"));
  expect(document.getElementById("airport-demand")?.textContent).toContain("Sin observaciones");
  expect(document.querySelector<HTMLTableCellElement>("#airport-groups td")?.colSpan).toBe(4);
  source.value = "direct"; source.dispatchEvent(new Event("change"));
  expect(document.getElementById("airport-demand")?.textContent).toContain("80");
  expect(document.getElementById("airport-demand")?.textContent).not.toContain("101");
  click("tab-reading"); click("tab-market");
  await vi.waitFor(() => expect(document.getElementById("panel-market")?.hidden).toBe(false));
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(document.querySelectorAll("#airport-source")).toHaveLength(1);
  expect(month.value).toBe("2026M08");
});
