import { describe, expect, it } from "vitest";
import { deltaDisplay, esc, finite, formatRouteMetric, metricDisplay, priorPeriod } from "./dom";

describe("finite", () => {
  it("accepts only finite numbers", () => {
    expect(finite(1)).toBe(true);
    expect(finite(0)).toBe(true);
    expect(finite(Number.NaN)).toBe(false);
    expect(finite(Infinity)).toBe(false);
    expect(finite(null)).toBe(false);
    expect(finite(undefined)).toBe(false);
    expect(finite("1")).toBe(false);
  });
});

describe("esc", () => {
  it("escapes HTML-sensitive characters", () => {
    expect(esc(`<a href="x">'&'</a>`)).toBe("&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
  });
  it("stringifies nullish values as empty string", () => {
    expect(esc(null)).toBe("");
    expect(esc(undefined)).toBe("");
  });
});

describe("metricDisplay", () => {
  it("shows 'No disponible' for non-finite values", () => {
    expect(metricDisplay("passengers", null)).toBe("No disponible");
    expect(metricDisplay("passengers", Number.NaN)).toBe("No disponible");
  });
  it("formats load_factor as a percentage", () => {
    expect(metricDisplay("load_factor", 0.812)).toBe("81.2%");
  });
  it("formats passengers in millions with 3 decimals", () => {
    expect(metricDisplay("passengers", 1_234_567)).toBe("1.235 M");
  });
  it("formats other metrics (asm_miles/rpm_miles) in thousand-millions", () => {
    expect(metricDisplay("asm_miles", 2_345_000_000)).toBe("2.345 mil M");
  });
});

describe("formatRouteMetric", () => {
  it("returns N/D for non-finite values", () => {
    expect(formatRouteMetric("seats", null)).toBe("N/D");
  });
  it("formats load_factor as a percentage", () => {
    expect(formatRouteMetric("load_factor", 0.5)).toBe("50.0%");
  });
  it("formats other metrics as an integer", () => {
    expect(formatRouteMetric("seats", 1234.6)).toBe("1,235");
  });
});

describe("priorPeriod", () => {
  it("steps back one quarter within the same year", () => {
    expect(priorPeriod("2026Q3")).toBe("2026Q2");
  });
  it("wraps to Q4 of the previous year from Q1", () => {
    expect(priorPeriod("2026Q1")).toBe("2025Q4");
  });
  it("steps back N years for the same quarter (year-over-year)", () => {
    expect(priorPeriod("2026Q3", 1)).toBe("2025Q3");
  });
});

describe("deltaDisplay", () => {
  it("is unavailable when either value is missing", () => {
    expect(deltaDisplay(null, 10).text).toBe("No disponible");
    expect(deltaDisplay(10, null).text).toBe("No disponible");
  });
  it("is unavailable dividing by a zero baseline unless using points", () => {
    expect(deltaDisplay(10, 0).text).toBe("No disponible");
    expect(deltaDisplay(0.1, 0, true).text).not.toBe("No disponible");
  });
  it("computes a percentage delta and direction", () => {
    const up = deltaDisplay(110, 100);
    expect(up.text).toBe("+10.0%");
    expect(up.className).toBe("delta-up");
    const down = deltaDisplay(90, 100);
    expect(down.text).toBe("-10.0%");
    expect(down.className).toBe("delta-down");
  });
  it("computes a percentage-point delta when points=true", () => {
    const change = deltaDisplay(0.82, 0.80, true);
    expect(change.text).toBe("+2.0 pp");
    expect(change.className).toBe("delta-up");
  });
  it("treats a tiny delta as unchanged (delta-na)", () => {
    expect(deltaDisplay(100.001, 100).className).toBe("delta-na");
  });
});
