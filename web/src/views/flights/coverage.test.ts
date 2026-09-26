import { describe, expect, it } from "vitest";
import { coverageMonths, shortSourceLabel } from "./coverage";
import type { Route } from "../../types/domain";

const route = (coverage_note: string): Route =>
  ({ coverage_note } as unknown as Route);

describe("coverageMonths", () => {
  it("counts an explicit 'Meses: 04, 05' list", () => {
    expect(coverageMonths(route("Meses: 04, 05"))).toBe(2);
  });
  it("counts a month range like 'abr-jun'", () => {
    expect(coverageMonths(route("Reportado abr-jun 2026"))).toBe(3);
  });
  it("counts a single named month as one", () => {
    expect(coverageMonths(route("Reportado en abril"))).toBe(1);
  });
  it("returns null when the note has no month information", () => {
    expect(coverageMonths(route(""))).toBeNull();
  });
});

describe("shortSourceLabel", () => {
  it("shortens a known source label", () => {
    expect(shortSourceLabel("Estados Unidos · BTS T-100")).toBe("BTS T-100");
  });
  it("passes through an unknown label unchanged", () => {
    expect(shortSourceLabel("Fuente desconocida")).toBe("Fuente desconocida");
  });
  it("returns an empty string for an undefined label", () => {
    expect(shortSourceLabel(undefined)).toBe("");
  });
});
