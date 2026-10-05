import { afterEach, describe, expect, it, vi } from "vitest";
import { webcrypto } from "node:crypto";
import { bootstrapReview, sha256Hex } from "./bootstrap";
import { parseDataset } from "./validation";
import { bundleStorageKey, storageKey } from "./storage";

function reviewShell(): string {
  return `
    <input id="dataset-file" type="file"><input id="ratings-file" type="file">
    <button id="import-button"></button><button id="export-button"></button>
    <p id="load-status"></p><label><input id="cache-option" type="checkbox"></label>
    <section id="cut-controls" hidden><h2 id="bundle-title"></h2><select id="cut-select"></select><p id="cut-status"></p></section>
    <section id="review-workspace" hidden>
      <output id="progress-count"></output><progress id="review-progress"></progress><p id="progress-detail"></p>
      <strong id="count-correct"></strong><strong id="count-problem"></strong>
      <strong id="count-not-evaluable"></strong><strong id="count-unreviewed"></strong>
      <select id="question-filter"><option value="all">Todas</option><option value="pending">Pendientes</option>
        <option value="reviewed">Revisadas</option><option value="problems">Con problemas</option></select>
      <p id="filter-empty"></p><ol id="question-nav"></ol>
      <div id="question-content"><p id="selection-filter-note" hidden></p><p id="question-position"></p><h2 id="question-text"></h2>
        <p id="question-language"></p><div id="expected-summary"></div><pre id="expected-answer"></pre>
        <div id="candidate-list"></div><button id="previous-question"></button><button id="next-question"></button>
      </div>
    </section>
  `;
}

function sourceDataset() {
  return {
    schema_version: 1,
    dataset_id: "a".repeat(64),
    available_count: 74,
    questions: Array.from({ length: 40 }, (_, index) => ({
      id: `Q${String(index + 1).padStart(2, "0")}`,
      question: `Pregunta ${index + 1}`,
      language: "es",
      expected: { status: "supported", rows: [] },
      candidates: ["A", "B", "C"].map((alias, candidateIndex) => ({
        alias,
        answer: index < 24 || (index === 24 && candidateIndex < 2) ? `Respuesta ${index + 1}/${alias}` : null,
      })),
    })),
  };
}

