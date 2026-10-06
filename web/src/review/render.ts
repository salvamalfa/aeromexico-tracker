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
  title.textContent = question.question;
  language.textContent = `Idioma: ${question.language}`;
  expected.textContent = expectedText(question.expected);
  renderExpectedSummary(summary, question.expected);
  candidateList.replaceChildren();
  previous.disabled = !hasPrevious;
  next.disabled = !hasNext;

  for (const candidate of question.candidates) {
    const article = document.createElement("article");
    article.className = "candidate-card";
    article.append(textNode("h3", "candidate-heading", `Candidato ${candidate.alias}`));
    if (candidate.answer === null) {
      const missingStatus = slotDispositions.get(ratingKey(question.id, candidate.alias));
      const labels: Record<SlotDisposition["status"], string> = {
        no_answer: "La ejecución terminó sin respuesta.",
        failed: "La ejecución terminó con error; no hay respuesta para calificar.",
        held: "Esta combinación quedó en espera; no hay respuesta para calificar.",
        not_attempted: "Esta combinación no se intentó en este corte.",
      };
      article.append(textNode("p", "missing-answer", missingStatus
        ? labels[missingStatus]
        : "Sin respuesta disponible; el archivo no detalla su estado."));
      candidateList.append(article);
      continue;
    }
    const answer = textNode("div", "candidate-answer", candidate.answer || "[Respuesta vacía]");
    answer.setAttribute("aria-label", `Respuesta del candidato ${candidate.alias}`);
    article.append(answer);
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
