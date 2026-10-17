import { describe, expect, it } from "vitest";
import { coverageIndicator, coverageMonths, shortSourceLabel } from "./coverage";
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

it("uses the selected month's denominator for dated international observations", () => {
  expect(coverageIndicator(route("Meses: 01 · BTS T-100"), 1)).toEqual({
    variant: "is-full", title: "1 de 1 mes del periodo seleccionado con datos de la fuente",
  });
  expect(coverageIndicator(route("Meses: 04, 05 · BTS T-100"), 3)?.variant).toBe("is-partial");
});

it("keeps incomplete frequencies partial even within a complete calendar month", () => {
  const partial = { ...route("Meses: 07"), months_covered: 1, months_selected: 1,
    operation_status: "estimated_from_afac_margins_and_temporal_support_partial_frequencies" };
  expect(coverageIndicator(partial, 1)?.variant).toBe("is-partial");
});
