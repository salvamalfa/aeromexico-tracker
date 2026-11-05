import { existsSync, readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { initPeriods } from "../../state/period";
import { loadReadingPeriods } from "./reading-periods";
import { renderIndustryReading } from "./overview";
import { state } from "./state";
import type { AnalysisDocument } from "../../types/domain";

const manifest = JSON.parse(readFileSync("../site/publication_manifest.json", "utf8")) as {
  analysis_manifest: Array<{ entity_key?: string; period_id: string; version: string }>;
};
const replacement = existsSync("../site/quarterly-story-publication.json");
const entities = ["INDUSTRY", "AEROMEXICO", "VIVA_AEROBUS", "VOLARIS"];
function approved(entity: string, period: string): AnalysisDocument | undefined {
  const entry = manifest.analysis_manifest.find(row => (row.entity_key ?? "AEROMEXICO") === entity && row.period_id === period);
  if (!entry) return undefined;
  // The raw catalog controls the path; the payload may normalize entity_key.
  const path = entry.entity_key === undefined ? period : `${entry.entity_key}/${period}`;
  const document = JSON.parse(readFileSync(`../site/data/v1/analysis/${path}.json`, "utf8")) as AnalysisDocument;
  expect(document.version).toBe(entry.version);
  return document;
}
function plain(element: Element): string {
  const copy = element.cloneNode(true) as Element;
  copy.querySelectorAll("sup").forEach(sup => sup.remove());
  return copy.textContent ?? "";
}

// Read the actual versioned site, including either the exact legacy seven
// entries or the explicit replacement's eight. No draft is served as approval.
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

it("uses exactly the declared historical or replacement catalog without inventing an Industry approval", () => {
  const identities = manifest.analysis_manifest.map(row => `${row.entity_key ?? "AEROMEXICO"}/${row.period_id}`).sort();
  expect(identities).toEqual([
    ...entities.map(entity => `${entity}/2026Q2`),
    ...(replacement ? entities : entities.filter(entity => entity !== "INDUSTRY")).map(entity => `${entity}/2026Q3`),
  ].sort());
  if (replacement) {
    expect(manifest.analysis_manifest.find(row => (row.entity_key ?? "AEROMEXICO") === "AEROMEXICO" && row.period_id === "2026Q3")?.entity_key).toBe("AEROMEXICO");
    expect(existsSync("../site/data/v1/analysis/2026Q3.json")).toBe(false);
  }
});

it("shows exactly four sourced points with no redundant controls or footers", async () => {
  initPeriods(["2026Q2", "2026Q3"], "2026Q3");
  await renderIndustryReading();
  const items = [...document.querySelectorAll("#narrative-copy li")];
  expect(items).toHaveLength(4);
  expect(items.map(li => li.querySelector("strong")?.textContent)).toEqual(["Industria. ", "Aeroméxico. ", "Viva. ", "Volaris. "]);
  if (replacement) {
    for (const [index, entity] of entities.entries()) {
      const document = approved(entity, "2026Q3")!;
      expect(document.summary_items).toHaveLength(1);
      const summary = document.summary_items[0]!;
      // AM's short summary omits its lead; its full approved text stays below.
      if (entity === "AEROMEXICO") {
        expect(summary.text.startsWith(summary.lead!)).toBe(true);
        expect(plain(items[index]!.querySelector("span")!)).toBe(summary.text.slice(summary.lead!.length).trim());
      } else expect(plain(items[index]!.querySelector("span")!)).toBe(summary.text);
      const claim = document.claims.find(claim => claim.claim_id === document.summary_items[0]!.claim_id)!;
      expect([...items[index]!.querySelectorAll("a.source-note")].map(a => a.getAttribute("href")).sort())
        .toEqual(claim.citations.map(citation => citation.href).sort());
    }
  } else {
    expect(items[1]?.textContent).toContain("US$1,619 millones");
    expect(items[1]?.textContent).toContain("11.7%");
    expect(items[2]?.textContent).toContain("695.8 millones");
    expect(items[3]?.textContent).toContain("1,038.0 millones");
  }
  for (const li of items) expect(li.querySelectorAll("a.source-note").length).toBeGreaterThan(0);
  expect(document.querySelector("#panel-reading select")).toBeNull();
  expect(document.querySelector("#panel-reading .analysis-context")).toBeNull();
  expect(document.querySelector("#panel-reading .analysis-actions")).toBeNull();
  expect(document.querySelector("#panel-reading")?.textContent).not.toContain("Corte de información");
  expect(document.querySelector("#panel-reading")?.textContent).not.toContain("Lectura ejecutiva ·");
  expect(document.getElementById("executive-reading-title")?.textContent).toBe(replacement
    ? approved("INDUSTRY", "2026Q3")!.thesis.replace(/^Industria:\s*/i, "")
    : "Mayores ingresos, rentabilidad bajo presión");
  if (!replacement) {
    expect(items[0]?.querySelector("span strong")?.textContent).toBe("aumentaron sus ingresos");
    expect(items[1]?.querySelector("span strong")?.textContent).toContain("facturó US$1,619 millones");
    expect(items[2]?.querySelector("span strong")?.textContent).toContain("ingresos trimestrales a 695.8");
    expect(items[3]?.querySelector("span strong")?.textContent).toContain("ingresos trimestrales de 1,038.0");
  }
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
  expect(card.querySelectorAll("article")).toHaveLength(replacement ? 4 : 3);
  for (const entity of entities) {
    const source = approved(entity, "2026Q3");
    if (!source) { expect(card.querySelector(`[data-entity="${entity}"]`)).toBeNull(); continue; }
    const article = card.querySelector(`[data-entity="${entity}"]`)!;
    const paragraphs = [...article.querySelectorAll("section p")];
    expect(paragraphs.map(plain)).toEqual(source.sections.flatMap(section => section.paragraphs));
    expect(article.querySelectorAll("a.source-note").length).toBeGreaterThan(0);
    if (replacement) {
      const claims = source.sections.flatMap(section => section.claim_ids);
      for (const [index, paragraph] of paragraphs.entries()) {
        const claim = source.claims.find(claim => claim.claim_id === claims[index])!;
        expect([...paragraph.querySelectorAll("a.source-note")].map(a => a.getAttribute("href")).sort())
          .toEqual(claim.citations.map(citation => citation.href).sort());
      }
    }
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
    for (const entity of entities) {
      const source = approved(entity, period);
      const article = document.querySelector(`#reading-full-copy [data-entity="${entity}"]`);
      if (source) {
        expect(article).not.toBeNull();
        expect([...article!.querySelectorAll("section p")].map(plain)).toEqual(source.sections.flatMap(section => section.paragraphs));
        expect(article!.querySelector("h3")?.textContent).toContain(source.thesis);
      } else expect(article).toBeNull();
      const previous = approved(entity, period === "2026Q3" ? "2026Q2" : "2026Q3");
      if (previous && previous.sections[0]!.paragraphs[0] !== source?.sections[0]?.paragraphs[0]) {
        expect(article?.textContent ?? "").not.toContain(previous.sections[0]!.paragraphs[0]);
      }
    }
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
