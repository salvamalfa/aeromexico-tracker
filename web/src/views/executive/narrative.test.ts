import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { applyCitations, citationsByClaim } from "./narrative";
import type { AnalysisCitation, AnalysisDocument } from "../../types/domain";

function citation(overrides: Partial<AnalysisCitation> = {}): AnalysisCitation {
  return {
    label: "1",
    href: "https://www.sec.gov/example#:~:text=foo",
    title: "Reporte original · foo",
    value: "12.3%",
    ...overrides,
  };
}

describe("applyCitations", () => {
  it("wraps the first occurrence of the value in <sup><a class=source-note>", () => {
    const li = document.createElement("li");
    li.textContent = "El margen fue de 12.3% en el trimestre.";
    applyCitations(li, [citation()]);
    const link = li.querySelector("a.source-note")!;
    expect(link.textContent).toBe("1");
    expect(link.getAttribute("href")).toBe("https://www.sec.gov/example#:~:text=foo");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.getAttribute("title")).toBe("Reporte original · foo");
    expect(link.getAttribute("aria-label")).toBe("Fuente 1: abrir dato original");
    expect(link.parentElement?.tagName).toBe("SUP");
    expect(li.textContent).toBe("El margen fue de 12.3%1 en el trimestre.");
  });

  it("wraps a value inside an already-emphasized <strong> run", () => {
    const p = document.createElement("p");
    p.innerHTML = "El <strong>margen fue de 12.3%</strong> en el trimestre.";
    applyCitations(p, [citation()]);
    expect(p.querySelector("strong a.source-note")).not.toBeNull();
  });

  it("applies multiple citations in order, each to the first remaining match", () => {
    const p = document.createElement("p");
    p.textContent = "RASK 5.5 y CASK 4.4 en el periodo.";
    applyCitations(p, [
      citation({ label: "1", value: "5.5" }),
      citation({ label: "2", value: "4.4", href: "https://ir.aeromexico.com/doc#:~:text=bar" }),
    ]);
    const links = [...p.querySelectorAll("a.source-note")];
    expect(links.map((a) => a.textContent)).toEqual(["1", "2"]);
  });

  it("never re-wraps text already inside a citation link or superscript", () => {
    const p = document.createElement("p");
    p.textContent = "12.3% y de nuevo 12.3% más adelante.";
    applyCitations(p, [citation(), citation({ label: "2" })]);
    const links = [...p.querySelectorAll("a.source-note")];
    expect(links).toHaveLength(2);
    expect(links[0]!.closest("sup")).not.toBe(links[1]!.closest("sup"));
  });

  it("leaves the text untouched when the citation's value is not present", () => {
    const p = document.createElement("p");
    p.textContent = "Sin ninguna cifra citable aquí.";
    applyCitations(p, [citation({ value: "99.9%" })]);
    expect(p.querySelector("sup")).toBeNull();
    expect(p.textContent).toBe("Sin ninguna cifra citable aquí.");
  });

  it("skips unsafe URLs and treats tooltip markup as literal text", () => {
    const p = document.createElement("p");
    p.textContent = "12.3%";
    applyCitations(p, [citation({ href: "javascript:alert(1)" }), citation({ href: "https://evil.example/file" })]);
    expect(p.querySelector("a")).toBeNull();
    applyCitations(p, [citation({ href: "https://cdn.investorcloud.net/VivaAerobus/2T26.pdf#page=7", title: '<img src=x onerror="alert(1)">' })]);
    expect(p.querySelector("a")?.title).toBe('<img src=x onerror="alert(1)">');
    expect(p.querySelector("img")).toBeNull();
  });
});

function analysis(entity = "AEROMEXICO", period = "2026Q2"): AnalysisDocument {
  return {
    period_id: period, version: `approved-${entity}-${period}`,
    ...(entity === "AEROMEXICO" ? {} : {
      entity_key: entity, period_label: "2T26 (abril–junio de 2026)", cutoff_date: "2026-10-13",
      selection_mode: "retrospective" as const, guidance_as_of: "report_date" as const,
    }),
    thesis: `Tesis ${entity} ${period}`,
    summary_items: [{ claim_id: "summary", text: `Resumen ${entity}: 12.3%`, lead: `Resumen ${entity}:`, emphasis: [] }],
    context: [], sections: [{ title: "Operación", paragraphs: [`Detalle ${entity}: 12.3%`], claim_ids: ["detail"] }],
    claims: [
      { claim_id: "summary", citations: [citation()] },
      { claim_id: "detail", citations: [citation({ href: "https://cdn.investorcloud.net/VivaAerobus/2T26.pdf#page=7" })] },
    ],
  };
}

