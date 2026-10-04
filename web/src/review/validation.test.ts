import { describe, expect, it } from "vitest";
import { renderQuestion } from "./render";
import { loadRatings, saveRatings, storageKey } from "./storage";
import { parseDataset, parseRatings, ratingsFile } from "./validation";

const datasetId = "a".repeat(64);
const contentHash = "c".repeat(64);

function sampleDataset(): {
  schema_version: number;
  dataset_id: string;
  questions: Array<{
    id: string;
    question: string;
    language: string;
    expected: unknown;
    candidates: Array<{ alias: string; answer: string | null }>;
  }>;
  available_count: number;
} {
  const questions = Array.from({ length: 40 }, (_, index) => {
    const id = `Q${String(index + 1).padStart(2, "0")}`;
    return {
      id,
      question: `Pregunta ${index + 1}`,
      language: index % 2 ? "en" : "es",
      expected: { value: index, safe: "texto" },
      candidates: ["A", "B", "C"].map((alias, candidateIndex) => ({
        alias,
        answer: index < 24 || (index === 24 && candidateIndex < 2) ? `Respuesta ${id}-${alias}` : null,
      })),
    };
  });
  return { schema_version: 1, dataset_id: datasetId, questions, available_count: 74 };
}

describe("blind review file validation", () => {
  it("accepts the agreed dataset and confirms the count of non-null answers", () => {
    const dataset = parseDataset(sampleDataset());
    expect(dataset.questions).toHaveLength(40);
    expect(dataset.available_count).toBe(74);
    expect(dataset.questions[39].candidates[0].answer).toBeNull();
  });

  it("rejects malformed, aliased, extra-field, or count-mismatched source data", () => {
    const wrongCount = sampleDataset();
    wrongCount.available_count = 75;
    expect(() => parseDataset(wrongCount)).toThrow("contiene 74");

    const wrongAlias = sampleDataset();
    wrongAlias.questions[0].candidates[0].alias = "Sol";
    expect(() => parseDataset(wrongAlias)).toThrow("alias de candidato inválido");

    const leakedMapping = sampleDataset() as ReturnType<typeof sampleDataset> & { model_ids?: unknown };
    leakedMapping.model_ids = ["private-model-id"];
    expect(() => parseDataset(leakedMapping)).toThrow("estructura inválida");
  });

  it("round-trips only ratings and rejects a different dataset or missing answer", () => {
    const dataset = parseDataset(sampleDataset());
    const raw = {
      schema_version: 1,
      dataset_id: dataset.dataset_id,
      dataset_content_sha256: contentHash,
      ratings: [{ question_id: "Q01", alias: "A", status: "problem", notes: "No cita la cifra." }],
    };
    const ratings = parseRatings(raw, dataset, contentHash);
    const exported = ratingsFile(dataset, contentHash, ratings);
    expect(JSON.stringify(exported)).not.toContain("Respuesta Q01-A");
    expect(exported).toEqual(raw);
    expect(() => parseRatings({ ...raw, dataset_id: "b".repeat(64) }, dataset, contentHash)).toThrow("otro conjunto");
    expect(() => parseRatings({ ...raw, dataset_content_sha256: "d".repeat(64) }, dataset, contentHash))
      .toThrow("contenido del archivo de respuestas cambió");
    expect(() => parseRatings({ ...raw, ratings: [{ ...raw.ratings[0], question_id: "Q40", alias: "B" }] }, dataset, contentHash))
      .toThrow("no existe una respuesta");
  });

  it("stores decisions locally under the dataset hash", () => {
    const dataset = parseDataset(sampleDataset());
    const ratings = parseRatings({
      schema_version: 1,
      dataset_id: dataset.dataset_id,
      dataset_content_sha256: contentHash,
      ratings: [{ question_id: "Q01", alias: "C", status: "correct", notes: "" }],
    }, dataset, contentHash);
    saveRatings(dataset, contentHash, ratings, window.localStorage);
    expect(window.localStorage.getItem(storageKey(dataset.dataset_id, contentHash))).toContain('"status":"correct"');
    expect(loadRatings(dataset, contentHash, window.localStorage)).toEqual(ratings);
    expect(loadRatings(dataset, "d".repeat(64), window.localStorage)).toEqual(new Map());
  });

  it("renders question, expected value, and candidate answer strictly as text", () => {
    document.body.innerHTML = `
      <p id="question-position"></p><h2 id="question-text"></h2><p id="question-language"></p>
      <div id="expected-summary"></div><pre id="expected-answer"></pre><div id="candidate-list"></div>
      <button id="previous-question"></button><button id="next-question"></button>`;
    const malicious = '<img src=x onerror="window.__reviewXss=true">';
    const source = sampleDataset();
    source.questions[0].question = malicious;
    source.questions[0].expected = malicious;
    source.questions[0].candidates[0].answer = malicious;
    const dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    expect(document.querySelector("#question-text")?.textContent).toBe(malicious);
    expect(document.querySelector("#expected-answer")?.textContent).toBe(malicious);
    expect(document.querySelector(".candidate-answer")?.textContent).toBe(malicious);
    expect(document.querySelector("img, script")).toBeNull();
  });
});
