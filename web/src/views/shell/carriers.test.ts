import { afterEach, describe, expect, it, vi } from "vitest";
import { mountPicker, parseSelection, selection, serializeSelection } from "./carriers";

describe("airline selection state", () => {
  afterEach(() => window.history.replaceState(null, "", "/"));
  it("falls back to the card defaults when the URL has no valid entity", () => {
    expect(parseSelection(null, true, ["INDUSTRY"])).toEqual(["INDUSTRY"]);
    expect(parseSelection("NOPE,ALSO_NOPE", true, ["AEROMEXICO"])).toEqual(["AEROMEXICO"]);
  });

  it("keeps the canonical order and drops unknown keys", () => {
    expect(parseSelection("VIVA_AEROBUS,foo,INDUSTRY", true, ["AEROMEXICO"])).toEqual(["INDUSTRY", "VIVA_AEROBUS"]);
  });

  it("keeps only the first entity on single-choice cards", () => {
    expect(parseSelection("VOLARIS,VIVA_AEROBUS", false, ["INDUSTRY"])).toEqual(["VOLARIS"]);
  });

  it("round-trips through the URL encoding", () => {
    const keys = parseSelection(serializeSelection(["VIVA_AEROBUS", "AEROMEXICO"]), true, ["INDUSTRY"]);
    expect(keys).toEqual(["AEROMEXICO", "VIVA_AEROBUS"]);
  });

  it("reads the entity deep link for the reading card and updates the alias on selection", () => {
    window.history.replaceState(null, "", "/?entity=VIVA_AEROBUS&period=2026Q2");
    const host = document.createElement("div");
    const listener = vi.fn();
    expect(mountPicker(host, { card: "reading", multi: false, defaults: ["AEROMEXICO"] }, listener)).toEqual(["VIVA_AEROBUS"]);
    const select = host.querySelector("select")!;
    select.value = "INDUSTRY"; select.dispatchEvent(new Event("change"));
    expect(selection("reading")).toEqual(["INDUSTRY"]);
    expect(new URLSearchParams(window.location.search).get("entity")).toBe("INDUSTRY");
    expect(new URLSearchParams(window.location.search).get("period")).toBe("2026Q2");
  });

  it("preserves canonical card selection precedence and ignores invalid entity aliases", () => {
    const host = document.createElement("div");
    window.history.replaceState(null, "", "/?entity=VIVA_AEROBUS&sel_reading=VOLARIS");
    expect(mountPicker(host, { card: "reading", multi: false, defaults: ["AEROMEXICO"] }, vi.fn())).toEqual(["VOLARIS"]);
    window.history.replaceState(null, "", "/?entity=../../escape");
    expect(mountPicker(host, { card: "reading", multi: false, defaults: ["AEROMEXICO"] }, vi.fn())).toEqual(["AEROMEXICO"]);
    window.history.replaceState(null, "", "/?entity=VIVA_AEROBUS");
    expect(mountPicker(host, { card: "kpis", multi: false, defaults: ["INDUSTRY"] }, vi.fn())).toEqual(["INDUSTRY"]);
  });
});
