import type { ChatMessage } from "../../types/chat";
import { renderSafeChart } from "./chart";
import { renderSafeMarkdown, safeReferences } from "./markdown";

export interface RenderOptions {
  canRetry: (message: ChatMessage) => boolean;
  onRetry: (message: ChatMessage) => void;
}

function referenceList(message: ChatMessage): HTMLUListElement | undefined {
  const references = safeReferences(message.references);
  if (!references.length) return undefined;
  const refs = document.createElement("ul");
  refs.className = "chat-references";
  refs.setAttribute("aria-label", "Fuentes");
  for (const reference of references) {
    const li = document.createElement("li");
    if (reference.url) {
      const anchor = document.createElement("a");
      anchor.href = reference.url; anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
      anchor.textContent = reference.label; li.append(anchor);
    } else {
      const title = document.createElement("span"); title.textContent = reference.label; li.append(title);
    }
    if (reference.detail) { const detail = document.createElement("small"); detail.textContent = reference.detail; li.append(detail); }
    refs.append(li);
  }
  return refs;
}

export function renderMessages(node: HTMLOListElement, messages: readonly ChatMessage[], options: RenderOptions): void {
  node.replaceChildren();
  for (const message of messages) {
    const item = document.createElement("li");
    item.className = `chat-message chat-message-${message.role}${message.pending ? " is-pending" : ""}`;
    item.dataset.messageId = message.id;
    const label = document.createElement("span");
    label.className = "chat-message-label";
    label.textContent = message.role === "user" ? "Tú" : "Airline Tracker";
    item.append(label);
    const body = document.createElement("div");
    body.className = "chat-message-body";
    const trustedReferenceUrls = safeReferences(message.references).flatMap((reference) => reference.url ? [reference.url] : []);
    renderSafeMarkdown(body, message.content, trustedReferenceUrls);
    item.append(body);
    if (message.chart) {
      const chartHost = document.createElement("div");
      chartHost.className = "chat-answer-chart";
      chartHost.setAttribute("role", "img");
      chartHost.setAttribute("aria-label", message.chart.title ?? "Gráfica de respuesta");
      item.append(chartHost);
      if (!renderSafeChart(chartHost, message.chart)) chartHost.remove();
    }
    const refs = referenceList(message);
    if (refs) item.append(refs);
    if (message.role === "assistant" && !message.pending && options.canRetry(message)) {
      const retry = document.createElement("button"); retry.type = "button"; retry.className = "chat-retry"; retry.textContent = "Reintentar";
      retry.addEventListener("click", () => options.onRetry(message));
      item.append(retry);
    }
    node.append(item);
  }
  node.scrollTop = node.scrollHeight;
}
