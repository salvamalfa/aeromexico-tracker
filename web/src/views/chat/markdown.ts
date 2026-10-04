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

export function renderSafeMarkdown(container: HTMLElement, source: string, allowedUrls: readonly string[] = []): void {
  container.replaceChildren();
  const trustedUrls = new Set(allowedUrls.flatMap((raw) => {
    const url = trustedSourceUrl(raw);
    return url ? [url] : [];
  }));
  const lines = source.replace(/\r/g, "").split("\n");
  let list: HTMLUListElement | null = null;
  for (const line of lines) {
    if (!line.trim()) { list = null; continue; }
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
