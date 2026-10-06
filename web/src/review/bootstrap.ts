import { bundleRatingsFile, parseBundleRatings, validateBundle } from "./bundle";
import { type BundleRatingsFile, type Rating, type RatingMap, type ReviewBundle, type ReviewCut, type ReviewDataset, ratingKey } from "./types";
import { bundleStorageKey, loadRatings, saveRatings } from "./storage";
import { renderNavigation, renderProgress, renderQuestion } from "./render";
import { type QuestionFilter, visibleQuestionIndices } from "./filters";
import { parseDataset, parseRatings, ratingsFile } from "./validation";
import { loadCutRatings, loadMissingBundleRatings, persistBundleRatings } from "./cache";
import { downloadJson, isRecord, readJsonFile } from "./files";

export async function sha256Hex(bytes: ArrayBuffer, subtle: SubtleCrypto = crypto.subtle): Promise<string> {
  const digest = await subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function requireNode<T extends Element>(root: ParentNode, selector: string): T {
  const node = root.querySelector<T>(selector);
  if (!node) throw new Error(`Falta el elemento requerido: ${selector}`);
  return node;
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
  let legacyCacheLoaded = false;
  let legacyRatingsAuthoritative = false;
  const modifiedRatingKeys = new Set<string>();
  const modifiedRatingsByCut = new Map<string, Set<string>>();
  let canPersist = true;
  let cacheFailureWarning = false;
  let selectedIndex = 0;
  const visible = () => dataset ? visibleQuestionIndices(dataset, ratings, filter.value as QuestionFilter) : [];

  const announce = (message: string, error = false) => {
    if (!error && cacheOption.checked && cacheFailureWarning) {
      if (message.startsWith("Se exportaron")) {
        loadStatus.textContent = `${message} El guardado local sigue indisponible; conserva este archivo antes de salir.`;
        loadStatus.setAttribute("data-error", "true");
      }
      return;
    }
    loadStatus.textContent = message;
    loadStatus.setAttribute("data-error", String(error));
  };
  const activeSlotStates = () => new Map((activeCut?.slot_dispositions ?? []).map((slot) => [
    ratingKey(slot.question_id, slot.alias), slot.status,
  ]));
  const hasCurrentRatings = () => bundle
    ? [...ratingsByCut.values()].some((map) => map.size > 0)
    : ratings.size > 0;
  const mayReplaceCurrentImport = (incomingHash: string, incomingBundle: boolean): boolean => {
    const sameFileAlreadyLoaded = incomingBundle
      ? Boolean(bundle && bundleHash === incomingHash)
      : Boolean(!bundle && dataset && contentHash === incomingHash);
    if (sameFileAlreadyLoaded) {
      announce("Este archivo ya está cargado; se conserva el progreso actual y el corte seleccionado.");
      return false;
    }
    if (hasCurrentRatings() && !view.confirm("Este archivo reemplazará calificaciones en memoria. Exporta el progreso actual antes de continuar si quieres conservarlo. ¿Continuar?")) {
      announce("Importación cancelada; se conserva el archivo y el progreso actuales.");
      return false;
    }
    return true;
  };
  const persistActiveRatings = (): boolean => {
    if (!cacheOption.checked || !dataset) return true;
    if (!canPersist) return false;
    try {
      if (bundle && activeCut) {
        getStorage().setItem(bundleStorageKey(bundleHash, activeCut.cut_id, activeCut.dataset_sha256),
          JSON.stringify(ratingsFile(activeCut.dataset, activeCut.dataset_sha256, ratings)));
      } else {
        legacyCacheLoaded = true;
        saveRatings(dataset, contentHash, ratings, getStorage());
      }
      return true;
    } catch {
      canPersist = false;
      cacheFailureWarning = true;
      announce("No se pudo guardar en este navegador. Exporta las calificaciones antes de salir.", true);
      return false;
    }
  };
  const persistAllBundleRatings = (): boolean => {
    if (!cacheOption.checked || !bundle) return true;
    if (!canPersist) return false;
    try {
      persistBundleRatings(bundle, bundleHash, ratingsByCut, getStorage());
      return true;
    } catch {
      canPersist = false;
      cacheFailureWarning = true;
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
        modifiedRatingKeys.add(key);
        if (!status) ratings.delete(key);
        else ratings.set(key, { question_id: questionId, alias, status, notes });
        if (bundle && activeCut) {
          ratingsByCut.set(activeCut.cut_id, ratings);
          const modified = modifiedRatingsByCut.get(activeCut.cut_id) ?? new Set<string>();
          modified.add(key);
          modifiedRatingsByCut.set(activeCut.cut_id, modified);
        }
        persistActiveRatings();
        updateSidebar();
      }, activeSlotStates());
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
    let cacheReadFailed = false;
    const missingCounts = { no_answer: 0, failed: 0, held: 0, not_attempted: 0 };
    for (const slot of selected.slot_dispositions) missingCounts[slot.status] += 1;
    cutStatus.textContent = `${selected.disposition === "terminal" ? "Corte terminal" : selected.disposition === "complete" ? "Corte completo" : "Corte parcial"} · ${selected.dataset.questions.length} preguntas · ${selected.dataset.available_count} respuestas disponibles · ${missingCounts.no_answer} sin respuesta, ${missingCounts.failed} con error, ${missingCounts.held} en espera, ${missingCounts.not_attempted} no intentadas.`;
    if (cacheOption.checked && canPersist && !loadedBundleCuts.has(selected.cut_id)) {
      try {
        const stored = loadCutRatings(selected, bundleHash, getStorage());
        if (stored.size || !ratings.size) ratings = stored;
        ratingsByCut.set(selected.cut_id, ratings);
        loadedBundleCuts.add(selected.cut_id);
      } catch {
        canPersist = false;
        cacheFailureWarning = true;
        cacheReadFailed = true;
        announce("No se pudo recuperar el guardado anterior. Se conserva el trabajo en memoria y el paquete puede exportarse.", true);
      }
    }
    updateView();
    if (announceSelection && !cacheReadFailed && !(cacheOption.checked && cacheFailureWarning)) {
      announce(`Corte seleccionado: ${selected.label}. Su progreso está separado de los demás cortes.`);
    }
    return cacheReadFailed;
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
        const prepared = loadMissingBundleRatings(bundle, bundleHash, ratingsByCut, loadedBundleCuts,
          modifiedRatingsByCut, getStorage());
        ratingsByCut = prepared.ratingsByCut;
        loadedBundleCuts = prepared.loadedCuts;
        if (activeCut) ratings = ratingsByCut.get(activeCut.cut_id) ?? new Map();
      } else {
        if (!legacyCacheLoaded) {
          if (!legacyRatingsAuthoritative) {
            const stored = loadRatings(dataset, contentHash, getStorage());
            const merged = new Map(stored);
            ratings.forEach((rating, key) => merged.set(key, rating));
            for (const key of modifiedRatingKeys) {
              if (ratings.has(key)) merged.set(key, ratings.get(key)!);
              else merged.delete(key);
            }
            ratings = merged;
          }
          legacyCacheLoaded = true;
        }
      }
      canPersist = true;
      const persisted = bundle ? persistAllBundleRatings() : persistActiveRatings();
      updateView();
      if (persisted) {
        cacheFailureWarning = false;
        announce("Guardado local activado. Se usa una clave vinculada al hash exacto del archivo y, para paquetes, al corte.");
      }
    } catch {
      canPersist = false;
      cacheFailureWarning = true;
      announce("No se pudo leer el guardado local; se conserva sin cambios. Puedes exportar el progreso.", true);
    }
  });

  datasetInput.addEventListener("change", async () => {
    const file = datasetInput.files?.[0];
    datasetInput.value = "";
    if (!file) return;
    try {
      let cacheReadFailed = false;
      const imported = await readJsonFile(file, sha256Hex);
      if (isRecord(imported.value) && "cuts" in imported.value) {
        const parsedBundle = await validateBundle(imported.value, async (bytes) =>
          sha256Hex(bytes.slice().buffer as ArrayBuffer));
        if (!mayReplaceCurrentImport(imported.contentHash, true)) return;
        activeCut = null;
        bundle = parsedBundle;
        bundleHash = imported.contentHash;
        contentHash = "";
        ratings = new Map();
        ratingsByCut = new Map();
        loadedBundleCuts = new Set();
        legacyCacheLoaded = false;
        legacyRatingsAuthoritative = false;
        modifiedRatingKeys.clear();
        modifiedRatingsByCut.clear();
        bundle.cuts.forEach((cut) => ratingsByCut.set(cut.cut_id, new Map()));
        canPersist = true;
        cacheFailureWarning = false;
        bundleTitle.textContent = `${bundle.title} · versión ${bundle.bundle_version}`;
        cutSelect.replaceChildren(...bundle.cuts.map((cut) => {
          const option = doc.createElement("option");
          option.value = cut.cut_id;
          option.textContent = `${cut.label} · ${cut.version}`;
          return option;
        }));
        cutControls.hidden = false;
        const cacheReadFailed = chooseCut(bundle.cuts[0].cut_id);
        importButton.disabled = false;
        exportButton.disabled = false;
        workspace.hidden = false;
        if (!cacheReadFailed && !(cacheOption.checked && cacheFailureWarning)) {
          announce(`Paquete cargado: ${bundle.cuts.length} cortes versionados. El hash del paquete y cada corte se verificaron.`);
        }
      } else {
        const parsedDataset = parseDataset(imported.value);
        if (!mayReplaceCurrentImport(imported.contentHash, false)) return;
        dataset = parsedDataset;
        bundle = null;
        activeCut = null;
        bundleHash = "";
        contentHash = imported.contentHash;
        ratings = new Map();
        ratingsByCut = new Map();
        loadedBundleCuts = new Set();
        legacyCacheLoaded = false;
        legacyRatingsAuthoritative = false;
        modifiedRatingKeys.clear();
        modifiedRatingsByCut.clear();
        cacheFailureWarning = false;
        cutControls.hidden = true;
        if (cacheOption.checked) {
          try { ratings = loadRatings(dataset, contentHash, getStorage()); canPersist = true; legacyCacheLoaded = true; }
          catch {
            canPersist = false;
            cacheFailureWarning = true;
            cacheReadFailed = true;
            announce("No se pudo recuperar el guardado anterior. Se conserva sin cambios; exporta las calificaciones.", true);
          }
        } else canPersist = true;
        selectedIndex = 0;
        workspace.hidden = false;
        importButton.disabled = false;
        exportButton.disabled = false;
        updateView();
        if (!cacheReadFailed && !(cacheOption.checked && cacheFailureWarning)) {
          announce(`Archivo cargado: ${dataset.questions.length} preguntas y ${dataset.available_count} respuestas disponibles.`);
        }
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
      const imported = await readJsonFile(file, sha256Hex);
      const incoming = bundle
        ? parseBundleRatings(imported.value, bundle, bundleHash)
        : parseRatings(imported.value, dataset, contentHash);
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
        modifiedRatingsByCut.clear();
        if (activeCut) ratings = ratingsByCut.get(activeCut.cut_id) ?? new Map();
      } else {
        ratings = incoming as RatingMap;
        legacyRatingsAuthoritative = true;
        legacyCacheLoaded = true;
        modifiedRatingKeys.clear();
      }
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
