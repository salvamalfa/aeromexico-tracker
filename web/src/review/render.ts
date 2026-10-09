import {
  type CandidateAlias,
  type RatingMap,
  type RatingStatus,
  type ReviewDataset,
  type SlotDisposition,
  ratingKey,
} from "./types";
import { questionProgress } from "./filters";
import { renderExpectedSummary } from "./expected";
import { renderSafeMarkdown } from "../views/chat/markdown";

const decisions: Array<{ value: RatingStatus; label: string }> = [
  { value: "correct", label: "Correcta" },
  { value: "problem", label: "Con problema" },
  { value: "not_evaluable", label: "No evaluable" },
];

function textNode(tag: string, className: string, text: string): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function expectedText(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2) ?? "null";
}

type ConversationMessage = { role: "user" | "assistant"; turn?: number; content: string };
type ParsedConversation = { messages: ConversationMessage[]; valid: boolean };

function hasMultilineHtml(source: string): boolean {
  const commentStart = source.indexOf("<!--");
  if (commentStart >= 0) {
    const commentEnd = source.indexOf("-->", commentStart + 4);
    if (commentEnd > commentStart && source.slice(commentStart, commentEnd).includes("\n")) return true;
  }
  for (const opening of source.matchAll(/<([a-z][\w:-]*)\b[^>]*>/gi)) {
    const start = opening.index ?? 0;
    const closing = new RegExp(`<\\/\\s*${opening[1]}\\s*>`, "ig");
    closing.lastIndex = start + opening[0].length;
    const close = closing.exec(source);
    if (close && source.slice(start, close.index).includes("\n")) return true;
  }
  return false;
}

