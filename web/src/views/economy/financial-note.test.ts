import { describe, it, expect, beforeEach } from "vitest";
import { state } from "../executive/state";
import { renderFinancialNote } from "./financial-note";

describe("scoped financial comparison note", () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="financial-comparison-note" hidden></div>';
    state.views = { "2026Q3": { period_id: "2026Q3", period_label: "3T26", kpis: [], margin_qoq: {available:false,display:"",direction:"na"}, margin_yoy: {available:false,display:"",direction:"na"}, narrative: {headline:"Bases",paragraphs:["TRASM total / ASM convertido por 1,609344", "<img src=x onerror=alert(1)>"]} } };
  });
  it("explains the new Aero quarter with text-safe source notes", () => {
    renderFinancialNote("AEROMEXICO", "2026Q3");
    const host = document.getElementById("financial-comparison-note")!;
    expect(host.hidden).toBe(false);
    expect(host.querySelectorAll("details p")).toHaveLength(2);
    expect(host.textContent).toContain("1,609344");
    expect(host.querySelector("img")).toBeNull();
    expect(host.querySelector("a")?.getAttribute("rel")).toBe("noopener noreferrer");
  });
  it("does not attach Aero values or source claims to a missing peer quarter", () => {
    renderFinancialNote("VOLARIS", "2026Q3");
    expect(document.getElementById("financial-comparison-note")?.textContent).toContain("No disponible");
    expect(document.querySelector("#financial-comparison-note details")).toBeNull();
  });
  it("preserves previous-quarter presentation", () => {
    renderFinancialNote("AEROMEXICO", "2026Q2");
    expect(document.getElementById("financial-comparison-note")?.hidden).toBe(true);
    expect(document.getElementById("financial-comparison-note")?.textContent).toBe("");
  });
});
