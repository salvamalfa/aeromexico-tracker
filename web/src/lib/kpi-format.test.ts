import { expect, it } from "vitest";
import { formatKpiComparison, formatKpiNumber } from "./kpi-format";

it("shows one decimal for measured values and scaled millions, and integers for counts", () => {
  expect(formatKpiNumber(8.149, { suffix: " ¢ USD" })).toBe("8.1 ¢ USD");
  expect(formatKpiNumber(12, { suffix: " M" })).toBe("12.0 M");
  expect(formatKpiNumber(1_234_567, { integer: true })).toBe("1,234,567");
  expect(formatKpiNumber(-0.149, { signed: true, suffix: " pp" })).toBe("-0.1 pp");
});

it("keeps missing values unavailable instead of turning them into zero", () => {
  for (const value of [null, undefined, NaN, Infinity, "3.4"]) {
    expect(formatKpiNumber(value)).toBe("No disponible");
  }
  expect(formatKpiNumber(null, { missing: "N/D" })).toBe("N/D");
  expect(formatKpiNumber(0)).toBe("0.0");
});

it("rounds comparisons from raw precision, preserving percent, cents, points and industry-share conventions", () => {
  expect(formatKpiComparison({available:true,raw:0.149,display:"+0.15 ¢ USD"})).toBe("+0.1 ¢ USD");
  expect(formatKpiComparison({available:true,raw:-0.01249,display:"-1.2%"})).toBe("-1.2%");
  expect(formatKpiComparison({available:true,raw:1.249,display:"+1.2 pp"})).toBe("+1.2 pp");
  expect(formatKpiComparison({available:true,raw:0.12449,display:"12.4% de la industria"})).toBe("12.4% de la industria");
  expect(formatKpiComparison({available:false,raw:null,display:"No disponible"})).toBe("No disponible");
  expect(formatKpiComparison({available:true,display:"-0.28 ¢ USD"})).toBe("-0.3 ¢ USD");
});
