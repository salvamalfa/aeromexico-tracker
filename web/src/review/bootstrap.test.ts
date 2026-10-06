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

async function bundleFixture(bundleId = "cache-review") {
  const dataset = sourceDataset();
  const normalized = parseDataset(dataset);
  const datasetJson = `${JSON.stringify(normalized, null, 2)}\n`;
  const datasetBytes = new TextEncoder().encode(datasetJson);
  const datasetHash = await sha256Hex(datasetBytes.slice().buffer as ArrayBuffer);
  const missing = dataset.questions.flatMap((question) => question.candidates
    .filter((candidate) => candidate.answer === null)
    .map((candidate) => ({ question_id: question.id, alias: candidate.alias, status: "not_attempted" })));
  const cuts = ["first", "second"].map((cut_id, index) => ({
    cut_id, version: String(index + 1), label: cut_id, disposition: "complete",
    source_sha256: dataset.dataset_id, dataset_sha256: datasetHash, dataset_json: datasetJson,
    slot_dispositions: missing,
  }));
  const text = JSON.stringify({
    schema_version: 1, bundle_id: bundleId, bundle_version: "1", title: bundleId, cuts,
  });
  const bytes = new TextEncoder().encode(text);
  const bundleHash = await sha256Hex(bytes.slice().buffer as ArrayBuffer);
  return {
    dataset, datasetHash, bundleHash,
    file: { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File,
    grades: (first: unknown[], second: unknown[]) => ({
      schema_version: 2, bundle_id: bundleId, bundle_version: "1", bundle_content_sha256: bundleHash,
      cuts: ["first", "second"].map((cut_id, index) => ({
        cut_id, version: String(index + 1), dataset_id: dataset.dataset_id, dataset_sha256: datasetHash,
        ratings: index === 0 ? first : second,
      })),
    }),
  };
}

function jsonFile(value: unknown): File {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  return { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function selectFile(selector: string, file: File): void {
  const input = document.querySelector<HTMLInputElement>(selector)!;
  Object.defineProperty(input, "files", { configurable: true, value: [file] });
  input.dispatchEvent(new Event("change"));
}

async function exportJson(): Promise<unknown> {
  const createDescriptor = Object.getOwnPropertyDescriptor(window.URL, "createObjectURL");
  const revokeDescriptor = Object.getOwnPropertyDescriptor(window.URL, "revokeObjectURL");
  let exportedBlob: Blob | null = null;
  Object.defineProperty(window.URL, "createObjectURL", { configurable: true, value: (blob: Blob) => { exportedBlob = blob; return "blob:captured"; } });
  Object.defineProperty(window.URL, "revokeObjectURL", { configurable: true, value: () => {} });
  const anchorClick = vi.spyOn(window.HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  try {
    document.querySelector<HTMLButtonElement>("#export-button")?.click();
    const raw = await new Promise<string>((resolve, reject) => {
      if (!exportedBlob) return reject(new Error("No se creó el archivo de calificaciones."));
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(exportedBlob);
    });
    await new Promise((resolve) => window.setTimeout(resolve, 1));
    return JSON.parse(raw) as unknown;
  } finally {
    anchorClick.mockRestore();
    if (createDescriptor) Object.defineProperty(window.URL, "createObjectURL", createDescriptor);
    else delete (window.URL as unknown as { createObjectURL?: unknown }).createObjectURL;
    if (revokeDescriptor) Object.defineProperty(window.URL, "revokeObjectURL", revokeDescriptor);
    else delete (window.URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
  }
}

function storedRatings(datasetId: string, datasetHash: string, ratings: unknown[]): string {
  return JSON.stringify({ schema_version: 1, dataset_id: datasetId, dataset_content_sha256: datasetHash, ratings });
}

afterEach(() => {
  document.body.replaceChildren();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("review page bootstrap", () => {
  it("hydrates saved ratings from every cut before allowing an immediate package export", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const fixture = await bundleFixture("preloaded-two-cuts");
    const first = [{ question_id: "Q01", alias: "A", status: "correct", notes: "first saved" }];
    const second = [{ question_id: "Q02", alias: "B", status: "problem", notes: "second saved" }];
    for (const [cutId, values] of [["first", first], ["second", second]] as const) {
      window.localStorage.setItem(bundleStorageKey(fixture.bundleHash, cutId, fixture.datasetHash),
        storedRatings(fixture.dataset.dataset_id, fixture.datasetHash, values));
    }
    const storageWrite = vi.spyOn(window.localStorage, "setItem");
    document.querySelector<HTMLInputElement>("#cache-option")!.checked = true;
    bootstrapReview(document, window.localStorage);
    selectFile("#dataset-file", fixture.file);
    await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));

    expect(document.querySelector<HTMLSelectElement>("#cut-select")?.value).toBe("first");
    const exported = await exportJson() as { cuts: Array<{ cut_id: string; ratings: unknown[] }> };
    expect(exported.cuts.map((cut) => [cut.cut_id, cut.ratings])).toEqual([["first", first], ["second", second]]);
    expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("Se exportaron 2 calificaciones de 2 cortes");
    expect(storageWrite).not.toHaveBeenCalled();
  });

  it("detects a corrupt inactive cut on initial cached load and warns before exporting partial memory", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const fixture = await bundleFixture("corrupt-inactive-initial");
    const first = [{ question_id: "Q01", alias: "A", status: "correct", notes: "first retained" }];
    const firstKey = bundleStorageKey(fixture.bundleHash, "first", fixture.datasetHash);
    const secondKey = bundleStorageKey(fixture.bundleHash, "second", fixture.datasetHash);
    const savedFirst = storedRatings(fixture.dataset.dataset_id, fixture.datasetHash, first);
    const corruptSecond = "{corrupt inactive grades";
    window.localStorage.setItem(firstKey, savedFirst);
    window.localStorage.setItem(secondKey, corruptSecond);
    const storageWrite = vi.spyOn(window.localStorage, "setItem");
    document.querySelector<HTMLInputElement>("#cache-option")!.checked = true;
    bootstrapReview(document, window.localStorage);
    selectFile("#dataset-file", fixture.file);
    await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));

    const status = document.querySelector<HTMLElement>("#load-status")!;
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("0 / 74");
    expect(status.textContent).toContain("No se pudieron recuperar todos los cortes guardados");
    expect(status.dataset.error).toBe("true");
    const exported = await exportJson() as { cuts: Array<{ cut_id: string; ratings: unknown[] }> };
    expect(exported.cuts.map((cut) => [cut.cut_id, cut.ratings])).toEqual([
      ["first", []], ["second", []],
    ]);
    expect(status.textContent).toContain("puede omitir esas calificaciones");
    expect(status.dataset.error).toBe("true");
    expect(storageWrite).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(firstKey)).toBe(savedFirst);
    expect(window.localStorage.getItem(secondKey)).toBe(corruptSecond);

    document.querySelector<HTMLInputElement>("#cache-option")!.click();
    expect(status.textContent).toContain("El guardado local está desactivado");
    await exportJson();
    expect(status.textContent).toContain("este archivo puede omitir esas calificaciones");
    expect(status.textContent).toContain("El caché no se modificó");
    expect(status.dataset.error).toBe("true");
    expect(window.localStorage.getItem(firstKey)).toBe(savedFirst);
    expect(window.localStorage.getItem(secondKey)).toBe(corruptSecond);

    selectFile("#ratings-file", jsonFile(fixture.grades(first, [])));
    await vi.waitFor(() => expect(status.textContent).toContain("Se importaron 1 calificaciones"));
    await exportJson();
    expect(status.textContent).toContain("Se exportaron 1 calificaciones de 2 cortes");
    expect(status.textContent).not.toContain("puede omitir esas calificaciones");
    expect(window.localStorage.getItem(firstKey)).toBe(savedFirst);
    expect(window.localStorage.getItem(secondKey)).toBe(corruptSecond);
  });

  it("keeps a newer legacy dataset when an older bundle validation resolves or rejects late", async () => {
    document.body.innerHTML = reviewShell();
    const fixture = await bundleFixture("slow-old-bundle");
    const datasetBytes = new TextEncoder().encode(`${JSON.stringify(parseDataset(fixture.dataset), null, 2)}\n`);
    const originalDigest = webcrypto.subtle.digest.bind(webcrypto.subtle);
    for (const rejectOld of [false, true]) {
      document.body.innerHTML = reviewShell();
      const started = deferred<void>();
      const gate = deferred<ArrayBuffer>();
      let pause = true;
      vi.stubGlobal("crypto", { subtle: { digest(algorithm: AlgorithmIdentifier, data: BufferSource) {
        const length = data instanceof ArrayBuffer ? data.byteLength : data.byteLength;
        if (pause && length === datasetBytes.byteLength) {
          pause = false;
          started.resolve();
          return gate.promise;
        }
        return originalDigest(algorithm, data);
      } } } as unknown as Crypto);
      bootstrapReview(document, window.localStorage);
      selectFile("#dataset-file", fixture.file);
      await started.promise;
      const newer = sourceDataset();
      newer.questions[0]!.question = "Dataset nuevo confirmado";
      selectFile("#dataset-file", jsonFile(newer));
      await vi.waitFor(() => expect(document.querySelector("#question-text")?.textContent).toBe("Dataset nuevo confirmado"));
      const status = document.querySelector<HTMLElement>("#load-status")!;
      const newerStatus = status.textContent;
      if (rejectOld) gate.reject(new Error("digest viejo falló"));
      else gate.resolve(await originalDigest("SHA-256", datasetBytes));
      await new Promise((resolve) => window.setTimeout(resolve, 0));
      expect(document.querySelector("#question-text")?.textContent).toBe("Dataset nuevo confirmado");
      expect(status.textContent).toBe(newerStatus);
      vi.unstubAllGlobals();
    }
  });

  it("ignores a delayed ratings import after its dataset has been replaced", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const originalDigest = webcrypto.subtle.digest.bind(webcrypto.subtle);
    bootstrapReview(document, window.localStorage);
    selectFile("#dataset-file", jsonFile(sourceDataset()));
    await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));
    const grades = jsonFile({ schema_version: 1, dataset_id: "a".repeat(64), dataset_content_sha256: "b".repeat(64), ratings: [] });
    const bytes = new Uint8Array(await grades.arrayBuffer());
    const started = deferred<void>();
    const gate = deferred<ArrayBuffer>();
    let pause = true;
    vi.stubGlobal("crypto", { subtle: { digest(algorithm: AlgorithmIdentifier, data: BufferSource) {
      const length = data instanceof ArrayBuffer ? data.byteLength : data.byteLength;
      if (pause && length === bytes.byteLength) { pause = false; started.resolve(); return gate.promise; }
      return originalDigest(algorithm, data);
    } } } as unknown as Crypto);
    selectFile("#ratings-file", grades);
    await started.promise;
    const newer = sourceDataset();
    newer.questions[0]!.question = "Dataset que invalida importación";
    selectFile("#dataset-file", jsonFile(newer));
    await vi.waitFor(() => expect(document.querySelector("#question-text")?.textContent).toBe("Dataset que invalida importación"));
    const status = document.querySelector<HTMLElement>("#load-status")!;
    const newerStatus = status.textContent;
    gate.resolve(await originalDigest("SHA-256", bytes));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(document.querySelector("#question-text")?.textContent).toBe("Dataset que invalida importación");
    expect(status.textContent).toBe(newerStatus);
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("0 / 74");
  });

  it("keeps package-wide grade imports valid when only the active cut changes", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const fixture = await bundleFixture("cut-switch-during-import");
    bootstrapReview(document, window.localStorage);
    selectFile("#dataset-file", fixture.file);
    await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));
    const gradeValue = fixture.grades([{ question_id: "Q01", alias: "A", status: "correct", notes: "imported" }], []);
    const gradeBytes = new TextEncoder().encode(JSON.stringify(gradeValue));
    const originalDigest = webcrypto.subtle.digest.bind(webcrypto.subtle);
    const started = deferred<void>();
    const gate = deferred<ArrayBuffer>();
    let pause = true;
    vi.stubGlobal("crypto", { subtle: { digest(algorithm: AlgorithmIdentifier, data: BufferSource) {
      const length = data instanceof ArrayBuffer ? data.byteLength : data.byteLength;
      if (pause && length === gradeBytes.byteLength) { pause = false; started.resolve(); return gate.promise; }
      return originalDigest(algorithm, data);
    } } } as unknown as Crypto);
    selectFile("#ratings-file", jsonFile(gradeValue));
    await started.promise;
    const selector = document.querySelector<HTMLSelectElement>("#cut-select")!;
    selector.value = "second";
    selector.dispatchEvent(new Event("change"));
    gate.resolve(await originalDigest("SHA-256", gradeBytes));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("Se importaron 1 calificaciones"));
    selector.value = "first";
    selector.dispatchEvent(new Event("change"));
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");
  });

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

  it("merges edited keys over saved bundle grades and persists every edited cut", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const fixture = await bundleFixture();
    window.localStorage.setItem(bundleStorageKey(fixture.bundleHash, "first", fixture.datasetHash),
      storedRatings(fixture.dataset.dataset_id, fixture.datasetHash, [
        { question_id: "Q01", alias: "A", status: "problem", notes: "older value" },
        { question_id: "Q02", alias: "B", status: "correct", notes: "untouched value" },
      ]));
    bootstrapReview(document, window.localStorage);
    const input = document.querySelector<HTMLInputElement>("#dataset-file")!;
    Object.defineProperty(input, "files", { configurable: true, value: [fixture.file] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));

    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.click();
    const selector = document.querySelector<HTMLSelectElement>("#cut-select")!;
    selector.value = "second";
    selector.dispatchEvent(new Event("change"));
    document.querySelector<HTMLInputElement>('input[name="rating-Q01-B"][value="problem"]')?.click();
    document.querySelector<HTMLInputElement>("#cache-option")!.click();

    const first = JSON.parse(window.localStorage.getItem(bundleStorageKey(fixture.bundleHash, "first", fixture.datasetHash))!).ratings;
    const second = JSON.parse(window.localStorage.getItem(bundleStorageKey(fixture.bundleHash, "second", fixture.datasetHash))!).ratings;
    expect(first).toEqual([
      { question_id: "Q01", alias: "A", status: "correct", notes: "" },
      { question_id: "Q02", alias: "B", status: "correct", notes: "untouched value" },
    ]);
    expect(second).toEqual([{ question_id: "Q01", alias: "B", status: "problem", notes: "" }]);
    expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("Guardado local activado");
  });

  it("treats imported bundle grades as authoritative across cuts when caching is enabled later", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const fixture = await bundleFixture("authoritative-cache");
    const old = [{ question_id: "Q01", alias: "A", status: "problem", notes: "old saved grade" }];
    for (const cutId of ["first", "second"]) {
      window.localStorage.setItem(bundleStorageKey(fixture.bundleHash, cutId, fixture.datasetHash),
        storedRatings(fixture.dataset.dataset_id, fixture.datasetHash, old));
    }
    bootstrapReview(document, window.localStorage);
    const datasetInput = document.querySelector<HTMLInputElement>("#dataset-file")!;
    Object.defineProperty(datasetInput, "files", { configurable: true, value: [fixture.file] });
    datasetInput.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));

    const ratingsInput = document.querySelector<HTMLInputElement>("#ratings-file")!;
    Object.defineProperty(ratingsInput, "files", { configurable: true, value: [jsonFile(fixture.grades([], []))] });
    ratingsInput.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("Se importaron 0 calificaciones"));
    document.querySelector<HTMLInputElement>("#cache-option")!.click();

    for (const cutId of ["first", "second"]) {
      const saved = JSON.parse(window.localStorage.getItem(bundleStorageKey(fixture.bundleHash, cutId, fixture.datasetHash))!).ratings;
      expect(saved).toEqual([]);
    }
    expect(window.localStorage.length).toBe(2);
  });

  it("keeps bundle cache-read warnings visible and never overwrites a failed read", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const fixture = await bundleFixture("corrupt-cache");
    const corrupt = "{corrupt saved grades";
    const key = bundleStorageKey(fixture.bundleHash, "first", fixture.datasetHash);
    window.localStorage.setItem(key, corrupt);
    bootstrapReview(document, window.localStorage);
    document.querySelector<HTMLInputElement>("#cache-option")!.checked = true;
    const input = document.querySelector<HTMLInputElement>("#dataset-file")!;
    Object.defineProperty(input, "files", { configurable: true, value: [fixture.file] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));

    const status = document.querySelector<HTMLElement>("#load-status")!;
    expect(status.textContent).toContain("No se pudieron recuperar todos los cortes guardados");
    expect(status.dataset.error).toBe("true");
    document.querySelector<HTMLInputElement>("#cache-option")!.click();
    document.querySelector<HTMLInputElement>("#cache-option")!.click();
    expect(status.textContent).toContain("No se pudo leer el guardado local");
    expect(status.dataset.error).toBe("true");
    expect(window.localStorage.getItem(key)).toBe(corrupt);
  });

  it("keeps a later-cut cache warning visible while other cuts remain editable and exportable", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const fixture = await bundleFixture("later-cut-failure");
    const corrupt = "{corrupt second cut";
    const failedKey = bundleStorageKey(fixture.bundleHash, "second", fixture.datasetHash);
    window.localStorage.setItem(failedKey, corrupt);
    bootstrapReview(document, window.localStorage);
    document.querySelector<HTMLInputElement>("#cache-option")!.checked = true;
    const input = document.querySelector<HTMLInputElement>("#dataset-file")!;
    Object.defineProperty(input, "files", { configurable: true, value: [fixture.file] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));

    const selector = document.querySelector<HTMLSelectElement>("#cut-select")!;
    selector.value = "second";
    selector.dispatchEvent(new Event("change"));
    const status = document.querySelector<HTMLElement>("#load-status")!;
    expect(status.textContent).toContain("No se pudieron recuperar todos los cortes guardados");
    selector.value = "first";
    selector.dispatchEvent(new Event("change"));
    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.click();

    expect(status.textContent).toContain("No se pudieron recuperar todos los cortes guardados");
    expect(status.dataset.error).toBe("true");
    expect(document.querySelector<HTMLOutputElement>("#progress-count")?.value).toBe("1 / 74");
    expect(document.querySelector<HTMLButtonElement>("#export-button")?.disabled).toBe(false);
    expect(window.localStorage.getItem(failedKey)).toBe(corrupt);

    const createDescriptor = Object.getOwnPropertyDescriptor(window.URL, "createObjectURL");
    const revokeDescriptor = Object.getOwnPropertyDescriptor(window.URL, "revokeObjectURL");
    Object.defineProperty(window.URL, "createObjectURL", { configurable: true, value: () => "blob:recovery" });
    Object.defineProperty(window.URL, "revokeObjectURL", { configurable: true, value: () => {} });
    const anchorClick = vi.spyOn(window.HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    document.querySelector<HTMLButtonElement>("#export-button")?.click();
    expect(status.textContent).toContain("Se exportaron");
    expect(status.textContent).toContain("este archivo puede omitir esas calificaciones");
    await new Promise((resolve) => window.setTimeout(resolve, 1));
    anchorClick.mockRestore();
    if (createDescriptor) Object.defineProperty(window.URL, "createObjectURL", createDescriptor);
    else delete (window.URL as unknown as { createObjectURL?: unknown }).createObjectURL;
    if (revokeDescriptor) Object.defineProperty(window.URL, "revokeObjectURL", revokeDescriptor);
    else delete (window.URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
  });

  it("keeps legacy cache-read warnings visible after loading the dataset", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const dataset = sourceDataset();
    const bytes = new TextEncoder().encode(JSON.stringify(dataset));
    const hash = await sha256Hex(bytes.slice().buffer as ArrayBuffer);
    const key = storageKey(dataset.dataset_id, hash);
    const corrupt = "{corrupt legacy grades";
    window.localStorage.setItem(key, corrupt);
    bootstrapReview(document, window.localStorage);
    document.querySelector<HTMLInputElement>("#cache-option")!.checked = true;
    const input = document.querySelector<HTMLInputElement>("#dataset-file")!;
    Object.defineProperty(input, "files", { configurable: true, value: [{ size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File] });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#review-workspace")?.hasAttribute("hidden")).toBe(false));

    expect(document.querySelector<HTMLElement>("#load-status")?.textContent).toContain("No se pudo recuperar el guardado anterior");
    expect(document.querySelector<HTMLElement>("#load-status")?.dataset.error).toBe("true");
    expect(window.localStorage.getItem(key)).toBe(corrupt);
  });
});
