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

  it("renders model-written tables as real tables, also with blank lines between rows", () => {
    const host = document.createElement("div");
    const answer = [
      "Tomando pasajeros nacionales e internacionales juntos:",
      "",
      "| Aerolínea | 1T26 | 2T26 |",
      "",
      "|---|---:|---:|",
      "",
      "| **Volaris** | 35.9% | 36.7% |",
      "",
      "| Grupo Aeroméxico | 29.5% | 29.1% |",
      "",
      "Volaris gana participación.",
    ].join("\n");
    renderSafeMarkdown(host, answer);
    const table = host.querySelector(".chat-table-wrap table");
    expect(table).not.toBeNull();
    expect([...table!.querySelectorAll("th")].map((cell) => cell.textContent)).toEqual(["Aerolínea", "1T26", "2T26"]);
    const rows = [...table!.querySelectorAll("tbody tr")];
    expect(rows).toHaveLength(2);
    expect(rows[0]!.querySelector("strong")?.textContent).toBe("Volaris");
    expect(rows[1]!.querySelectorAll("td")[2]?.className).toBe("align-right");
    expect(host.querySelectorAll("p")).toHaveLength(2);
    expect(host.textContent).not.toContain("|---");
  });

  it("splits consecutive tables and consumes rows past the limit", () => {
    const host = document.createElement("div");
    const second = "| x | y |\n|---|---|\n| 1 | 2 |";
    renderSafeMarkdown(host, `| a | b |\n|---|---|\n| 1 | 2 |\n\n${second}`);
    const tables = host.querySelectorAll("table");
    expect(tables).toHaveLength(2);
    expect(tables[0]!.querySelectorAll("tbody tr")).toHaveLength(1);
    expect(host.textContent).not.toContain("---");

    const long = ["| n | v |", "|---|---|", ...Array.from({ length: 65 }, (_, i) => `| ${i} | x |`), "", "Fin."].join("\n");
    renderSafeMarkdown(host, long);
    expect(host.querySelectorAll("tbody tr")).toHaveLength(60);
    expect(host.textContent).not.toContain("| 64 |");
    expect(host.textContent).toContain("se omitieron 5");
    expect([...host.querySelectorAll(":scope > p")].map((p) => p.textContent)).toEqual(["Fin."]);
  });

  it("accepts GFM tables without leading pipes", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, "A | B\n---|---\n1 | 2\n3 | 4\n\nTexto con a | b | c.");
    expect(host.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(host.querySelector("th")?.textContent).toBe("A");
    expect(host.querySelector("p")?.textContent).toBe("Texto con a | b | c.");
  });

  it("keeps the last row when a markdown divider follows the table", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\n---\n\nFin.");
    expect(host.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(host.textContent).not.toContain("| 3 |");
  });

  it("keeps pipes inside ordinary text and HTML-looking cells as plain text", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, "Opción A | opción B\n\n| a | b |\n|---|---|\n| <img src=x onerror=alert(1)> | ok |");
    expect(host.querySelector("p")?.textContent).toBe("Opción A | opción B");
    expect(host.querySelector("img")).toBeNull();
    expect(host.querySelector("td")?.textContent).toBe("<img src=x onerror=alert(1)>");
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
