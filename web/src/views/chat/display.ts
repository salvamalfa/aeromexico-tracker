import type { ChatDisplay, ChatDisplayColumn, ChatReference } from "../../types/chat";
import { parseSafeChart, renderSafeChart } from "./chart";

const VALUE_KINDS = new Set([
  "reported", "observed", "calculated", "inferred", "estimated", "scheduled", "mixed",
  "derived_sum_of_reported_quarters", "candidate_unapproved", "missing",
]);
const DISPLAY_ID = /^(tabla|grafica):[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/;
const TRUSTED_HOSTS = new Set(["sec.gov", "www.sec.gov", "ir.aeromexico.com", "gob.mx", "www.gob.mx", "github.com", "salvamalfa.github.io"]);

function parseSources(value: unknown): ChatReference[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.slice(0, 12).flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const source = item as Record<string, unknown>;
    if (typeof source.label !== "string" || !source.label.trim()) return [];
    const result: ChatReference = { label: source.label.slice(0, 200) };
    if (typeof source.url === "string") {
      try {
        const url = new URL(source.url);
        if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || !TRUSTED_HOSTS.has(url.hostname.toLowerCase())) return [];
        if (seen.has(url.href)) return [];
        seen.add(url.href);
        result.url = url.href;
      } catch { return []; }
    }
    return [result];
  });
}

function parseColumns(value: unknown): ChatDisplayColumn[] | undefined {
  if (!Array.isArray(value) || value.length < 1 || value.length > 12) return undefined;
  const keys = new Set<string>();
  const result: ChatDisplayColumn[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") return undefined;
    const column = item as Record<string, unknown>;
    if (typeof column.key !== "string" || !/^[A-Za-z0-9_.-]{1,80}$/.test(column.key) || keys.has(column.key) ||
      typeof column.label !== "string" || !column.label.trim()) return undefined;
    keys.add(column.key);
    result.push({ key: column.key, label: column.label.slice(0, 120), ...(typeof column.unit === "string" ? { unit: column.unit.slice(0, 60) } : {}) });
  }
  return result;
}

export function safeDisplays(value: unknown): ChatDisplay[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.slice(0, 12).flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const raw = item as Record<string, unknown>;
    const kind = raw.kind;
    if ((kind !== "table" && kind !== "chart") || typeof raw.display_id !== "string" || !DISPLAY_ID.test(raw.display_id) || seen.has(raw.display_id)) return [];
    if ((raw.display_id.startsWith("tabla:") ? "table" : "chart") !== kind || typeof raw.title !== "string" || !VALUE_KINDS.has(String(raw.value_kind))) return [];
    const sources = parseSources(raw.sources);
    const result: ChatDisplay = {
      display_id: raw.display_id,
      kind,
      title: raw.title.slice(0, 200),
      value_kind: raw.value_kind as ChatDisplay["value_kind"],
      sources,
    };
    if (kind === "table") {
      const columns = parseColumns(raw.columns);
      if (!columns || !Array.isArray(raw.rows) || raw.rows.length > 100) return [];
      const keys = new Set(columns.map((column) => column.key));
      const rows = raw.rows.flatMap((value) => {
        if (!value || typeof value !== "object") return [];
        const row = value as Record<string, unknown>;
        const clean: Record<string, string | number | boolean | null> = {};
        for (const key of keys) {
          const cell = row[key];
          if (cell === null || typeof cell === "string" || typeof cell === "boolean") clean[key] = cell;
          else if (typeof cell === "number" && Number.isFinite(cell)) clean[key] = cell;
          else return [];
        }
        return [clean];
      });
      if (rows.length !== raw.rows.length) return [];
      result.columns = columns;
      result.rows = rows;
    } else {
      const chart = parseSafeChart(raw.chart);
      if (!chart) return [];
      result.chart = chart;
    }
    seen.add(raw.display_id);
    return [result];
  });
}

function formattedNumber(value: number, unit?: string): string {
  if (unit === "fraction") return `${new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value * 100)}%`;
  if (unit === "%") return `${new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value)}%`;
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

function renderSources(host: HTMLElement, sources: readonly ChatReference[], seenUrls: Set<string>): void {
  const unique = sources.filter((source) => !source.url || !seenUrls.has(source.url));
  for (const source of unique) if (source.url) seenUrls.add(source.url);
  if (!unique.length) return;
  const footer = document.createElement("p");
  footer.className = "chat-display-sources";
  footer.append(document.createTextNode("Fuente: "));
  unique.forEach((source, index) => {
    if (index) footer.append(document.createTextNode(" · "));
    if (source.url) {
      const link = document.createElement("a");
      link.href = source.url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = source.label;
      footer.append(link);
    } else footer.append(document.createTextNode(source.label));
  });
  host.append(footer);
}

export function renderDisplay(host: HTMLElement, display: ChatDisplay, seenUrls: Set<string>): boolean {
  const section = document.createElement("section");
  section.className = `chat-display chat-display-${display.kind}`;
  section.dataset.displayId = display.display_id;
  const heading = document.createElement("h4");
  heading.textContent = display.title;
  section.append(heading);
  if (display.value_kind === "estimated") {
    const badge = document.createElement("span");
    badge.className = "chat-display-estimated";
    badge.textContent = "Estimado";
    section.append(badge);
  }
  if (display.kind === "table" && display.columns && display.rows) {
    const wrapper = document.createElement("div");
    wrapper.className = "chat-table-wrap chat-reference-table-wrap";
    const table = document.createElement("table");
    const head = document.createElement("thead");
    const header = document.createElement("tr");
    for (const column of display.columns) {
      const th = document.createElement("th"); th.scope = "col"; th.textContent = column.label; header.append(th);
    }
    head.append(header);
    const body = document.createElement("tbody");
    for (const row of display.rows) {
      const tr = document.createElement("tr");
      for (const column of display.columns) {
        const td = document.createElement("td");
        const value = row[column.key];
        if (typeof value === "number") {
          td.className = "align-right";
          td.textContent = formattedNumber(value, column.unit);
        } else if (value === null || value === undefined) td.textContent = "—";
        else td.textContent = String(value);
        tr.append(td);
      }
      body.append(tr);
    }
    table.append(head, body); wrapper.append(table); section.append(wrapper);
  } else if (display.kind === "chart" && display.chart) {
    const chartHost = document.createElement("div");
    chartHost.className = "chat-answer-chart";
    chartHost.setAttribute("role", "img");
    chartHost.setAttribute("aria-label", display.title);
    section.append(chartHost);
    const chart = display.chart;
    const fraction = chart.unit === "fraction";
    const renderedChart = fraction ? {
      ...chart,
      title: "",
      unit: "%",
      series: chart.series.map((series) => ({
        ...series,
        y: series.y.map((value) => value === null ? null : value * 100),
      })),
    } : { ...chart, title: "" };
    if (!renderSafeChart(chartHost, renderedChart)) return false;
  } else return false;
  renderSources(section, display.sources, seenUrls);
  host.append(section);
  return true;
}
