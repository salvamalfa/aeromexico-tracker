import { afterEach, describe, expect, it, vi } from "vitest";
import { webcrypto } from "node:crypto";
import { bootstrapReview, sha256Hex } from "./bootstrap";
import { datasetFileBytes } from "./bundle";
import { parseDataset } from "./validation";
import { storageKey } from "./storage";

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
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { value: [file] });
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
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { value: [file] });
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
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { value: [file] });
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

  it("imports one bundle, switches cut-local progress, and keeps aliases scoped to each cut", async () => {
    document.body.innerHTML = reviewShell();
    vi.stubGlobal("crypto", webcrypto as unknown as Crypto);
    const dataset = sourceDataset();
    const normalizedDataset = parseDataset(dataset);
    const datasetBytes = datasetFileBytes(normalizedDataset);
    const datasetHash = await sha256Hex(datasetBytes.slice().buffer as ArrayBuffer);
    const sourceHash = dataset.dataset_id;
    const missing = dataset.questions.flatMap((question) => question.candidates
      .filter((candidate) => candidate.answer === null)
      .map((candidate) => ({ question_id: question.id, alias: candidate.alias, status: "not_attempted" })));
    const cut = (cut_id: string, version: string) => ({
      cut_id, version, label: cut_id === "original" ? "Corte original" : "MVP actual",
      disposition: "complete", source_sha256: sourceHash, dataset_sha256: datasetHash,
      dataset, slot_dispositions: missing,
    });
    const bundleText = JSON.stringify({
      schema_version: 1, bundle_id: "synthetic-review", bundle_version: "1.0.0", title: "Paquete sintético",
      cuts: [cut("original", "1.0.0"), cut("current", "2.0.0")],
    });
    const bytes = new TextEncoder().encode(bundleText);
    const file = { size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
    bootstrapReview(document, window.localStorage);
    Object.defineProperty(document.querySelector("#dataset-file"), "files", { value: [file] });
    document.querySelector<HTMLInputElement>("#dataset-file")?.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(document.querySelector("#cut-controls")?.hasAttribute("hidden")).toBe(false));

    expect(document.querySelectorAll("#cut-select option")).toHaveLength(2);
    expect(document.querySelector("#cut-status")?.textContent).toContain("74 respuestas disponibles");
    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.click();
    expect((document.querySelector("#progress-count") as HTMLOutputElement)?.value).toBe("1 / 74");
    const selector = document.querySelector<HTMLSelectElement>("#cut-select")!;
    selector.value = "current";
    selector.dispatchEvent(new Event("change"));
    expect((document.querySelector("#progress-count") as HTMLOutputElement)?.value).toBe("0 / 74");
    document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="correct"]')?.click();
    selector.value = "original";
    selector.dispatchEvent(new Event("change"));
    expect((document.querySelector("#progress-count") as HTMLOutputElement)?.value).toBe("1 / 74");
    expect(document.querySelector<HTMLInputElement>('input[name="rating-Q01-A"][value="problem"]')?.checked).toBe(true);
    expect(window.localStorage.length).toBe(0);
  });
});
