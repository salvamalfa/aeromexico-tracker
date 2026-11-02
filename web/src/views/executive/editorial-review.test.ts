import { readFileSync } from "node:fs";
import { afterEach, expect, it, vi } from "vitest";
import { initPeriods } from "../../state/period";
import { loadEditorialReview } from "./editorial-review";
import { renderIndustryReading } from "./overview";

const review = JSON.parse(readFileSync("../docs/referencias/periodos-20261031/editorial-rerun-q3.json", "utf8"));
afterEach(() => { window.history.replaceState(null,"","/"); vi.unstubAllGlobals(); });

it("renders the four rebuilt readings only in explicit local draft review", async () => {
  document.body.innerHTML = readFileSync("index.html","utf8");
  window.history.replaceState(null,"","/?period=2026Q3&review=1");
  vi.stubGlobal("fetch",vi.fn(async () => ({ok:true,json:async()=>review})));
  initPeriods(["2026Q2","2026Q3"],"2026Q3");
  await renderIndustryReading();
  const list = document.querySelectorAll("#narrative-copy li");
  expect(list).toHaveLength(4);
  expect(list[0]?.textContent).toContain("La presión de costos fue compartida");
  expect(list[1]?.textContent).toContain("puntos de lealtad");
  expect(list[2]?.textContent).toContain("31.5");
  expect(list[3]?.textContent).toContain("mil millones de dólares");
  expect(document.getElementById("reading-review-note")).toBeNull();
  expect(document.querySelector("#panel-reading")?.textContent).not.toContain("Propuesta editorial para revisión");
  expect(document.querySelectorAll("#reading-full-copy article")).toHaveLength(4);
  expect(document.getElementById("reading-full-copy")?.textContent).toContain("17.20");
  expect(document.getElementById("reading-full-copy")?.textContent).toContain("11.49");
  expect(document.getElementById("reading-full-copy")?.textContent).toContain("10.31");
  expect(review.state).toBe("draft");
  for (const analysis of Object.values(review.analyses) as object[]) expect(analysis).not.toHaveProperty("approval_event");
});

it("does not fetch drafts without the explicit review query and rejects a mismatched quarter", async () => {
  const fetcher=vi.fn(async()=>({ok:true,json:async()=>({...review,period_id:"2026Q2"})}));
  vi.stubGlobal("fetch",fetcher);
  expect(await loadEditorialReview("2026Q3")).toBeNull(); expect(fetcher).not.toHaveBeenCalled();
  window.history.replaceState(null,"","/?review=1");
  await expect(loadEditorialReview("2026Q3")).rejects.toThrow("inválida");
});
