import { describe, expect, it } from "vitest";
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