afterEach(() => {
  document.body.replaceChildren();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("review page bootstrap", () => {
  it("starts with an empty shell and performs no network request", () => {
    document.body.innerHTML = reviewShell();
    const fetchSpy = vi.fn();
    const getSpy = vi.fn(() => null);
    const setSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    bootstrapReview(document, { getItem: getSpy, setItem: setSpy } as unknown as Storage);

    expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(getSpy).not.toHaveBeenCalled();
    expect(setSpy).not.toHaveBeenCalled();
  });

  it("does not touch the storage getter until local caching is enabled", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const descriptor = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() { throw new Error("storage getter blocked"); },
    });
    try {
      expect(() => bootstrapReview(document)).not.toThrow();
      const bytes = new TextEncoder().encode(JSON.stringify(sourceDataset()));
      const file = { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
      Object.defineProperty(document.querySelector("#dataset-file"), "files", { value: [file] });
      document.querySelector<HTMLInputElement>("#dataset-file")?.dispatchEvent(new Event("change"));
      await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));

      document.querySelector<HTMLInputElement>("#cache-option")!.click();
      expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("No se pudo leer el guardado local");
      document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.click();
      expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");
    } finally {
      if (descriptor) Object.defineProperty(window, "localStorage", descriptor);
    }
  });

  it("hashes the exact file bytes, so whitespace edits receive a distinct identity", async () => {
    const first = new TextEncoder().encode('{"dataset_id":"sheet-hash"}').buffer;
    const edited = new TextEncoder().encode('{ "dataset_id": "sheet-hash" }').buffer;
    const subtle = webcrypto.subtle as unknown as SubtleCrypto;
    const firstHash = await sha256Hex(first, subtle);
    const editedHash = await sha256Hex(edited, subtle);
    expect(firstHash).toMatch(/^[a-f0-9]{64}$/);
    expect(editedHash).not.toBe(firstHash);
  });

  it("filters questions and supports arrow/Home/End navigation without changing global progress", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    bootstrapReview(document, window.localStorage);
    const text = JSON.stringify(sourceDataset());
    const bytes = new TextEncoder().encode(text);
    const file = { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { configurable: true, value: [file] });
    document.querySelector<HTMLInputElement>("#dataset-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));

    const nav = document.querySelector<HTMLOListElement>("#question-nav")!;
    expect(nav.querySelectorAll("button")).toHaveLength(40);
    expect(nav.querySelectorAll('button[tabindex="0"]')).toHaveLength(1);
    nav.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(document.querySelector("#question-position")?.textContent).toContain("Q02");
    nav.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));
    expect(document.querySelector("#question-position")?.textContent).toContain("Q01");

    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.click();
    const filter = document.querySelector<HTMLSelectElement>("#question-filter")!;
    filter.value = "problems";
    filter.dispatchEvent(new Event("change", { bubbles: true }));
    expect([...nav.querySelectorAll<HTMLButtonElement>("button")].map((button) => button.dataset.questionIndex))
      .toEqual(["0"]);
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");
  });

  it("keeps a just-reviewed question open while pending filter navigation stays keyboard reachable", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    bootstrapReview(document, window.localStorage);
    const bytes = new TextEncoder().encode(JSON.stringify(sourceDataset()));
    const file = { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { configurable: true, value: [file] });
    document.querySelector<HTMLInputElement>("#dataset-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));

    const filter = document.querySelector<HTMLSelectElement>("#question-filter")!;
    filter.value = "pending";
    filter.dispatchEvent(new Event("change", { bubbles: true }));
    for (const alias of ["A", "B", "C"]) {
      document.querySelector<HTMLInputElement>(`input[name="rating-Q01-${alias}"][value="correct"]`)?.click();
    }

    expect(document.querySelector("#question-position")?.textContent).toContain("Q01");
    expect(document.querySelector<HTMLElement>("#selection-filter-note")?.hidden).toBe(false);
    const nav = document.querySelector<HTMLOListElement>("#question-nav")!;
    expect(nav.querySelector<HTMLButtonElement>('button[tabindex="0"]')?.textContent).toContain("Q02");
    const notes = document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Notas para candidato A"]')!;
    expect(notes.disabled).toBe(false);
    notes.value = "Revisada y anotada";
    notes.dispatchEvent(new Event("input", { bubbles: true }));

    nav.querySelector<HTMLButtonElement>('button[tabindex="0"]')!.focus();
    nav.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(document.querySelector("#question-position")?.textContent).toContain("Q02");
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("3 / 74");
  });

  it("preserves an unreadable saved blob while allowing an in-memory review", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const text = JSON.stringify(sourceDataset());
    const bytes = new TextEncoder().encode(text);
    const contentHash = await sha256Hex(bytes.buffer);
    const key = storageKey("a".repeat(64), contentHash);
    const original = "{corrupt saved ratings";
    window.localStorage.setItem(key, original);
    bootstrapReview(document, window.localStorage);
    const file = { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { configurable: true, value: [file] });
    document.querySelector<HTMLInputElement>("#dataset-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));
    document.querySelector<HTMLInputElement>("#cache-option")!.click();

    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.click();

    expect(window.localStorage.getItem(key)).toBe(original);
    expect(document.querySelector<HTMLElement>("#load-status")?.textContent)
      .toContain("Puedes exportar el progreso");
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");
    expect(document.querySelector<HTMLButtonElement>("#export-button")?.disabled).toBe(false);
  });

  it("merges legacy cache without losing current work and treats imported grades as authoritative", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const dataset = sourceDataset();
    const bytes = new TextEncoder().encode(JSON.stringify(dataset));
    const contentHash = await sha256Hex(bytes.slice().buffer as ArrayBuffer);
    const key = storageKey(dataset.dataset_id, contentHash);
    window.localStorage.setItem(key, JSON.stringify({
      schema_version: 1,
      dataset_id: dataset.dataset_id,
      dataset_content_sha256: contentHash,
      ratings: [
        { question_id: "Q01", alias: "A", status: "problem", notes: "older saved grade" },
        { question_id: "Q02", alias: "B", status: "correct", notes: "older independent grade" },
      ],
    }));
    bootstrapReview(document, window.localStorage);
    const input = document.querySelector<HTMLInputElement>("#dataset-file")!;
    const file = { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));

    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.click();
    document.querySelector<HTMLInputElement>("#cache-option")!.click();
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.checked).toBe(true);
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("2 / 74");
    const merged = JSON.parse(window.localStorage.getItem(key)!).ratings as Array<{ question_id: string; alias: string; status: string }>;
    expect(merged.find((rating) => rating.question_id === "Q01" && rating.alias === "A")?.status).toBe("correct");
    expect(merged.find((rating) => rating.question_id === "Q02" && rating.alias === "B")?.status).toBe("correct");

    document.querySelector<HTMLInputElement>("#cache-option")!.click();
    const importedGrades = {
      schema_version: 1,
      dataset_id: dataset.dataset_id,
      dataset_content_sha256: contentHash,
      ratings: [{ question_id: "Q01", alias: "A", status: "not_evaluable", notes: "imported replacement" }],
    };
    const gradeBytes = new TextEncoder().encode(JSON.stringify(importedGrades));
    const gradeFile = { size: gradeBytes.byteLength, arrayBuffer: async () => gradeBytes.buffer } as File;
    Object.defineProperty(document.querySelector("#ratings-file"), "files", { configurable: true, value: [gradeFile] });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    document.querySelector<HTMLInputElement>("#ratings-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("Se importaron"));
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");

    document.querySelector<HTMLInputElement>("#cache-option")!.click();
    const replaced = JSON.parse(window.localStorage.getItem(key)!).ratings as Array<{ question_id: string; alias: string; status: string }>;
    expect(replaced).toEqual([{ question_id: "Q01", alias: "A", status: "not_evaluable", notes: "imported replacement" }]);
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");
  });

  it("validates then asks before replacing a legacy review, and cancel keeps identity and selection", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    bootstrapReview(document, window.localStorage);
    const dataset = sourceDataset();
    const bytes = new TextEncoder().encode(JSON.stringify(dataset));
    const input = document.querySelector<HTMLInputElement>("#dataset-file")!;
    const file = { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));
    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.click();
    document.querySelector<HTMLButtonElement>('#question-nav button[data-question-index="1"]')?.click();
    const confirmation = vi.spyOn(window, "confirm").mockReturnValue(false);

    const different = structuredClone(dataset);
    different.questions[1]!.question = "Pregunta alternativa sintética";
    const differentBytes = new TextEncoder().encode(JSON.stringify(different));
    const differentFile = { size: differentBytes.byteLength, arrayBuffer: async () => differentBytes.buffer } as File;
    Object.defineProperty(input, "files", { configurable: true, value: [differentFile] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("Importación cancelada"));
    expect(confirmation).toHaveBeenCalledTimes(1);
    expect(document.querySelector("#question-position")?.textContent).toContain("Q02");
    expect(document.querySelector("#question-text")?.textContent).toBe("Pregunta 2");
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");

    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent)
      .toContain("se conserva el progreso actual"));
    expect(confirmation).toHaveBeenCalledTimes(1);
    expect(document.querySelector("#question-position")?.textContent).toContain("Q02");
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");
    document.querySelector<HTMLButtonElement>('#question-nav button[data-question-index="0"]')?.click();
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.checked).toBe(true);
  });

  it("confirms a different valid bundle before replacement and keeps the active cut on cancel", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const dataset = sourceDataset();
    const datasetJson = `${JSON.stringify(parseDataset(dataset), null, 2)}\n`;
    const datasetBytes = new TextEncoder().encode(datasetJson);
    const datasetHash = await sha256Hex(datasetBytes.slice().buffer as ArrayBuffer);
    const missing = dataset.questions.flatMap((question) => question.candidates
      .filter((candidate) => candidate.answer === null)
      .map((candidate) => ({ question_id: question.id, alias: candidate.alias, status: "not_attempted" })));
    const cut = (cut_id: string) => ({
      cut_id, version: "1", label: cut_id, disposition: "complete", source_sha256: dataset.dataset_id,
      dataset_sha256: datasetHash, dataset_json: datasetJson, slot_dispositions: missing,
    });
    const makeBundle = (bundle_id: string) => JSON.stringify({
      schema_version: 1, bundle_id, bundle_version: "1", title: bundle_id,
      cuts: [cut("first"), cut("second")],
    });
    const text = makeBundle("original-bundle");
    const bytes = new TextEncoder().encode(text);
    const file = { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
    bootstrapReview(document, window.localStorage);
    const input = document.querySelector<HTMLInputElement>("#dataset-file")!;
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));
    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.click();
    const selector = document.querySelector<HTMLSelectElement>("#cut-select")!;
    selector.value = "second";
    selector.dispatchEvent(new Event("change"));
    document.querySelector<HTMLInputElement>('input[name="rating-Q01-B"][value="correct"]')?.click();
    const confirmation = vi.spyOn(window, "confirm").mockReturnValue(false);

    const replacementBytes = new TextEncoder().encode(makeBundle("replacement-bundle"));
    const replacementFile = { size: replacementBytes.byteLength, arrayBuffer: async () => replacementBytes.buffer } as File;
    Object.defineProperty(input, "files", { configurable: true, value: [replacementFile] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("Importación cancelada"));

    expect(confirmation).toHaveBeenCalledTimes(1);
    expect(document.querySelector("#bundle-title")?.textContent).toContain("original-bundle");
    expect(document.querySelector<HTMLSelectElement>("#cut-select")?.value).toBe("second");
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-B"][value="correct"]')?.checked).toBe(true);
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");

    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent)
      .toContain("se conserva el progreso actual"));
    expect(confirmation).toHaveBeenCalledTimes(1);
    expect(document.querySelector<HTMLSelectElement>("#cut-select")?.value).toBe("second");
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-B"][value="correct"]')?.checked).toBe(true);
  });

  it("imports one bundle, switches cut-local progress, and keeps aliases scoped to each cut", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const dataset = sourceDataset();
    const normalizedDataset = parseDataset(dataset);
    const datasetJson = `${JSON.stringify(normalizedDataset, null, 2)}\n`;
    const datasetBytes = new TextEncoder().encode(datasetJson);
    const datasetHash = await sha256Hex(datasetBytes.slice().buffer as ArrayBuffer);
    const sourceHash = dataset.dataset_id;
    const missing = dataset.questions.flatMap((question) => question.candidates
      .filter((candidate) => candidate.answer === null)
      .map((candidate) => ({ question_id: question.id, alias: candidate.alias, status: "not_attempted" })));
    const cut = (cut_id: string, version: string) => ({
      cut_id, version, label: cut_id === "original" ? "Corte original" : "MVP actual",
      disposition: "complete", source_sha256: sourceHash, dataset_sha256: datasetHash,
      dataset_json: datasetJson, slot_dispositions: missing,
    });
    const bundleText = JSON.stringify({
      schema_version: 1, bundle_id: "synthetic-review", bundle_version: "1.0.0", title: "Paquete sintético",
      cuts: [cut("original", "1.0.0"), cut("current", "2.0.0")],
    });
    const bytes = new TextEncoder().encode(bundleText);
    const bundleHash = await sha256Hex(bytes.slice().buffer as ArrayBuffer);
    const file = { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
    bootstrapReview(document, window.localStorage);
    window.localStorage.setItem(bundleStorageKey(bundleHash, "current", datasetHash), JSON.stringify({
      schema_version: 1,
      dataset_id: sourceHash,
      dataset_content_sha256: datasetHash,
      ratings: [{ question_id: "Q01", alias: "A", status: "problem", notes: "saved old rating" }],
    }));
    document.querySelector<HTMLInputElement>("#cache-option")!.checked = true;
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { configurable: true, value: [file] });
    document.querySelector<HTMLInputElement>("#dataset-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));

    expect(document.querySelectorAll("#cut-select option")).toHaveLength(2);
    expect(document.querySelector("#cut-status")?.textContent).toContain("74 respuestas disponibles");
    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.click();
    expect((document.querySelector("#progress-count") as HTMLOutputElement)?.value).toBe("1 / 74");
    let selector = document.querySelector<HTMLSelectElement>("#cut-select")!;
    selector.value = "current";
    selector.dispatchEvent(new Event("change"));
    expect((document.querySelector("#progress-count") as HTMLOutputElement)?.value).toBe("1 / 74");
    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.click();
    selector.value = "original";
    selector.dispatchEvent(new Event("change"));
    expect((document.querySelector("#progress-count") as HTMLOutputElement)?.value).toBe("1 / 74");
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.checked).toBe(true);

    const grades = {
      schema_version: 2,
      bundle_id: "synthetic-review",
      bundle_version: "1.0.0",
      bundle_content_sha256: bundleHash,
      cuts: [
        { cut_id: "original", version: "1.0.0", dataset_id: sourceHash, dataset_sha256: datasetHash, ratings: [] },
        { cut_id: "current", version: "2.0.0", dataset_id: sourceHash, dataset_sha256: datasetHash,
          ratings: [{ question_id: "Q01", alias: "A", status: "correct", notes: "new imported grade" }] },
      ],
    };
    const gradesBytes = new TextEncoder().encode(JSON.stringify(grades));
    const gradesFile = { size: gradesBytes.byteLength, arrayBuffer: async () => gradesBytes.buffer } as File;
    Object.defineProperty(document.querySelector("#ratings-file"), "files", { configurable: true, value: [gradesFile] });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    document.querySelector<HTMLInputElement>("#ratings-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("Se importaron"));
    const currentStorageKey = bundleStorageKey(bundleHash, "current", datasetHash);
    expect(JSON.parse(window.localStorage.getItem(currentStorageKey)!).ratings[0].status).toBe("correct");

    const reloadAndSelectCurrent = async (): Promise<HTMLSelectElement> => {
      document.body.innerHTML = reviewShell();
      bootstrapReview(document, window.localStorage);
      document.querySelector<HTMLInputElement>("#cache-option")!.checked = true;
      Object.defineProperty(document.querySelector("#dataset-file"), "files", { configurable: true, value: [file] });
      document.querySelector<HTMLInputElement>("#dataset-file")?.dispatchEvent(new Event("change"));
      await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));
      const freshSelector = document.querySelector<HTMLSelectElement>("#cut-select")!;
      freshSelector.value = "current";
      freshSelector.dispatchEvent(new Event("change"));
      return freshSelector;
    };

    selector = await reloadAndSelectCurrent();
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.checked).toBe(true);

    grades.cuts[1]!.ratings = [];
    const clearedBytes = new TextEncoder().encode(JSON.stringify(grades));
    const clearedFile = { size: clearedBytes.byteLength, arrayBuffer: async () => clearedBytes.buffer } as File;
    Object.defineProperty(document.querySelector("#ratings-file"), "files", { configurable: true, value: [clearedFile] });
    document.querySelector<HTMLInputElement>("#ratings-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("Se importaron 0 calificaciones"));
    expect(JSON.parse(window.localStorage.getItem(currentStorageKey)!).ratings).toEqual([]);

    selector = await reloadAndSelectCurrent();
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.checked).toBe(false);
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.checked).toBe(false);

    // Invalid replacement must keep this refreshed bundle and its grades bound to the uploaded bytes.
    const invalidBundle = JSON.parse(bundleText) as { cuts: Array<Record<string, unknown>> };
    invalidBundle.cuts[0]!.dataset_sha256 = "f".repeat(64);
    const invalidBytes = new TextEncoder().encode(JSON.stringify(invalidBundle));
    const invalidFile = { size: invalidBytes.byteLength, arrayBuffer: async () => invalidBytes.buffer } as File;
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { configurable: true, value: [invalidFile] });
    document.querySelector<HTMLInputElement>("#dataset-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.dataset.error).toBe("true"));
    expect(document.querySelector<HTMLSelectElement>("#cut-select")?.value).toBe("current");
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.checked).toBe(false);
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.checked).toBe(false);
    expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false);

    const createDescriptor = Object.getOwnPropertyDescriptor(window.URL, "createObjectURL");
    const revokeDescriptor = Object.getOwnPropertyDescriptor(window.URL, "revokeObjectURL");
    let exportedBlob: Blob | null = null;
    Object.defineProperty(window.URL, "createObjectURL", {
      configurable: true,
      value: (blob: Blob) => { exportedBlob = blob; return "blob:synthetic"; },
    });
    Object.defineProperty(window.URL, "revokeObjectURL", { configurable: true, value: () => {} });
    const anchorClick = vi.spyOn(window.HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    document.querySelector<HTMLButtonElement>("#export-button")?.click();
    const exportedText = await new Promise<string>((resolve, reject) => {
      if (!exportedBlob) return reject(new Error("No se creó el archivo de calificaciones."));
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(exportedBlob);
    });
    expect(JSON.parse(exportedText).bundle_content_sha256).toBe(bundleHash);
    await new Promise((resolve) => window.setTimeout(resolve, 1));
    anchorClick.mockRestore();
    if (createDescriptor) Object.defineProperty(window.URL, "createObjectURL", createDescriptor);
    else delete (window.URL as unknown as { createObjectURL?: unknown }).createObjectURL;
    if (revokeDescriptor) Object.defineProperty(window.URL, "revokeObjectURL", revokeDescriptor);
    else delete (window.URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
    expect(window.localStorage.length).toBe(2);
  });

  it("keeps imported cut grades exportable and warns when saving all cuts fails", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const dataset = sourceDataset();
    const datasetJson = `${JSON.stringify(parseDataset(dataset), null, 2)}\n`;
    const datasetBytes = new TextEncoder().encode(datasetJson);
    const datasetHash = await sha256Hex(datasetBytes.slice().buffer as ArrayBuffer);
    const missing = dataset.questions.flatMap((question) => question.candidates
      .filter((candidate) => candidate.answer === null)
      .map((candidate) => ({ question_id: question.id, alias: candidate.alias, status: "not_attempted" })));
    const cut = (cut_id: string, version: string) => ({
      cut_id, version, label: cut_id, disposition: "complete", source_sha256: dataset.dataset_id,
      dataset_sha256: datasetHash, dataset_json: datasetJson, slot_dispositions: missing,
    });
    const bundleText = JSON.stringify({
      schema_version: 1, bundle_id: "storage-failure", bundle_version: "1", title: "Paquete sintético",
      cuts: [cut("first", "1"), cut("second", "2")],
    });
    const bundleBytes = new TextEncoder().encode(bundleText);
    const bundleHash = await sha256Hex(bundleBytes.slice().buffer as ArrayBuffer);
    let writeCount = 0;
    const storage = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(() => { writeCount += 1; if (writeCount === 2) throw new Error("storage full"); }),
    } as unknown as Storage;
    bootstrapReview(document, storage);
    document.querySelector<HTMLInputElement>("#cache-option")!.checked = true;
    const bundleFile = { size: bundleBytes.byteLength, arrayBuffer: async () => bundleBytes.buffer } as File;
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { configurable: true, value: [bundleFile] });
    document.querySelector<HTMLInputElement>("#dataset-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));

    const grades = {
      schema_version: 2,
      bundle_id: "storage-failure",
      bundle_version: "1",
      bundle_content_sha256: bundleHash,
      cuts: [
        { cut_id: "first", version: "1", dataset_id: dataset.dataset_id, dataset_sha256: datasetHash,
          ratings: [{ question_id: "Q01", alias: "A", status: "correct", notes: "first cut" }] },
        { cut_id: "second", version: "2", dataset_id: dataset.dataset_id, dataset_sha256: datasetHash,
          ratings: [{ question_id: "Q02", alias: "B", status: "problem", notes: "second cut" }] },
      ],
    };
    const gradeBytes = new TextEncoder().encode(JSON.stringify(grades));
    const gradeFile = { size: gradeBytes.byteLength, arrayBuffer: async () => gradeBytes.buffer } as File;
    Object.defineProperty(document.querySelector("#ratings-file"), "files", { configurable: true, value: [gradeFile] });
    document.querySelector<HTMLInputElement>("#ratings-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent)
      .toContain("Las calificaciones siguen en memoria"));

    expect(storage.setItem).toHaveBeenCalledTimes(2);
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");
    expect(document.querySelector<HTMLButtonElement>("#export-button")?.disabled).toBe(false);
    expect(document.querySelector<HTMLElement>("#load-status")?.dataset.error).toBe("true");
  });
});
