import {
  type RatingMap,
  type ReviewDataset,
  ratingKey,
} from "./types";
import { loadRatings, saveRatings } from "./storage";
import { renderNavigation, renderProgress, renderQuestion } from "./render";
import { type QuestionFilter, visibleQuestionIndices } from "./filters";
import { parseDataset, parseRatings, ratingsFile } from "./validation";

const MAX_FILE_BYTES = 10 * 1024 * 1024;

export async function sha256Hex(bytes: ArrayBuffer, subtle: SubtleCrypto = crypto.subtle): Promise<string> {
  const digest = await subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function requireNode<T extends Element>(root: ParentNode, selector: string): T {
  const node = root.querySelector<T>(selector);
  if (!node) throw new Error(`Falta el elemento requerido: ${selector}`);
  return node;
}

async function readJsonFile(file: File): Promise<{ value: unknown; contentHash: string }> {
  if (file.size > MAX_FILE_BYTES) throw new Error("El archivo supera el límite de 10 MB.");
  if (!crypto.subtle) throw new Error("Este navegador no permite verificar el archivo. Abre la página por HTTPS o localhost.");
  let bytes: ArrayBuffer;
  try {
    bytes = await file.arrayBuffer();
  } catch {
    throw new Error("No se pudo leer el archivo.");
  }
  const contentHash = await sha256Hex(bytes);
  try {
    return { value: JSON.parse(new TextDecoder().decode(bytes)) as unknown, contentHash };
  } catch {
    throw new Error("El archivo no contiene JSON válido.");
  }
}

function downloadRatings(dataset: ReviewDataset, contentHash: string, ratings: RatingMap, view: Window): void {
  const file = ratingsFile(dataset, contentHash, ratings);
  const blob = new Blob([`${JSON.stringify(file, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `calificaciones-${dataset.dataset_id.slice(0, 12)}.json`;
  anchor.ownerDocument.body.append(anchor);
  anchor.click();
  anchor.remove();
  view.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function bootstrapReview(doc: Document = document, storage: Storage = window.localStorage): void {
  const datasetInput = requireNode<HTMLInputElement>(doc, "#dataset-file");
  const ratingsInput = requireNode<HTMLInputElement>(doc, "#ratings-file");
  const importButton = requireNode<HTMLButtonElement>(doc, "#import-button");
  const exportButton = requireNode<HTMLButtonElement>(doc, "#export-button");
  const loadStatus = requireNode<HTMLElement>(doc, "#load-status");
  const workspace = requireNode<HTMLElement>(doc, "#review-workspace");
  const nav = requireNode<HTMLOListElement>(doc, "#question-nav");
  const filter = requireNode<HTMLSelectElement>(doc, "#question-filter");
  const filterEmpty = requireNode<HTMLElement>(doc, "#filter-empty");
  const questionContent = requireNode<HTMLElement>(doc, "#question-content");
  const selectionFilterNote = requireNode<HTMLElement>(doc, "#selection-filter-note");
  const previous = requireNode<HTMLButtonElement>(doc, "#previous-question");
  const next = requireNode<HTMLButtonElement>(doc, "#next-question");
  const view = doc.defaultView;
  if (!view) throw new Error("La revisión requiere un navegador.");

  let dataset: ReviewDataset | null = null;
  let contentHash = "";
  let ratings: RatingMap = new Map();
  let canPersist = true;
  let selectedIndex = 0;
  const visible = () => dataset
    ? visibleQuestionIndices(dataset, ratings, filter.value as QuestionFilter)
    : [];

  const announce = (message: string, error = false) => {
    loadStatus.textContent = message;
    loadStatus.setAttribute("data-error", String(error));
  };
  const save = () => {
    if (!dataset || !canPersist) return;
    try {
      saveRatings(dataset, contentHash, ratings, storage);
    } catch {
      announce("No se pudo guardar en este navegador. Exporta las calificaciones antes de salir.", true);
    }
  };
  const updateSidebar = () => {
    if (!dataset) return;
    renderProgress(dataset, ratings);
    const indices = visible();
    selectionFilterNote.hidden = indices.includes(selectedIndex) || indices.length === 0;
    renderNavigation(nav, dataset, ratings, indices, selectedIndex, (index) => {
      selectedIndex = index;
      updateView();
      nav.querySelector<HTMLButtonElement>(`[data-question-index="${index}"]`)?.focus();
    });
    filterEmpty.hidden = indices.length > 0;
  };
  const updateView = () => {
    if (!dataset) return;
    const indices = visible();
    if (indices.length === 0) {
      selectedIndex = -1;
      updateSidebar();
      questionContent.hidden = true;
      return;
    }
    questionContent.hidden = false;
    if (!indices.includes(selectedIndex)) selectedIndex = indices[0];
    updateSidebar();
    selectionFilterNote.hidden = indices.includes(selectedIndex);
    const position = indices.indexOf(selectedIndex);
    renderQuestion(dataset, selectedIndex, ratings, position > 0 || position === -1,
      position < indices.length - 1 || position === -1,
      (questionId, alias, status, notes) => {
      const key = ratingKey(questionId, alias);
      if (!status) {
        ratings.delete(key);
      } else {
        ratings.set(key, { question_id: questionId, alias, status, notes });
      }
      save();
      updateSidebar();
    });
  };
  const moveQuestion = (delta: number, focus = false) => {
    if (!dataset) return;
    const indices = visible();
    if (indices.length === 0) return;
    const position = indices.indexOf(selectedIndex);
    const nextIndex = position === -1
      ? (delta > 0 ? indices[0] : indices[indices.length - 1])
      : indices[position + delta];
    if (nextIndex === undefined) return;
    selectedIndex = nextIndex;
    updateView();
    if (focus) nav.querySelector<HTMLButtonElement>(`[data-question-index="${nextIndex}"]`)?.focus();
  };

  datasetInput.addEventListener("change", async () => {
    const file = datasetInput.files?.[0];
    datasetInput.value = "";
    if (!file) return;
    try {
      const imported = await readJsonFile(file);
      const parsed = parseDataset(imported.value);
      dataset = parsed;
      contentHash = imported.contentHash;
      selectedIndex = 0;
      canPersist = true;
      try {
        ratings = loadRatings(parsed, contentHash, storage);
        announce(`Archivo cargado: ${parsed.questions.length} preguntas y ${parsed.available_count} respuestas.`);
      } catch {
        ratings = new Map();
        canPersist = false;
        announce("No se pudo recuperar el guardado anterior. Se conservará sin cambios; esta revisión solo se guardará al exportarla.", true);
      }
      workspace.hidden = false;
      importButton.disabled = false;
      exportButton.disabled = false;
      updateView();
    } catch (error) {
      announce(error instanceof Error ? error.message : "No se pudo abrir el archivo.", true);
    }
  });

  importButton.addEventListener("click", () => ratingsInput.click());
  ratingsInput.addEventListener("change", async () => {
    const file = ratingsInput.files?.[0];
    ratingsInput.value = "";
    if (!file || !dataset) return;
    try {
      const parsed = await readJsonFile(file);
      const imported = parseRatings(parsed.value, dataset, contentHash);
      if (ratings.size > 0 && !view.confirm("Importar reemplazará las calificaciones guardadas para este conjunto. ¿Continuar?")) {
        announce("Importación cancelada.");
        return;
      }
      ratings = imported;
      save();
      updateView();
      announce(`Se importaron ${ratings.size} calificaciones.`);
    } catch (error) {
      announce(error instanceof Error ? error.message : "No se pudieron importar las calificaciones.", true);
    }
  });

  exportButton.addEventListener("click", () => {
    if (!dataset) return;
    downloadRatings(dataset, contentHash, ratings, view);
    announce(`Se exportaron ${ratings.size} calificaciones, sin respuestas.`);
  });
  filter.addEventListener("change", () => {
    updateView();
  });
  nav.addEventListener("keydown", (event) => {
    if (!(event instanceof view.KeyboardEvent)) return;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      moveQuestion(1, true);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      moveQuestion(-1, true);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const indices = visible();
      const index = event.key === "Home" ? indices[0] : indices[indices.length - 1];
      if (index !== undefined) {
        selectedIndex = index;
        updateView();
        nav.querySelector<HTMLButtonElement>(`[data-question-index="${index}"]`)?.focus();
      }
    }
  });
  previous.addEventListener("click", () => {
    moveQuestion(-1);
    doc.querySelector<HTMLButtonElement>("#previous-question")?.focus();
  });
  next.addEventListener("click", () => {
    moveQuestion(1);
    doc.querySelector<HTMLButtonElement>("#next-question")?.focus();
  });
}
