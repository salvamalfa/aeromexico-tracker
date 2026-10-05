import { bundleRatingsFile, parseBundleRatings, validateBundle } from "./bundle";
import { type BundleRatingsFile, type Rating, type RatingMap, type ReviewBundle, type ReviewCut, type ReviewDataset, ratingKey } from "./types";
import { bundleStorageKey, loadRatings, saveRatings } from "./storage";
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

function downloadJson(value: unknown, filename: string, view: Window): void {
  const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.ownerDocument.body.append(anchor);
  anchor.click();
  anchor.remove();
  view.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function bootstrapReview(doc: Document = document, storageSource?: Storage | (() => Storage)): void {
  const datasetInput = requireNode<HTMLInputElement>(doc, "#dataset-file");
  const ratingsInput = requireNode<HTMLInputElement>(doc, "#ratings-file");
  const importButton = requireNode<HTMLButtonElement>(doc, "#import-button");
  const exportButton = requireNode<HTMLButtonElement>(doc, "#export-button");
  const loadStatus = requireNode<HTMLElement>(doc, "#load-status");
  const workspace = requireNode<HTMLElement>(doc, "#review-workspace");
  const cutControls = requireNode<HTMLElement>(doc, "#cut-controls");
  const bundleTitle = requireNode<HTMLElement>(doc, "#bundle-title");
  const cutSelect = requireNode<HTMLSelectElement>(doc, "#cut-select");
  const cutStatus = requireNode<HTMLElement>(doc, "#cut-status");
  const cacheOption = requireNode<HTMLInputElement>(doc, "#cache-option");
  const nav = requireNode<HTMLOListElement>(doc, "#question-nav");
  const filter = requireNode<HTMLSelectElement>(doc, "#question-filter");
  const filterEmpty = requireNode<HTMLElement>(doc, "#filter-empty");
  const questionContent = requireNode<HTMLElement>(doc, "#question-content");
  const selectionFilterNote = requireNode<HTMLElement>(doc, "#selection-filter-note");
  const previous = requireNode<HTMLButtonElement>(doc, "#previous-question");
  const next = requireNode<HTMLButtonElement>(doc, "#next-question");
  const view = doc.defaultView;
  if (!view) throw new Error("La revisión requiere un navegador.");
  const getStorage = (): Storage => {
    if (typeof storageSource === "function") return storageSource();
    return storageSource ?? view.localStorage;
  };

  let dataset: ReviewDataset | null = null;
  let bundle: ReviewBundle | null = null;
  let activeCut: ReviewCut | null = null;
  let contentHash = "";
  let bundleHash = "";
  let ratings: RatingMap = new Map();
  let ratingsByCut = new Map<string, RatingMap>();
  let loadedBundleCuts = new Set<string>();
  let canPersist = true;
  let selectedIndex = 0;
  const visible = () => dataset ? visibleQuestionIndices(dataset, ratings, filter.value as QuestionFilter) : [];

  const announce = (message: string, error = false) => {
    loadStatus.textContent = message;
    loadStatus.setAttribute("data-error", String(error));
  };
  const activeSlotStates = () => new Map((activeCut?.slot_dispositions ?? []).map((slot) => [
    ratingKey(slot.question_id, slot.alias), slot.status,
  ]));
  const persistActiveRatings = (): boolean => {
    if (!cacheOption.checked || !dataset) return true;
    if (!canPersist) return false;
    try {
      if (bundle && activeCut) {
        getStorage().setItem(bundleStorageKey(bundleHash, activeCut.cut_id, activeCut.dataset_sha256),
          JSON.stringify(ratingsFileForCut(activeCut, ratings)));
      } else {
        saveRatings(dataset, contentHash, ratings, getStorage());
      }
      return true;
    } catch {
      canPersist = false;
      announce("No se pudo guardar en este navegador. Exporta las calificaciones antes de salir.", true);
      return false;
    }
  };
  const persistAllBundleRatings = (): boolean => {
    if (!cacheOption.checked || !bundle) return true;
    if (!canPersist) return false;
    try {
      const storage = getStorage();
      for (const cut of bundle.cuts) {
        const values = ratingsByCut.get(cut.cut_id) ?? new Map();
        storage.setItem(bundleStorageKey(bundleHash, cut.cut_id, cut.dataset_sha256),
          JSON.stringify(ratingsFileForCut(cut, values)));
      }
      return true;
    } catch {
      canPersist = false;
      announce("No se pudieron guardar todos los cortes en este navegador. Las calificaciones siguen en memoria; exporta el paquete antes de salir.", true);
      return false;
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
        if (!status) ratings.delete(key);
        else ratings.set(key, { question_id: questionId, alias, status, notes });
        if (bundle && activeCut) {
          ratingsByCut.set(activeCut.cut_id, ratings);
          loadedBundleCuts.add(activeCut.cut_id);
        }
        persistActiveRatings();
        updateSidebar();
      }, activeSlotStates());
  };
  const loadBundleCutRatings = (cut: ReviewCut): RatingMap => {
    const key = bundleStorageKey(bundleHash, cut.cut_id, cut.dataset_sha256);
    const raw = getStorage().getItem(key);
    if (!raw) return new Map();
    let value: unknown;
    try { value = JSON.parse(raw) as unknown; } catch { throw new Error("El guardado local está dañado; no se modificó."); }
    return parseRatings(value, cut.dataset, cut.dataset_sha256);
  };
  const chooseCut = (cutId: string, announceSelection = false) => {
    if (!bundle) return;
    const selected = bundle.cuts.find((cut) => cut.cut_id === cutId);
    if (!selected) return;
    activeCut = selected;
    dataset = selected.dataset;
    ratings = ratingsByCut.get(selected.cut_id) ?? new Map();
    ratingsByCut.set(selected.cut_id, ratings);
    selectedIndex = 0;
    filter.value = "all";
    const missingCounts = { no_answer: 0, failed: 0, held: 0, not_attempted: 0 };
    for (const slot of selected.slot_dispositions) missingCounts[slot.status] += 1;
    cutStatus.textContent = `${selected.disposition === "terminal" ? "Corte terminal" : selected.disposition === "complete" ? "Corte completo" : "Corte parcial"} · ${selected.dataset.questions.length} preguntas · ${selected.dataset.available_count} respuestas disponibles · ${missingCounts.no_answer} sin respuesta, ${missingCounts.failed} con error, ${missingCounts.held} en espera, ${missingCounts.not_attempted} no intentadas.`;
    if (cacheOption.checked && canPersist && !loadedBundleCuts.has(selected.cut_id)) {
      loadedBundleCuts.add(selected.cut_id);
      try {
        const stored = loadBundleCutRatings(selected);
        if (stored.size || !ratings.size) ratings = stored;
        ratingsByCut.set(selected.cut_id, ratings);
      } catch {
        canPersist = false;
        announce("No se pudo recuperar el guardado anterior. Se conserva el trabajo en memoria y el paquete puede exportarse.", true);
      }
    }
    updateView();
    if (announceSelection) announce(`Corte seleccionado: ${selected.label}. Su progreso está separado de los demás cortes.`);
  };
  const moveQuestion = (delta: number, focus = false) => {
    if (!dataset) return;
    const indices = visible();
    if (indices.length === 0) return;
    const position = indices.indexOf(selectedIndex);
    const nextIndex = position === -1 ? (delta > 0 ? indices[0] : indices[indices.length - 1]) : indices[position + delta];
    if (nextIndex === undefined) return;
    selectedIndex = nextIndex;
    updateView();
    if (focus) nav.querySelector<HTMLButtonElement>(`[data-question-index="${nextIndex}"]`)?.focus();
  };

  cacheOption.addEventListener("change", () => {
    if (!cacheOption.checked || !dataset) {
      canPersist = true;
      announce(cacheOption.checked ? "El guardado local está activado." : "El guardado local está desactivado; el progreso seguirá disponible en memoria y al exportar.");
      return;
    }
    try {
      if (bundle) {
        const nextRatingsByCut = new Map(ratingsByCut);
        const newlyLoaded = new Set<string>();
        for (const cut of bundle.cuts) {
          if (loadedBundleCuts.has(cut.cut_id)) continue;
          const stored = loadBundleCutRatings(cut);
          const current = nextRatingsByCut.get(cut.cut_id) ?? new Map();
          nextRatingsByCut.set(cut.cut_id, stored.size || current.size === 0 ? stored : current);
          newlyLoaded.add(cut.cut_id);
        }
        ratingsByCut = nextRatingsByCut;
        newlyLoaded.forEach((cutId) => loadedBundleCuts.add(cutId));
        if (activeCut) ratings = ratingsByCut.get(activeCut.cut_id) ?? new Map();
      } else {
        const stored = loadRatings(dataset, contentHash, getStorage());
        if (stored.size || ratings.size === 0) ratings = stored;
      }
      canPersist = true;
      persistActiveRatings();
      updateView();
      announce("Guardado local activado. Se usa una clave vinculada al hash exacto del archivo y, para paquetes, al corte.");
    } catch {
      canPersist = false;
      announce("No se pudo leer el guardado local; se conserva sin cambios. Puedes exportar el progreso.", true);
    }
  });

  datasetInput.addEventListener("change", async () => {
    const file = datasetInput.files?.[0];
    datasetInput.value = "";
    if (!file) return;
    try {
      const imported = await readJsonFile(file);
      if (isRecord(imported.value) && "cuts" in imported.value) {
        const parsedBundle = await validateBundle(imported.value, async (bytes) =>
          sha256Hex(bytes.slice().buffer as ArrayBuffer));
        activeCut = null;
        bundle = parsedBundle;
        bundleHash = imported.contentHash;
        contentHash = "";
        ratings = new Map();
        ratingsByCut = new Map();
        loadedBundleCuts = new Set();
        bundle.cuts.forEach((cut) => ratingsByCut.set(cut.cut_id, new Map()));
        canPersist = true;
        bundleTitle.textContent = `${bundle.title} · versión ${bundle.bundle_version}`;
        cutSelect.replaceChildren(...bundle.cuts.map((cut) => {
          const option = doc.createElement("option");
          option.value = cut.cut_id;
          option.textContent = `${cut.label} · ${cut.version}`;
          return option;
        }));
        cutControls.hidden = false;
        chooseCut(bundle.cuts[0].cut_id);
        importButton.disabled = false;
        exportButton.disabled = false;
        workspace.hidden = false;
        announce(`Paquete cargado: ${bundle.cuts.length} cortes versionados. El hash del paquete y cada corte se verificaron.`);
      } else {
        const parsedDataset = parseDataset(imported.value);
        dataset = parsedDataset;
        bundle = null;
        activeCut = null;
        bundleHash = "";
        contentHash = imported.contentHash;
        ratings = new Map();
        ratingsByCut = new Map();
        loadedBundleCuts = new Set();
        cutControls.hidden = true;
        if (cacheOption.checked) {
          try { ratings = loadRatings(dataset, contentHash, getStorage()); canPersist = true; }
          catch { canPersist = false; announce("No se pudo recuperar el guardado anterior. Se conserva sin cambios; exporta las calificaciones.", true); }
        } else canPersist = true;
        selectedIndex = 0;
        workspace.hidden = false;
        importButton.disabled = false;
        exportButton.disabled = false;
        updateView();
        announce(`Archivo cargado: ${dataset.questions.length} preguntas y ${dataset.available_count} respuestas disponibles.`);
      }
    } catch (error) {
      announce(error instanceof Error ? error.message : "No se pudo abrir el archivo.", true);
    }
  });
  cutSelect.addEventListener("change", () => chooseCut(cutSelect.value, true));
  importButton.addEventListener("click", () => ratingsInput.click());
  ratingsInput.addEventListener("change", async () => {
    const file = ratingsInput.files?.[0];
    ratingsInput.value = "";
    if (!file || !dataset) return;
    try {
      const imported = await readJsonFile(file);
      const incoming = bundle
        ? parseBundleRatings(imported.value, bundle, bundleHash)
        : parseLegacyRatings(imported.value, dataset, contentHash);
      const hasRatings = bundle
        ? [...ratingsByCut.values()].some((value) => value.size > 0)
        : ratings.size > 0;
      if (hasRatings && !view.confirm("Importar reemplazará las calificaciones guardadas para este paquete. ¿Continuar?")) {
        announce("Importación cancelada.");
        return;
      }
      if (bundle) {
        ratingsByCut = incoming as Map<string, RatingMap>;
        loadedBundleCuts = new Set(bundle.cuts.map((cut) => cut.cut_id));
        if (activeCut) ratings = ratingsByCut.get(activeCut.cut_id) ?? new Map();
      } else ratings = incoming as RatingMap;
      const persistenceSucceeded = bundle ? persistAllBundleRatings() : persistActiveRatings();
      updateView();
      const count = bundle ? [...ratingsByCut.values()].reduce((sum, map) => sum + map.size, 0) : ratings.size;
      if (persistenceSucceeded) announce(`Se importaron ${count} calificaciones${bundle ? ` en ${bundle.cuts.length} cortes` : ""}.`);
    } catch (error) {
      announce(error instanceof Error ? error.message : "No se pudieron importar las calificaciones.", true);
    }
  });
  exportButton.addEventListener("click", () => {
    if (!dataset) return;
    if (bundle) {
      const file: BundleRatingsFile = bundleRatingsFile(bundle, bundleHash, ratingsByCut);
      downloadJson(file, "calificaciones-paquete.json", view);
      const count = file.cuts.reduce((sum, cut) => sum + cut.ratings.length, 0);
      announce(`Se exportaron ${count} calificaciones de ${file.cuts.length} cortes; incluye solo notas y decisiones, no respuestas.`);
    } else {
      downloadJson(ratingsFile(dataset, contentHash, ratings), "calificaciones.json", view);
      announce(`Se exportaron ${ratings.size} calificaciones, sin respuestas.`);
    }
  });
  filter.addEventListener("change", updateView);
  nav.addEventListener("keydown", (event) => {
    if (!(event instanceof view.KeyboardEvent)) return;
    if (["ArrowRight", "ArrowDown"].includes(event.key)) { event.preventDefault(); moveQuestion(1, true); }
    else if (["ArrowLeft", "ArrowUp"].includes(event.key)) { event.preventDefault(); moveQuestion(-1, true); }
    else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const indices = visible();
      const index = event.key === "Home" ? indices[0] : indices[indices.length - 1];
      if (index !== undefined) { selectedIndex = index; updateView(); nav.querySelector<HTMLButtonElement>(`[data-question-index="${index}"]`)?.focus(); }
    }
  });
  previous.addEventListener("click", () => { moveQuestion(-1); doc.querySelector<HTMLButtonElement>("#previous-question")?.focus(); });
  next.addEventListener("click", () => { moveQuestion(1); doc.querySelector<HTMLButtonElement>("#next-question")?.focus(); });
}

function ratingsFileForCut(cut: ReviewCut, ratings: RatingMap): ReturnType<typeof ratingsFile> {
  return ratingsFile(cut.dataset, cut.dataset_sha256, ratings);
}

function parseLegacyRatings(value: unknown, dataset: ReviewDataset, contentHash: string): RatingMap {
  return parseRatings(value, dataset, contentHash);
}