const view = (period = "2026Q2") => ({ period_id: period, period_label: period, kpis: [], margin_qoq: { available: false, display: "", direction: "na" }, margin_yoy: { available: false, display: "", direction: "na" } });
const response = (payload: unknown, ok = true) => ({ ok, json: async () => payload }) as Response;

describe("entity narratives", () => {
  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = '<span id="narrative-period"></span><span id="narrative-entity"></span><div id="narrative-copy"></div><dialog id="analysis-full"><div class="bar"><h2></h2></div><div class="modal-content"></div></dialog>';
    const dialog = document.getElementById("analysis-full") as HTMLDialogElement;
    dialog.showModal = vi.fn(() => { dialog.open = true; });
    dialog.close = vi.fn(() => { dialog.open = false; });
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("switches all four entities, isolates caches and preserves the legacy Aero path", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const entity = /analysis\/(INDUSTRY|VOLARIS|VIVA_AEROBUS)\//.exec(url)?.[1] ?? "AEROMEXICO";
      return response(analysis(entity));
    });
    vi.stubGlobal("fetch", fetchMock);
    const { renderNarrative } = await import("./narrative");
    for (const [entity, label] of [["AEROMEXICO", "Aeroméxico"], ["VOLARIS", "Volaris"], ["VIVA_AEROBUS", "Viva"], ["INDUSTRY", "Industria"]]) {
      await renderNarrative(view(), entity, label);
      expect(document.getElementById("narrative-copy")?.textContent).toContain(`Tesis ${entity}`);
      expect(document.getElementById("narrative-copy")?.dataset.entity).toBe(entity);
      document.getElementById("analysis-open-full")!.click();
      expect(document.querySelector(".modal-content")?.textContent).toContain(`Detalle ${entity}`);
      expect(document.querySelector(".modal-content a")?.getAttribute("href")).toContain("2T26.pdf#page=7");
      expect(document.querySelector(".bar h2")?.textContent).toBe(entity === "AEROMEXICO" ? "Análisis completo · 2026Q2" : `Análisis completo · ${label} · 2T26 (abril–junio de 2026)`);
      expect(document.getElementById("narrative-copy")?.textContent?.includes("Análisis retrospectivo")).toBe(entity !== "AEROMEXICO");
    }
    await renderNarrative(view(), "AEROMEXICO");
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "data/v1/analysis/2026Q2.json", "data/v1/analysis/VOLARIS/2026Q2.json",
      "data/v1/analysis/VIVA_AEROBUS/2026Q2.json", "data/v1/analysis/INDUSTRY/2026Q2.json",
    ]);
  });

  it("rejects wrong entity, period, version and malformed arrays without Aero fallback", async () => {
    const { validAnalysis, renderNarrative } = await import("./narrative");
    expect(validAnalysis(analysis(), "VOLARIS", "2026Q2")).toBe(false);
    expect(validAnalysis(analysis("VOLARIS", "2026Q1"), "VOLARIS", "2026Q2")).toBe(false);
    expect(validAnalysis({ ...analysis("VOLARIS"), version: "" }, "VOLARIS", "2026Q2")).toBe(false);
    expect(validAnalysis({ ...analysis("VOLARIS"), cutoff_date: "2026-02-31" }, "VOLARIS", "2026Q2")).toBe(false);
    expect(validAnalysis({ ...analysis("VOLARIS"), sections: [{ title: "x", paragraphs: ["a"], claim_ids: [] }] }, "VOLARIS", "2026Q2")).toBe(false);
    expect(validAnalysis({ ...analysis("VOLARIS"), context: null }, "VOLARIS", "2026Q2")).toBe(false);
    expect(validAnalysis({ ...analysis(), entity_key: null }, "AEROMEXICO", "2026Q2")).toBe(false);
    const fetchMock = vi.fn(async () => response(analysis()));
    vi.stubGlobal("fetch", fetchMock);
    await renderNarrative(view(), "VOLARIS", "Volaris");
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith("data/v1/analysis/VOLARIS/2026Q2.json");
    expect(document.getElementById("analysis-empty")).not.toBeNull();
    expect(document.getElementById("analysis-open-full")).toBeNull();
  });

  it("shows current-period metadata and renders business text without interpreting HTML", async () => {
    const payload = analysis("VIVA_AEROBUS");
    payload.summary_items[0]!.text = '<img src=x onerror="x"> 12.3%';
    vi.stubGlobal("fetch", vi.fn(async () => response(payload)));
    const { renderNarrative } = await import("./narrative");
    await renderNarrative(view(), "VIVA_AEROBUS", "Viva");
    expect(document.getElementById("narrative-period")?.textContent).toBe("2T26 (abril–junio de 2026)");
    expect(document.getElementById("narrative-copy")?.textContent).toContain("Corte de información: 13 de octubre de 2026");
    expect(document.querySelector("#narrative-copy img")).toBeNull();
    expect(document.querySelector("#narrative-copy li")?.textContent).toContain('<img src=x onerror="x">');
  });

  it("ignores slower responses after both entity and period switches", async () => {
    let release!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("analysis/2026Q1.json") ? new Promise<Response>((resolve) => { release = resolve; }) : Promise.resolve(response(analysis("VIVA_AEROBUS")))));
    const { renderNarrative } = await import("./narrative");
    const stale = renderNarrative(view("2026Q1"), "AEROMEXICO", "Aeroméxico");
    await renderNarrative(view(), "VIVA_AEROBUS", "Viva");
    release(response(analysis("AEROMEXICO", "2026Q1")));
    await stale;
    expect(document.getElementById("narrative-copy")?.textContent).toContain("Tesis VIVA_AEROBUS");
    expect(document.getElementById("narrative-period")?.textContent).toBe("2T26 (abril–junio de 2026)");
    expect(document.getElementById("narrative-entity")?.textContent).toBe("Viva");
  });

  it("closes an open modal and removes old body while a new selection loads", async () => {
    let release!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn((url: string) => url.includes("/VOLARIS/") ? new Promise<Response>((resolve) => { release = resolve; }) : Promise.resolve(response(analysis()))));
    const { renderNarrative } = await import("./narrative");
    await renderNarrative(view());
    document.getElementById("analysis-open-full")!.click();
    const dialog = document.getElementById("analysis-full") as HTMLDialogElement;
    expect(dialog.open).toBe(true);
    const pending = renderNarrative(view(), "VOLARIS", "Volaris");
    expect(dialog.open).toBe(false);
    expect(dialog.querySelector(".modal-content")?.textContent).toBe("");
    expect(document.getElementById("narrative-copy")?.textContent).not.toContain("AEROMEXICO");
    release(response(null, false)); await pending;
    expect(document.getElementById("analysis-empty")).not.toBeNull();
  });

  it("isolates cache entries by period and data root and handles offline errors", async () => {
    const fetchMock = vi.fn(async (url: string) => response(analysis("AEROMEXICO", url.includes("2026Q1") ? "2026Q1" : "2026Q2")));
    vi.stubGlobal("fetch", fetchMock);
    const { renderNarrative } = await import("./narrative");
    const { state } = await import("./state");
    await renderNarrative(view()); await renderNarrative(view("2026Q1"));
    state.dataRoot = "other/data/v1"; await renderNarrative(view());
    expect(fetchMock).toHaveBeenCalledTimes(3);
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    await renderNarrative(view(), "INDUSTRY", "Industria");
    expect(document.getElementById("analysis-empty")).not.toBeNull();
  });
});

describe("citationsByClaim", () => {
  it("indexes each claim's citations by claim_id", () => {
    const analysis = {
      claims: [
        { claim_id: "a", citations: [citation()] },
        { claim_id: "b", citations: [] },
      ],
    } as unknown as AnalysisDocument;
    const map = citationsByClaim(analysis);
    expect(map.get("a")).toHaveLength(1);
    expect(map.get("b")).toEqual([]);
    expect(map.get("missing")).toBeUndefined();
  });
});
