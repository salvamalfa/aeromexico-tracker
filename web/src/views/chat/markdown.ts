import type { ChatChart, ChatMessage, ChatReference } from "../../types/chat";

const TRUSTED_HOSTS = new Set([
  "sec.gov", "www.sec.gov", "ir.aeromexico.com", "gob.mx", "www.gob.mx",
  "github.com", "salvamalfa.github.io",
]);

function trustedSourceUrl(raw: string): string | undefined {
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:" || url.username || url.password || url.search || !TRUSTED_HOSTS.has(url.hostname.toLowerCase())) return undefined;
    return url.href;
  } catch { return undefined; }
}

function appendInline(parent: HTMLElement, raw: string, allowedUrls: ReadonlySet<string>): void {
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let cursor = 0;
  for (const match of raw.matchAll(pattern)) {
    const index = match.index ?? 0;
    parent.append(document.createTextNode(raw.slice(cursor, index)));
    const token = match[0];
    if (token.startsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = token.slice(2, -2);
      parent.append(strong);
    } else if (token.startsWith("*")) {
      const em = document.createElement("em");
      em.textContent = token.slice(1, -1);
      parent.append(em);
    } else {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/)!;
      const safeUrl = trustedSourceUrl(link[2]!);
      if (safeUrl && allowedUrls.has(safeUrl)) {
        const anchor = document.createElement("a");
        anchor.href = safeUrl;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        anchor.textContent = link[1]!;
        parent.append(anchor);
      } else parent.append(document.createTextNode(link[1]!));
    }
    cursor = index + token.length;
  }
  parent.append(document.createTextNode(raw.slice(cursor)));
}

const TABLE_SEPARATOR = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;
const MAX_TABLE_COLUMNS = 12;
const MAX_TABLE_ROWS = 60;

function tableCells(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split(/(?<!\\)\|/).map((cell) => cell.replace(/\\\|/g, "|").trim());
}

/** Parse a GitHub-style table starting at `start`; returns the element and the next line index. */
function parseTable(lines: readonly string[], start: number, allowedUrls: ReadonlySet<string>): [HTMLElement, number] | null {
  // Models sometimes leave blank lines between table rows; skip them.
  const nextLine = (from: number): number => {
    let index = from;
    while (index < lines.length && !lines[index]!.trim()) index += 1;
    return index;
  };
  const header = lines[start]!;
  const separatorIndex = nextLine(start + 1);
  const separator = lines[separatorIndex];
  // The leading pipe is optional in GFM; the separator and equal column counts mark a table.
  if (!header.includes("|") || separator === undefined || !TABLE_SEPARATOR.test(separator)) return null;
  const headings = tableCells(header);
  const aligns = tableCells(separator).map((cell) =>
    cell.endsWith(":") ? (cell.startsWith(":") ? "center" : "right") : "left");
  if (headings.length < 2 || headings.length > MAX_TABLE_COLUMNS || aligns.length !== headings.length) return null;
  const rows: string[][] = [];
  let index = separatorIndex + 1;
  let hidden = 0;
  for (let next = nextLine(index); next < lines.length; next = nextLine(index)) {
    const candidate = lines[next]!.trim();
    if (!candidate.startsWith("|") && (!candidate.includes("|") || tableCells(candidate).length !== headings.length)) break;
    // A header followed by its separator starts the next table.
    const after = lines[nextLine(next + 1)];
    if (after !== undefined && TABLE_SEPARATOR.test(after)) break;
    // Rows past the limit are consumed, not rendered, so they never leak out as pipe text.
    if (rows.length < MAX_TABLE_ROWS) rows.push(tableCells(lines[next]!));
    else hidden += 1;
    index = next + 1;
  }
  const table = document.createElement("table");
  const row = (cells: readonly string[], tag: "th" | "td"): HTMLTableRowElement => {
    const tr = document.createElement("tr");
    headings.forEach((_, column) => {
      const cell = document.createElement(tag);
      if (aligns[column] !== "left") cell.className = `align-${aligns[column]}`;
      if (tag === "th") cell.scope = "col";
      appendInline(cell, cells[column] ?? "", allowedUrls);
      tr.append(cell);
    });
    return tr;
  };
  const thead = document.createElement("thead");
  thead.append(row(headings, "th"));
  const tbody = document.createElement("tbody");
  for (const cells of rows) tbody.append(row(cells, "td"));
  table.append(thead, tbody);
  // Narrow screens scroll the table sideways instead of squeezing every column.
  const wrap = document.createElement("div");
  wrap.className = "chat-table-wrap";
  wrap.append(table);
  if (hidden) {
    const note = document.createElement("p");
    note.textContent = `Se muestran ${MAX_TABLE_ROWS} filas; se omitieron ${hidden}.`;
    wrap.append(note);
  }
  return [wrap, index];
}

export function renderSafeMarkdown(container: HTMLElement, source: string, allowedUrls: readonly string[] = []): void {
  container.replaceChildren();
  const trustedUrls = new Set(allowedUrls.flatMap((raw) => {
    const url = trustedSourceUrl(raw);
    return url ? [url] : [];
  }));
  const lines = source.replace(/\r/g, "").split("\n");
  let list: HTMLUListElement | null = null;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]!;
    if (!line.trim()) { list = null; continue; }
    const table = parseTable(lines, index, trustedUrls);
    if (table) {
      list = null;
      container.append(table[0]);
      index = table[1] - 1;
      continue;
    }
    const item = line.match(/^\s*[-*]\s+(.+)$/);
    if (item) {
      if (!list) { list = document.createElement("ul"); container.append(list); }
      const li = document.createElement("li"); appendInline(li, item[1]!, trustedUrls); list.append(li);
      continue;
    }
    list = null;
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    const element = document.createElement(heading ? `h${heading[1]!.length + 2}` : "p");
    appendInline(element, heading?.[2] ?? line, trustedUrls);
    container.append(element);
  }
}

export function safeReferences(references: unknown): ChatReference[] {
  if (!Array.isArray(references)) return [];
  return references.slice(0, 12).flatMap((value) => {
    if (!value || typeof value !== "object") return [];
    const ref = value as Record<string, unknown>;
    if (typeof ref.label !== "string") return [];
    const output: ChatReference = { label: ref.label.slice(0, 200) };
    if (typeof ref.detail === "string") output.detail = ref.detail.slice(0, 500);
    if (typeof ref.url === "string") output.url = trustedSourceUrl(ref.url);
    return [output];
  });
}

export function messageFromPayload(raw: Record<string, unknown>, maxLength = 20_000): Partial<ChatMessage> {
  return {
    ...(typeof raw.content === "string" ? { content: raw.content.slice(0, maxLength) } : {}),
    references: safeReferences(raw.references),
    ...(raw.chart ? { chart: raw.chart as ChatChart } : {}),
  };
}