function conversationMessages(source: string, role: ConversationMessage["role"]): ParsedConversation {
  if (!source) return { messages: [], valid: true };
  const markerPattern = role === "user"
    ? /^Mensaje del usuario · turno (\d+):[ \t]*$/
    : /^Respuesta del asistente · turno (\d+):[ \t]*$/;
  const markers: Array<{ start: number; end: number; turn: number }> = [];
  let fence: { character: string; width: number } | null = null;
  let offset = 0;
  for (const rawLine of source.split(/(?<=\n)/)) {
    const line = rawLine.replace(/\r?\n$/, "");
    const fenceStart = line.match(/^\s*(`{3,}|~{3,})/);
    if (fence) {
      const closing = new RegExp(`^\\s*${fence.character}{${fence.width},}\\s*$`);
      if (closing.test(line)) fence = null;
    } else if (fenceStart) {
      fence = { character: fenceStart[1]![0]!, width: fenceStart[1]!.length };
    } else if (!/^\s*>/.test(line)) {
      const match = line.match(markerPattern);
      if (match) markers.push({ start: offset, end: offset + rawLine.length, turn: Number(match[1]) });
    }
    offset += rawLine.length;
  }
  if (!markers.length) return { messages: [{ role, content: source }], valid: true };
  const messages: ConversationMessage[] = [];
  const prefix = source.slice(0, markers[0]!.start);
  if (prefix.trim()) messages.push({ role, content: prefix });
  for (const [index, marker] of markers.entries()) {
    messages.push({
      role,
      turn: marker.turn,
      content: source.slice(marker.end, markers[index + 1]?.start ?? source.length),
    });
  }
  return {
    messages,
    valid: !prefix.trim() && !hasMultilineHtml(source)
      && markers.every((marker, index) => Number.isSafeInteger(marker.turn) && marker.turn === index + 1),
  };
}

function renderCandidateConversation(host: HTMLElement, userSource: string, assistantSource: string): void {
  const users = conversationMessages(userSource, "user");
  const assistants = conversationMessages(assistantSource, "assistant");
  const messages = (users.valid && assistants.valid
    ? [...users.messages, ...assistants.messages]
    : [{ role: "user" as const, content: userSource }, { role: "assistant" as const, content: assistantSource }])
    .sort((left, right) => {
    const leftTurn = left.turn ?? (left.role === "user" ? -Infinity : Infinity);
    const rightTurn = right.turn ?? (right.role === "user" ? -Infinity : Infinity);
    if (leftTurn !== rightTurn) return leftTurn < rightTurn ? -1 : 1;
    if (left.role === right.role) return 0;
    return left.role === "user" ? -1 : 1;
  });
  for (const message of messages) {
    const bubble = document.createElement("section");
    bubble.className = `review-message review-message-${message.role}`;
    const label = document.createElement("h4");
    label.className = "review-message-label";
    label.textContent = message.turn
      ? `${message.role === "user" ? "Usuario" : "Asistente"} · turno ${message.turn}`
      : message.role === "user" ? "Usuario" : "Asistente";
    const body = document.createElement("div");
    body.className = "review-message-body markdown-body";
    const allowedUrls = [...message.content.matchAll(/\]\((https:\/\/[^)]+)\)/g)].map((match) => match[1]!);
    renderSafeMarkdown(body, message.content, allowedUrls);
    bubble.append(label, body);
    host.append(bubble);
  }
}

export function renderNavigation(
  node: HTMLOListElement,
  dataset: ReviewDataset,
  ratings: RatingMap,
  visibleIndices: number[],
  selectedIndex: number,
  onSelect: (index: number) => void,
): void {
  node.replaceChildren();
  const selectionIsVisible = visibleIndices.includes(selectedIndex);
  visibleIndices.forEach((index, visibleIndex) => {
    const question = dataset.questions[index];
    if (!question) return;
    const { available, reviewed, hasProblem } = questionProgress(dataset, index, ratings);
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "question-nav-button";
    button.dataset.questionIndex = String(index);
    button.setAttribute("aria-current", selectionIsVisible && index === selectedIndex ? "step" : "false");
    button.setAttribute("aria-label", `${question.id}, ${reviewed} de ${available} respuestas calificadas${hasProblem ? ", con problema" : ""}`);
    button.tabIndex = (selectionIsVisible && index === selectedIndex) || (!selectionIsVisible && visibleIndex === 0) ? 0 : -1;
    button.append(textNode("span", "question-nav-id", question.id));
    button.append(textNode("span", "question-nav-count", `${reviewed}/${available}`));
    if (hasProblem) button.append(textNode("span", "question-nav-problem", "Problema"));
    button.addEventListener("click", () => onSelect(index));
    item.append(button);
    node.append(item);
  });
}

export function renderProgress(dataset: ReviewDataset, ratings: RatingMap): void {
  const total = dataset.available_count;
  const reviewed = ratings.size;
  const progress = document.querySelector<HTMLProgressElement>("#review-progress");
  const count = document.querySelector<HTMLOutputElement>("#progress-count");
  const detail = document.querySelector<HTMLElement>("#progress-detail");
  if (!progress || !count || !detail) return;
  progress.max = total || 1;
  progress.value = reviewed;
  progress.setAttribute("aria-valuetext", `${reviewed} de ${total} respuestas calificadas`);
  count.value = `${reviewed} / ${total}`;
  detail.textContent = `${dataset.questions.length} preguntas · ${total} respuestas disponibles`;
  const amounts: Record<RatingStatus, number> = { correct: 0, problem: 0, not_evaluable: 0 };
  for (const rating of ratings.values()) amounts[rating.status] += 1;
  const setCount = (id: string, value: number) => {
    const node = document.querySelector<HTMLElement>(id);
    if (node) node.textContent = String(value);
  };
  setCount("#count-correct", amounts.correct);
  setCount("#count-problem", amounts.problem);
  setCount("#count-not-evaluable", amounts.not_evaluable);
  setCount("#count-unreviewed", Math.max(0, total - reviewed));
}

export function renderQuestion(
  dataset: ReviewDataset,
  index: number,
  ratings: RatingMap,
  hasPrevious: boolean,
  hasNext: boolean,
  onChange: (questionId: string, alias: CandidateAlias, status: RatingStatus | null, notes: string) => void,
  slotDispositions: Map<string, SlotDisposition["status"]> = new Map(),
): void {
  const question = dataset.questions[index];
  const position = document.querySelector<HTMLElement>("#question-position");
  const title = document.querySelector<HTMLElement>("#question-text");
  const language = document.querySelector<HTMLElement>("#question-language");
  const summary = document.querySelector<HTMLElement>("#expected-summary");
  const expected = document.querySelector<HTMLElement>("#expected-answer");
  const candidateList = document.querySelector<HTMLElement>("#candidate-list");
  const previous = document.querySelector<HTMLButtonElement>("#previous-question");
  const next = document.querySelector<HTMLButtonElement>("#next-question");
  if (!question || !position || !title || !language || !summary || !expected || !candidateList || !previous || !next) return;

  position.textContent = `Pregunta ${index + 1} de ${dataset.questions.length} · ${question.id}`;
  title.textContent = "Pregunta y respuestas";
  language.textContent = `Idioma: ${question.language}`;
  expected.textContent = expectedText(question.expected);
  renderExpectedSummary(summary, question.expected);
  const expectedData = typeof question.expected === "object" && question.expected !== null && !Array.isArray(question.expected)
    ? question.expected as Record<string, unknown>
    : {};
  const rejectedAliases = Array.isArray(expectedData.application_context_rejected_aliases)
    ? expectedData.application_context_rejected_aliases
    : [];
  candidateList.replaceChildren();
  previous.disabled = !hasPrevious;
  next.disabled = !hasNext;

  for (const candidate of question.candidates) {
    const article = document.createElement("article");
    article.className = "candidate-card";
    article.append(textNode("h3", "candidate-heading", `Candidato ${candidate.alias}`));
    if (candidate.answer === null) {
      if (rejectedAliases.includes(candidate.alias)) {
        article.append(textNode("p", "missing-answer", "No evaluable: rechazado por el contexto de aplicación antes de llamar al modelo."));
        candidateList.append(article);
        continue;
      }
      const missingStatus = slotDispositions.get(ratingKey(question.id, candidate.alias));
      const labels: Record<SlotDisposition["status"], string> = {
        no_answer: "La ejecución terminó sin respuesta.",
        failed: "La ejecución terminó con error; no hay respuesta para calificar.",
        held: "Esta combinación quedó en espera; no hay respuesta para calificar.",
        not_attempted: "Esta combinación no se intentó en este corte.",
      };
      const conversation = document.createElement("div");
      conversation.className = "candidate-answer";
      conversation.setAttribute("aria-label", `Pregunta para el candidato ${candidate.alias}`);
      renderCandidateConversation(conversation, question.question, "");
      article.append(conversation);
      article.append(textNode("p", "missing-answer", missingStatus
        ? labels[missingStatus]
        : "Sin respuesta disponible; el archivo no detalla su estado."));
      candidateList.append(article);
      continue;
    }
    const answer = document.createElement("div");
    answer.className = "candidate-answer";
    answer.setAttribute("aria-label", `Conversación del candidato ${candidate.alias}`);
    renderCandidateConversation(answer, question.question, candidate.answer);
    if (!candidate.answer) answer.append(textNode("p", "missing-answer", "[Respuesta vacía]"));
    article.append(answer);
    const original = document.createElement("details");
    original.className = "candidate-original";
    const originalSummary = document.createElement("summary");
    originalSummary.textContent = "Ver texto original completo";
    const originalText = document.createElement("pre");
    originalText.textContent = candidate.answer;
    original.append(originalSummary, originalText);
    article.append(original);
    const key = ratingKey(question.id, candidate.alias);
    const existing = ratings.get(key);
    const fieldset = document.createElement("fieldset");
    fieldset.className = "rating-options";
    fieldset.append(textNode("legend", "", "Evaluación"));
    for (const decision of decisions) {
      const label = document.createElement("label");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `rating-${question.id}-${candidate.alias}`;
      radio.value = decision.value;
      radio.checked = existing?.status === decision.value;
      radio.addEventListener("change", () => {
        notes.disabled = false;
        onChange(question.id, candidate.alias, decision.value, notes.value);
      });
      label.append(radio, document.createTextNode(decision.label));
      fieldset.append(label);
    }
    article.append(fieldset);
    const noteLabel = document.createElement("label");
    noteLabel.className = "notes-label";
    noteLabel.textContent = "Notas";
    const notes = document.createElement("textarea");
    notes.maxLength = 2_000;
    notes.rows = 3;
    notes.value = existing?.notes ?? "";
    notes.disabled = !existing;
    notes.setAttribute("aria-label", `Notas para candidato ${candidate.alias}`);
    notes.addEventListener("input", () => {
      const selected = fieldset.querySelector<HTMLInputElement>("input:checked");
      onChange(question.id, candidate.alias, (selected?.value as RatingStatus | undefined) ?? null, notes.value);
    });
    noteLabel.append(notes);
    article.append(noteLabel);
    candidateList.append(article);
  }
}
