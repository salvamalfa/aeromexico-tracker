import { describe, expect, it } from "vitest";
import { renderSafeMarkdown, safeReferences } from "./markdown";
import { parseSafeChart } from "./chart";

describe("safe response rendering", () => {
  it("treats raw HTML as text and permits only safe https markdown links", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, `<img src=x onerror=alert(1)> [fuente](https://www.sec.gov/report) [mal](javascript:alert(1)) [phishing](https://www.sec.gov/forged)`, ["https://www.sec.gov/report"]);
    expect(host.querySelector("img")).toBeNull();
    expect(host.textContent).toContain("<img src=x onerror=alert(1)>");
    const links = [...host.querySelectorAll("a")];
    expect(links).toHaveLength(1);
    expect(links[0]?.rel).toBe("noopener noreferrer");
  });

  it("drops references with credentials or query strings and bounds the list", () => {
    const refs = safeReferences([
      { label: "ok", url: "https://www.gob.mx/afac/source" },
      { label: "secret", url: "https://www.gob.mx/?api_key=x" },
      { label: "credential", url: "https://user:pass@www.gob.mx/" },
      ...Array.from({ length: 14 }, (_, index) => ({ label: `r${index}` })),
    ]);
    expect(refs.length).toBe(12);
    expect(refs[0]?.url).toBe("https://www.gob.mx/afac/source");
    expect(refs[1]?.url).toBeUndefined();
  });

  it("accepts bounded bar and line chart shapes and rejects arbitrary Plotly options", () => {
    const value = { type: "line", title: "Tendencia", x: ["2026Q1", "2026Q2"], unit: "%", series: [{ name: "Ocupación", y: [0.7, null] }], layout: { annotations: [{ text: "x" }] } };
    expect(parseSafeChart(value)).toEqual({ type: "line", title: "Tendencia", x: ["2026Q1", "2026Q2"], unit: "%", series: [{ name: "Ocupación", y: [0.7, null] }] });
    expect(parseSafeChart({ ...value, type: "scatter3d" })).toBeUndefined();
    expect(parseSafeChart({ ...value, x: Array.from({ length: 101 }, (_, index) => index) })).toBeUndefined();
  });
});
