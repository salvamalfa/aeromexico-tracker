import { describe, expect, it } from "vitest";
import { parseSelection, serializeSelection } from "./carriers";

describe("airline selection state", () => {
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
});
