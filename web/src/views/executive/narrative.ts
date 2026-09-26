// Renders panel-reading's narrative-copy for the active period from
// web/public/data/v1/analysis/<period_id>.json — the export of
// src.analysis_agent.lifecycle.consumer_payload(record) plus per-claim
// citations (see src/web_export/analysis.py) — one fetch per period,
// cached afterwards. A period with no exported file (draft/unapproved, or
// a dev build run with --allow-missing-analysis) shows the same fallback
// text the published page shows for a quarter pending approval.
//
// Citations: applyCitations below is a port of
// src/analysis_agent/reader_ui.py::cite()'s DOM-splicing step (same
// <sup><a class="source-note"> markup/attributes, same "first text node
// containing the value, skip if already inside <a>/<sup>" rule) run
// against each already-rendered claim's own container — the numbering and
// href/title themselves are computed once, ahead of time, by
// src/web_export/analysis.py.

import { $ } from "../flights/dom";
import { state } from "./state";
import type { AnalysisCitation, AnalysisDocument, ExecutiveView } from "../../types/domain";

export function citationsByClaim(analysis: AnalysisDocument): Map<string, AnalysisCitation[]> {
  return new Map(analysis.claims.map((claim) => [claim.claim_id, claim.citations]));
}

// Port of reader_ui.py::cite()'s inner text-node walk and <sup><a> splice.
export function applyCitations(container: Element, citations: AnalysisCitation[]): void {
  for (const citation of citations) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode() as Text | null;
    while (node) {
      const parentName = node.parentElement?.nodeName;
      if (parentName === "A" || parentName === "SUP") {
        node = walker.nextNode() as Text | null;
        continue;
      }
      const text = node.textContent ?? "";
      const index = text.indexOf(citation.value);
      if (index === -1) {
        node = walker.nextNode() as Text | null;
        continue;
      }
      const before = text.slice(0, index + citation.value.length);
      const after = text.slice(index + citation.value.length);
      const sup = document.createElement("sup");
      const a = document.createElement("a");
      a.href = citation.href;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "source-note";
      a.setAttribute("aria-label", `Fuente ${citation.label}: abrir dato original`);
      a.title = citation.title;
      a.textContent = citation.label;
      sup.appendChild(a);
      node.textContent = before;
      node.after(sup, document.createTextNode(after));
      break;
    }
  }
}

const cache = new Map<string, AnalysisDocument | null>(); // period_id -> payload | null (no export for this period)
let dialogPeriodLabel = "";

async function fetchAnalysis(periodId: string): Promise<AnalysisDocument | null> {
  if (cache.has(periodId)) return cache.get(periodId) ?? null;
  const response = await fetch(`${state.dataRoot}/analysis/${periodId}.json`);
  const payload = response.ok ? ((await response.json()) as AnalysisDocument) : null;
  cache.set(periodId, payload);
  return payload;
}

// Port of src/analysis_agent/analyst.py::emphasized: wraps the lead
// sentence and any emphasis phrase in <strong>, escaping everything else.
function emphasized(text: string, lead: string, phrases: string[] = []): string {
  const spans: Array<[number, number]> = [];
  for (const phrase of [lead, ...phrases]) {
    if (!phrase || !text.includes(phrase)) continue;
    const start = text.indexOf(phrase);
    const end = start + phrase.length;
    if (spans.some(([a, b]) => start < b && end > a)) continue;
    spans.push([start, end]);
  }
  spans.sort((a, b) => a[0] - b[0]);
  const escape = (value: string) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  let cursor = 0;
  const parts: string[] = [];
  for (const [start, end] of spans) {
    parts.push(escape(text.slice(cursor, start)), "<strong>", escape(text.slice(start, end)), "</strong>");
    cursor = end;
  }
  parts.push(escape(text.slice(cursor)));
  return parts.join("");
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderDialog(analysis: AnalysisDocument, periodLabel: string): void {
  const dialog = $("analysis-full");
  if (!dialog) return;
  dialog.querySelector(".bar h2")!.textContent = `Análisis completo · ${periodLabel}`;
  const content = dialog.querySelector(".modal-content")!;
  content.innerHTML = analysis.sections
    .map(
      (section) =>
        `<section><h3>${escapeHtml(section.title)}</h3>` +
        section.paragraphs.map((p) => `<p>${escapeHtml(p)}</p>`).join("") +
        "</section>"
    )
    .join("");
  const citations = citationsByClaim(analysis);
  const paragraphs = [...content.querySelectorAll("section p")];
  const claimIds = analysis.sections.flatMap((section) => section.claim_ids);
  paragraphs.forEach((paragraph, index) => {
    const claimId = claimIds[index];
    if (claimId) applyCitations(paragraph, citations.get(claimId) ?? []);
  });
}

function wireDialogButton(analysis: AnalysisDocument, periodLabel: string): void {
  const button = $("analysis-open-full");
  if (!button) return;
  button.onclick = () => {
    dialogPeriodLabel = periodLabel;
    renderDialog(analysis, dialogPeriodLabel);
    ($("analysis-full") as HTMLDialogElement).showModal();
  };
}

export async function renderNarrative(view: ExecutiveView): Promise<void> {
  $("narrative-period")!.textContent = view.period_label;
  const analysis = await fetchAnalysis(view.period_id);
  const copy = $("narrative-copy")!;
  if (!analysis) {
    copy.innerHTML = '<p class="analysis-placeholder" id="analysis-empty">Análisis pendiente de aprobación para este trimestre.</p>';
    copy.dataset.period = view.period_id;
    return;
  }
  const items = analysis.summary_items
    .map((item) => `<li>${emphasized(item.text, item.lead ?? "", item.emphasis)}</li>`)
    .join("");
  const context = analysis.context.map((text) => `<aside class="analysis-context">${escapeHtml(text)}</aside>`).join("");
  copy.innerHTML =
    `<div><h3>${escapeHtml(analysis.thesis)}</h3>` +
    `<ul class="analysis-summary">${items}</ul>${context}` +
    '<div class="analysis-actions"><button type="button" id="analysis-open-full">▸ Leer análisis completo</button></div></div>';
  const citations = citationsByClaim(analysis);
  [...copy.querySelectorAll(".analysis-summary li")].forEach((li, index) => {
    const claimId = analysis.summary_items[index]?.claim_id;
    if (claimId) applyCitations(li, citations.get(claimId) ?? []);
  });
  copy.dataset.period = view.period_id;
  wireDialogButton(analysis, view.period_label);
}
