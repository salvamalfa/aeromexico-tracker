import { describe, expect, it } from "vitest";
import { renderSafeMarkdown, safeReferences } from "./markdown";
import { parseSafeChart } from "./chart";

describe("safe response rendering", () => {
  it("renders same-turn reference tables and combines labels for duplicate source URLs", () => {
    const host = document.createElement("div");
    const market = {
      display_id: "tabla:market_2026", kind: "table", title: "Participación total, 2T26", value_kind: "estimated",
      columns: [{ key: "airline", label: "Aerolínea" }, { key: "share", label: "2T26", unit: "fraction" }],
      rows: [{ airline: "Volaris", share: 0.366615816786413 }, { airline: "Grupo Aeroméxico", share: null }],
      sources: [
        { label: "AFAC, estadística mensual, junio 2026", url: "https://www.gob.mx/afac/source" },
        { label: "AFAC duplicada", url: "https://www.gob.mx/afac/source" },
      ],
    };
    renderSafeMarkdown(host, "Participación: {{tabla:market_2026}}", [], [market]);
    expect(host.querySelector(".chat-display-kind")?.textContent).toBe("Estimado");
    expect([...host.querySelectorAll("tbody td")].map((cell) => cell.textContent)).toEqual(["Volaris", "36.7%", "Grupo Aeroméxico", "—"]);
    expect([...host.querySelectorAll(".chat-display-sources a")].map((link) => link.textContent)).toEqual([
      "AFAC, estadística mensual, junio 2026 · AFAC duplicada",
    ]);
    expect(host.textContent).not.toContain("{{tabla:");
  });

  it("keeps verified financial and reporting citations clickable", () => {
    const host = document.createElement("div");
    const display = {
      display_id: "tabla:financial_sources", kind: "table", title: "Resultados", value_kind: "reported",
      columns: [{ key: "value", label: "Valor" }], rows: [{ value: 1 }],
      sources: [
        { label: "Aeroméxico IR", url: "https://ir.aeromexico.com/report-q2.pdf" },
        { label: "Viva InvestorCloud", url: "https://cdn.investorcloud.net/viva/report-q2.pdf" },
        { label: "FlightGlobal", url: "https://www.flightglobal.com/news/article.html" },
        { label: "BMV · miembro ZIP q1.json", url: "https://www.bmv.com.mx/docs-pub/ifrsxbrl/package.zip" },
        { label: "BMV · miembro ZIP q2.json", url: "https://www.bmv.com.mx/docs-pub/ifrsxbrl/package.zip" },
        { label: "No verificada", url: "https://example.org/article" },
      ],
    };
    renderSafeMarkdown(host, "{{tabla:financial_sources}}", [], [display]);
    expect([...host.querySelectorAll<HTMLAnchorElement>(".chat-display-sources a")].map((link) => link.hostname)).toEqual([
      "ir.aeromexico.com", "cdn.investorcloud.net", "www.flightglobal.com", "www.bmv.com.mx",
    ]);
    expect(host.querySelector(".chat-display-sources a:last-child")?.textContent).toBe("BMV · miembro ZIP q1.json · BMV · miembro ZIP q2.json");
    expect(host.textContent).not.toContain("No verificada");
  });

  it("labels calculated values and blocks values behind a closed approval gate", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, "{{tabla:calculated}}", [], [
      {
        display_id: "tabla:calculated", kind: "table", title: "Margen unitario", value_kind: "calculated",
        columns: [{ key: "value", label: "Margen", unit: "USD_cents_per_ASK_km" }], rows: [{ value: 0.43 }], sources: [],
      },
    ]);
    expect(host.querySelector(".chat-display-kind")?.textContent).toBe("Calculado");

    renderSafeMarkdown(host, "{{tabla:blocked}}", [], [
      {
        display_id: "tabla:blocked", kind: "table", title: "Candidato", value_kind: "candidate_unapproved",
        columns: [{ key: "value", label: "Valor" }], rows: [{ value: 100 }], sources: [],
      },
    ]);
    expect(host.querySelector("table")).toBeNull();
    expect(host.textContent).toBe("");
  });

  it("removes missing and mismatched display markers without drawing artifacts", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, "{{tabla:unknown}} {{grafica:unknown}}", [], [
      { display_id: "tabla:wrong", kind: "table", title: "Tabla", value_kind: "reported", columns: [{ key: "x", label: "X" }], rows: [{ x: 1 }] },
    ]);
    expect(host.textContent).toBe("");
    expect(host.querySelector("table, .chat-answer-chart")).toBeNull();
  });

  it("treats raw HTML as text and permits only safe https markdown links", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, `<img src=x onerror=alert(1)> [fuente](https://www.sec.gov/report) [mal](javascript:alert(1)) [phishing](https://www.sec.gov/forged)`, ["https://www.sec.gov/report"]);
    expect(host.querySelector("img")).toBeNull();
    expect(host.textContent).toContain("<img src=x onerror=alert(1)>");
    const links = [...host.querySelectorAll("a")];
    expect(links).toHaveLength(1);
    expect(links[0]?.rel).toBe("noopener noreferrer");
  });

  it("renders bold, ordered and unordered lists, quotations, and fenced code as inert markup", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, [
      "**Negritas** y `código inline`.",
      "",
      "1. Primer paso",
      "2. Segundo paso",
      "",
      "- Una opción",
      "- Otra opción",
      "",
      "> Cita visible",
      "",
      "```html",
      "<script>window.__reviewXss=true</script>",
      "```",
    ].join("\n"));
    expect(host.querySelector("strong")?.textContent).toBe("Negritas");
    expect(host.querySelector("p code")?.textContent).toBe("código inline");
    expect(host.querySelectorAll("ol li")).toHaveLength(2);
    expect(host.querySelectorAll("ul li")).toHaveLength(2);
    expect(host.querySelector("blockquote")?.textContent).toBe("Cita visible");
    expect(host.querySelector("pre code")?.textContent).toBe("<script>window.__reviewXss=true</script>");
    expect(host.querySelector("script")).toBeNull();
    expect(host.textContent).toContain("window.__reviewXss=true");
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

  it("keeps an escaped pipe at the end of a cell", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, "a | b\n---|---\nx | RASK \\|");
    expect([...host.querySelectorAll("td")].map((cell) => cell.textContent)).toEqual(["x", "RASK |"]);
  });

  it("keeps blank-separated borderless prose out of the table", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, "A | B\n---|---\nVolaris | 36.7%\n\nVolaris | ganó 0.8 pp.");
    expect(host.querySelectorAll("tbody tr")).toHaveLength(1);
    expect(host.querySelector("p")?.textContent).toBe("Volaris | ganó 0.8 pp.");

    renderSafeMarkdown(host, "| A | B |\n|---|---|\n| 1 | 2 |\n\n| Fuente: AFAC |");
    expect(host.querySelectorAll("tbody tr")).toHaveLength(1);
    expect(host.querySelector("p")?.textContent).toBe("| Fuente: AFAC |");
  });

  it("treats a pipe after an escaped backslash as a delimiter", () => {
    const host = document.createElement("div");
    renderSafeMarkdown(host, "Ruta | Valor\n---|---\nC:\\\\| 5\n| a \\| b | 6 |");
    const rows = [...host.querySelectorAll("tbody tr")].map((row) => [...row.querySelectorAll("td")].map((cell) => cell.textContent));
    expect(rows).toEqual([["C:\\", "5"], ["a | b", "6"]]);
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

  it("merges citation labels by canonical URL", () => {
    expect(safeReferences([
      { label: "AFAC", url: "https://www.gob.mx/afac/source" },
      { label: "AFAC, junio", url: "https://www.gob.mx/afac/source" },
    ])).toEqual([{ label: "AFAC · AFAC, junio", url: "https://www.gob.mx/afac/source" }]);
  });

  it("accepts bounded bar and line chart shapes and rejects arbitrary Plotly options", () => {
    const value = { type: "line", title: "Tendencia", x: ["2026Q1", "2026Q2"], unit: "%", series: [{ name: "Ocupación", y: [0.7, null] }], layout: { annotations: [{ text: "x" }] } };
    expect(parseSafeChart(value)).toEqual({ type: "line", title: "Tendencia", x: ["2026Q1", "2026Q2"], unit: "%", series: [{ name: "Ocupación", y: [0.7, null] }] });
    expect(parseSafeChart({ ...value, type: "scatter3d" })).toBeUndefined();
    expect(parseSafeChart({ ...value, x: Array.from({ length: 101 }, (_, index) => index) })).toBeUndefined();
  });
});
