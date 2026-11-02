import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { initPeriods } from "../../state/period";
import { loadReadingPeriods } from "./reading-periods";
import { renderIndustryReading } from "./overview";
import { state } from "./state";

// Real signed publication catalog and issuer documents, including the gap for
// Industry Q3. The overview must never load Industry Q2 to fill that gap.
beforeEach(async () => {
  document.body.innerHTML = readFileSync("index.html", "utf8");
  state.dataRoot = "data/v1";
  vi.stubGlobal("fetch", vi.fn(async (url: string | URL) => {
    const path = String(url).includes("publication_manifest")
      ? "../site/publication_manifest.json" : `../site/${String(url)}`;
    try { return { ok: true, json: async () => JSON.parse(readFileSync(path, "utf8")) }; }
    catch { return { ok: false }; }
  }));
  await loadReadingPeriods("data/v1");
});
afterEach(() => vi.unstubAllGlobals());

it("shows exactly four sourced points with no redundant controls or footers", async () => {
  initPeriods(["2026Q2", "2026Q3"], "2026Q3");
  await renderIndustryReading();
  const items = [...document.querySelectorAll("#narrative-copy li")];
  expect(items).toHaveLength(4);
  expect(items.map(li => li.querySelector("strong")?.textContent)).toEqual(["Industria. ", "Aeroméxico. ", "Viva. ", "Volaris. "]);
  expect(items[1]?.textContent).toContain("US$1,619 millones");
  expect(items[1]?.textContent).toContain("11.7%");
  expect(items[2]?.textContent).toContain("695.8 millones");
  expect(items[3]?.textContent).toContain("1,038.0 millones");
  for (const li of items) expect(li.querySelectorAll("a.source-note").length).toBeGreaterThan(0);
  expect(document.querySelector("#panel-reading select")).toBeNull();
  expect(document.querySelector("#panel-reading .analysis-context")).toBeNull();
  expect(document.querySelector("#panel-reading .analysis-actions")).toBeNull();
  expect(document.querySelector("#panel-reading")?.textContent).not.toContain("Corte de información");
  expect(document.querySelector("#panel-reading")?.textContent).not.toContain("Lectura ejecutiva ·");
  expect(document.getElementById("executive-reading-title")?.textContent).toBe("Mayores ingresos, rentabilidad bajo presión");
  expect(items[0]?.querySelector("span strong")?.textContent).toBe("aumentaron sus ingresos");
  expect(items[1]?.querySelector("span strong")?.textContent).toContain("facturó US$1,619 millones");
  expect(items[2]?.querySelector("span strong")?.textContent).toContain("ingresos trimestrales a 695.8");
  expect(items[3]?.querySelector("span strong")?.textContent).toContain("ingresos trimestrales de 1,038.0");
});

it("keeps the complete approved text and citations below the summary inside the same reading card", async () => {
  initPeriods(["2026Q2", "2026Q3"], "2026Q3");
  await renderIndustryReading();
  const card = document.getElementById("reading-full-card")!;
  const details = document.getElementById("reading-full") as HTMLDetailsElement;
  expect(card.hidden).toBe(false);
  expect(details.open).toBe(false);
  expect(card.closest(".narrative-card")).toBe(document.getElementById("narrative-copy")?.closest(".narrative-card"));
  expect(document.querySelectorAll("#panel-reading .narrative-card")).toHaveLength(1);
  expect(card.querySelectorAll("select")).toHaveLength(0);
  expect(card.querySelector('[data-entity="INDUSTRY"]')).toBeNull();
  for (const [entity, path] of [["AEROMEXICO", ""], ["VIVA_AEROBUS", "VIVA_AEROBUS/"], ["VOLARIS", "VOLARIS/"]]) {
    const approved = JSON.parse(readFileSync(`../site/data/v1/analysis/${path}2026Q3.json`, "utf8"));
    const article = card.querySelector(`[data-entity="${entity}"]`)!;
    const paragraphs = [...article.querySelectorAll("section p")].map(p => {
      const clone = p.cloneNode(true) as HTMLElement;
      clone.querySelectorAll("sup").forEach(sup => sup.remove());
      return clone.textContent;
    });
    expect(paragraphs).toEqual(approved.sections.flatMap((section: {paragraphs: string[]}) => section.paragraphs));
    expect(article.querySelectorAll("a.source-note").length).toBeGreaterThan(0);
  }
  details.open = true;
  initPeriods(["2026Q2", "2026Q3"], "2026Q2");
  await renderIndustryReading();
  expect(details.open).toBe(false);
  expect(card.querySelectorAll("article")).toHaveLength(4);
  expect(card.textContent).not.toContain("US$1,619 millones");
});

it("replaces actual values on Q3 to Q2 and back, including the Industry reading", async () => {
  for (const period of ["2026Q3", "2026Q2", "2026Q3"]) {
    initPeriods(["2026Q2", "2026Q3"], period);
    await renderIndustryReading();
    const copy = document.getElementById("narrative-copy")!;
    expect(copy.dataset.period).toBe(period);
    expect(copy.querySelectorAll("li")).toHaveLength(4);
    expect(copy.textContent).toContain(period === "2026Q3" ? "US$1,619 millones" : "1,479.0 millones");
    expect(copy.textContent).not.toContain(period === "2026Q3" ? "1,479.0 millones" : "US$1,619 millones");
    if (period === "2026Q2") expect(copy.textContent).toContain("31,5 %");
  }
});

it("clears the previous reading when a selected quarter has no approved documents", async () => {
  initPeriods(["2026Q1", "2026Q3"], "2026Q3");
  await renderIndustryReading();
  initPeriods(["2026Q1", "2026Q3"], "2026Q1");
  await renderIndustryReading();
  const copy = document.getElementById("narrative-copy")!;
  expect(copy.textContent).not.toContain("US$1,619 millones");
  expect(copy.querySelectorAll("li")).toHaveLength(4);
  expect(copy.querySelectorAll("a")).toHaveLength(0);
  expect(copy.textContent?.match(/Sin lectura publicada/g)).toHaveLength(4);
  expect(document.getElementById("reading-full-card")?.hidden).toBe(true);
  expect(document.getElementById("reading-full-copy")?.textContent).toBe("");
});
