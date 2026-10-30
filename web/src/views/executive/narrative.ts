// Renders panel-reading's narrative-copy for the active period from
// web/public/data/v1/analysis/<period_id>.json — the export of
// src.analysis_agent.lifecycle.consumer_payload(record) plus per-claim
// citations (see src/web_export/analysis.py) — one fetch per period,
// cached afterwards by data root, entity and period. A period with no exported file (draft/unapproved, or
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
import { isEntityKey } from "../shell/carriers";

export function citationsByClaim(analysis: AnalysisDocument): Map<string, AnalysisCitation[]> {
  return new Map(analysis.claims.map((claim) => [claim.claim_id, claim.citations]));
}

// Port of reader_ui.py::cite()'s inner text-node walk and <sup><a> splice.
export function applyCitations(container: Element, citations: AnalysisCitation[]): void {
  const tails = new Map<string, HTMLElement>();
  for (const citation of citations) {
    if (!citation.value || !safeSourceUrl(citation.href)) continue;
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
    const tail = tails.get(citation.value);
    if (tail) {
      tail.after(sup);
      tails.set(citation.value, sup);
      continue;
    }
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode() as Text | null;
    while (node) {
      if (node.parentElement?.closest("a, sup")) {
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
      node.textContent = before;
      node.after(sup, document.createTextNode(after));
      tails.set(citation.value, sup);
      break;
    }
  }
}

function safeSourceUrl(href: string): boolean {
  try {
    const url = new URL(href);
    return url.protocol === "https:" && !url.username && !url.password && [
      "www.sec.gov", "sec.gov", "ir.aeromexico.com", "cdn.investorcloud.net", "ir.volaris.com",
      "www.globenewswire.com",
    ].includes(url.hostname);
  } catch { return false; }
}

const cache = new Map<string, AnalysisDocument | null>();
let renderEpoch = 0;

function validDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

// Runtime boundary: a missing entity is compatible only with the historical
// Aeroméxico endpoint. Never use that document as another entity's fallback.
export function validAnalysis(payload: unknown, entityKey: string, periodId: string): payload is AnalysisDocument {
  if (!isEntityKey(entityKey) || !/^\d{4}Q[1-4]$/.test(periodId)) return false;
  if (!payload || typeof payload !== "object") return false;
  const p = payload as Record<string, unknown>;
  if (p.period_id !== periodId || typeof p.version !== "string" || !p.version.trim()) return false;
  if ((p.entity_key === undefined ? "AEROMEXICO" : p.entity_key) !== entityKey) return false;
  if (entityKey !== "AEROMEXICO") {
    if (typeof p.period_label !== "string" || !p.period_label.trim() || !validDate(p.cutoff_date)) return false;
    const historical = p.selection_mode === "retrospective" && p.guidance_as_of === "report_date";
    const issuerDate = entityKey === "VIVA_AEROBUS" ? "2026-10-28" : entityKey === "VOLARIS" ? "2026-10-26" : null;
    const issuer = periodId === "2026Q3" && p.period_label === "3T26" && issuerDate !== null &&
      p.selection_mode === "retrospective_source_edition" && p.guidance_as_of === issuerDate &&
      validDate(p.guidance_as_of) && p.guidance_as_of <= p.cutoff_date;
    if (!historical && !issuer) return false;
  }
  const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every((s) => typeof s === "string");
  if (typeof p.thesis !== "string" || !strings(p.context)) return false;
  if (!Array.isArray(p.summary_items) || !p.summary_items.every((s) => s &&
    typeof s.claim_id === "string" && typeof s.text === "string" &&
    (s.lead == null || typeof s.lead === "string") && (s.emphasis === undefined || strings(s.emphasis)))) return false;
  if (!Array.isArray(p.sections) || !p.sections.every((s) => s &&
    typeof s.title === "string" && strings(s.paragraphs) && strings(s.claim_ids) && s.paragraphs.length === s.claim_ids.length)) return false;
  if (!Array.isArray(p.claims) || !p.claims.every((c) => c && typeof c.claim_id === "string" &&
    Array.isArray(c.citations) && c.citations.every((x: AnalysisCitation) => x &&
      [x.label, x.href, x.title, x.value].every((v) => typeof v === "string") && safeSourceUrl(x.href)))) return false;
  const claimIds = new Set(p.claims.map((c) => c.claim_id));
  return claimIds.size === p.claims.length && p.summary_items.every((s) => claimIds.has(s.claim_id)) &&
    p.sections.every((s) => s.claim_ids.every((id: string) => claimIds.has(id)));
}

async function fetchAnalysis(entityKey: string, periodId: string): Promise<AnalysisDocument | null> {
  if (!isEntityKey(entityKey) || !/^\d{4}Q[1-4]$/.test(periodId)) return null;
  const key = JSON.stringify([state.dataRoot, entityKey, periodId]);
  if (cache.has(key)) return cache.get(key) ?? null;
  const path = entityKey === "AEROMEXICO" ? periodId : `${entityKey}/${periodId}`;
  try {
    const response = await fetch(`${state.dataRoot}/analysis/${path}.json`);
    const raw: unknown = response.ok ? await response.json() : null;
    const payload = validAnalysis(raw, entityKey, periodId) ? raw : null;
    cache.set(key, payload);
    return payload;
  } catch { return null; }
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

function temporalNotice(analysis: AnalysisDocument): string {
  if (!analysis.cutoff_date || !["retrospective", "retrospective_source_edition"].includes(analysis.selection_mode ?? "")) return "";
  const parsed = new Date(`${analysis.cutoff_date}T00:00:00Z`);
  const date = Number.isNaN(parsed.getTime()) ? analysis.cutoff_date : new Intl.DateTimeFormat("es-MX", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  }).format(parsed);
  const report = analysis.selection_mode === "retrospective_source_edition" ? ` (${analysis.guidance_as_of})` : "";
  return `Corte de información: ${date} · Análisis retrospectivo. Las expectativas corresponden a la fecha del reporte${report}.`;
}

function renderDialog(analysis: AnalysisDocument, periodLabel: string, entityKey: string, entityName: string): void {
  const dialog = $("analysis-full");
  if (!dialog) return;
  const prefix = entityKey === "AEROMEXICO" ? "Análisis completo" : `Análisis completo · ${entityName}`;
  dialog.querySelector(".bar h2")!.textContent = `${prefix} · ${periodLabel}`;
  const content = dialog.querySelector(".modal-content")!;
  const notice = temporalNotice(analysis);
  content.innerHTML = (notice ? `<aside class="analysis-context">${escapeHtml(notice)}</aside>` : "") + analysis.sections
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

function wireDialogButton(analysis: AnalysisDocument, periodLabel: string, entityKey: string, entityName: string): void {
  const button = $("analysis-open-full");
  if (!button) return;
  button.onclick = () => {
    renderDialog(analysis, periodLabel, entityKey, entityName);
    ($("analysis-full") as HTMLDialogElement).showModal();
  };
}

export async function renderNarrative(view: Pick<ExecutiveView, "period_id" | "period_label">, entityKey = "AEROMEXICO", entityName = "Aeroméxico"): Promise<void> {
  const epoch = ++renderEpoch;
  $("narrative-period")!.textContent = view.period_label;
  const entityNode = $("narrative-entity");
  if (entityNode) entityNode.textContent = entityName;
  const copy = $("narrative-copy")!;
  const dialog = $("analysis-full") as HTMLDialogElement | null;
  if (dialog?.open) dialog.close();
  dialog?.querySelector(".modal-content")?.replaceChildren();
  copy.innerHTML = '<p class="analysis-placeholder">Cargando análisis…</p>';
  copy.dataset.period = view.period_id;
  copy.dataset.entity = entityKey;
  const analysis = await fetchAnalysis(entityKey, view.period_id);
  if (epoch !== renderEpoch) return;
  if (!analysis) {
    copy.innerHTML = '<p class="analysis-placeholder" id="analysis-empty">Análisis pendiente de aprobación para este trimestre.</p>';
    copy.dataset.period = view.period_id;
    return;
  }
  const periodLabel = analysis.period_label ?? view.period_label;
  $("narrative-period")!.textContent = periodLabel;
  const items = analysis.summary_items
    .map((item) => `<li>${emphasized(item.text, item.lead ?? "", item.emphasis)}</li>`)
    .join("");
  const notice = temporalNotice(analysis);
  const context = [...(notice ? [notice] : []), ...analysis.context].map((text) => `<aside class="analysis-context">${escapeHtml(text)}</aside>`).join("");
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
  wireDialogButton(analysis, periodLabel, entityKey, entityName);
}
