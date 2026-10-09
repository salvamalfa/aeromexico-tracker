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

  it("accepts two-candidate data without adding a third alias", () => {
    const source = sampleDataset();
    source.questions = source.questions.slice(0, 1).map((question) => ({
      ...question,
      candidates: question.candidates.slice(0, 2),
    }));
    source.available_count = 2;
    const dataset = parseDataset(source);
    expect(dataset.questions[0]?.candidates.map(({ alias }) => alias)).toEqual(["A", "B"]);
    expect(dataset.available_count).toBe(2);

    const nonCanonicalAliases = sampleDataset();
    nonCanonicalAliases.questions = nonCanonicalAliases.questions.slice(0, 1).map((question) => ({
      ...question,
      candidates: [question.candidates[0]!, { ...question.candidates[1]!, alias: "C" }],
    }));
    nonCanonicalAliases.available_count = 2;
    expect(() => parseDataset(nonCanonicalAliases)).toThrow("los alias deben ser A/B o A/B/C");
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
    expect(document.querySelector("#question-text")?.textContent).toBe("Pregunta y respuestas");
    expect(document.querySelector("#expected-answer")?.textContent).toBe(malicious);
    expect(document.querySelector(".review-message-user .review-message-body")?.textContent).toBe(malicious);
    expect(document.querySelector(".review-message-assistant .review-message-body")?.textContent).toBe(malicious);
    expect(document.querySelector("img, script")).toBeNull();
  });

  it("interleaves user and assistant messages by their existing turn markers", () => {
    document.body.innerHTML = `
      <p id="question-position"></p><h2 id="question-text"></h2><p id="question-language"></p>
      <div id="expected-summary"></div><pre id="expected-answer"></pre><div id="candidate-list"></div>
      <button id="previous-question"></button><button id="next-question"></button>`;
    const source = sampleDataset();
    source.questions[0]!.question = "Mensaje del usuario · turno 1:\n¿Cuál fue la ocupación?\n\nMensaje del usuario · turno 2:\nNow in English, please.";
    source.questions[0]!.candidates[0]!.answer = "Respuesta del asistente · turno 1:\nFue 84.9%.\n\nRespuesta del asistente · turno 2:\nIt was 84.9%.";
    source.questions[0]!.candidates[1]!.answer = "Respuesta del asistente · turno 1:\n84.9%.\n\nRespuesta del asistente · turno 2:\n84.9 percent.";
    const dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    const messages = [...document.querySelectorAll<HTMLElement>(".candidate-card:first-child .review-message")];
    expect(messages.map((message) => message.classList.contains("review-message-user") ? "user" : "assistant"))
      .toEqual(["user", "assistant", "user", "assistant"]);
    expect(messages.map((message) => message.querySelector(".review-message-label")?.textContent))
      .toEqual(["Usuario · turno 1", "Asistente · turno 1", "Usuario · turno 2", "Asistente · turno 2"]);
    expect(messages[2]?.textContent).toContain("Now in English, please.");
    expect(document.querySelector(".candidate-card:first-child .candidate-original pre")?.textContent)
      .toBe(source.questions[0]!.candidates[0]!.answer);

    source.questions[0]!.question = [1, 2, 3].map((turn) => `Mensaje del usuario · turno ${turn}:\nPetición ${turn}.`).join("\n\n");
    source.questions[0]!.candidates[1]!.answer = [1, 2, 3].map((turn) => `Respuesta del asistente · turno ${turn}:\nRespuesta ${turn}.`).join("\n\n");
    const threeTurn = parseDataset(source);
    renderQuestion(threeTurn, 0, new Map(), false, true, () => undefined);
    const thirdCandidate = [...document.querySelectorAll<HTMLElement>(".candidate-card:nth-child(2) .review-message")];
    expect(thirdCandidate.map((message) => message.classList.contains("review-message-user") ? "user" : "assistant"))
      .toEqual(["user", "assistant", "user", "assistant", "user", "assistant"]);
    expect(thirdCandidate.map((message) => message.querySelector(".review-message-label")?.textContent))
      .toEqual(["Usuario · turno 1", "Asistente · turno 1", "Usuario · turno 2", "Asistente · turno 2", "Usuario · turno 3", "Asistente · turno 3"]);
  });

  it("keeps legacy text and falls back to raw safe rendering when turn markers are invalid or quoted", () => {
    document.body.innerHTML = `
      <p id="question-position"></p><h2 id="question-text"></h2><p id="question-language"></p>
      <div id="expected-summary"></div><pre id="expected-answer"></pre><div id="candidate-list"></div>
      <button id="previous-question"></button><button id="next-question"></button>`;
    const source = sampleDataset();
    source.questions[0]!.question = "Pregunta anterior completa";
    source.questions[0]!.candidates[0]!.answer = "Respuesta anterior completa";
    let dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    expect(document.querySelector(".review-message-user .review-message-label")?.textContent).toBe("Usuario");
    expect(document.querySelector(".review-message-assistant .review-message-label")?.textContent).toBe("Asistente");
    expect(document.querySelector(".review-message-user")?.textContent).toContain("Pregunta anterior completa");
    expect(document.querySelector(".review-message-assistant")?.textContent).toContain("Respuesta anterior completa");

    source.questions[0]!.question = "Mensaje del usuario · turno 1:\nPregunta.\n\nMensaje del usuario · turno 3:\nCita omitida.";
    source.questions[0]!.candidates[0]!.answer = "Respuesta del asistente · turno 1:\n```text\nMensaje del usuario · turno 2:\nCódigo literal\n```";
    dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    expect(document.querySelectorAll(".candidate-card:first-child .review-message-user")).toHaveLength(1);
    expect(document.querySelectorAll(".candidate-card:first-child .review-message-assistant")).toHaveLength(1);
    expect(document.querySelector(".candidate-card:first-child .review-message-body pre")?.textContent)
      .toContain("Mensaje del usuario · turno 2:");
    expect(document.querySelector(".candidate-card:first-child .review-message-body")?.textContent)
      .toContain("Mensaje del usuario · turno 3:");
    expect(document.querySelector("img, script")).toBeNull();
  });

  it("keeps unmarked prefixes in place and does not split marker-like text inside multiline HTML", () => {
    document.body.innerHTML = `
      <p id="question-position"></p><h2 id="question-text"></h2><p id="question-language"></p>
      <div id="expected-summary"></div><pre id="expected-answer"></pre><div id="candidate-list"></div>
      <button id="previous-question"></button><button id="next-question"></button>`;
    const source = sampleDataset();
    source.questions[0]!.candidates[0]!.answer = "Prefacio del asistente antes del turno.\n\nRespuesta del asistente · turno 1:\nRespuesta sintética.";
    let dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    let bodies = document.querySelectorAll<HTMLElement>(".candidate-card:first-child .review-message-assistant .review-message-body");
    expect(bodies).toHaveLength(1);
    const prefixed = bodies[0]!.textContent ?? "";
    expect(prefixed.indexOf("Prefacio del asistente")).toBeLessThan(prefixed.indexOf("Respuesta del asistente · turno 1:"));
    expect(prefixed.indexOf("Respuesta del asistente · turno 1:")).toBeLessThan(prefixed.indexOf("Respuesta sintética."));

    source.questions[0]!.candidates[0]!.answer = [
      "Respuesta del asistente · turno 1:",
      "Ejemplo HTML:",
      "<div>",
      "Respuesta del asistente · turno 2:",
      "marcador literal",
      "</div>",
    ].join("\n");
    dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    bodies = document.querySelectorAll<HTMLElement>(".candidate-card:first-child .review-message-assistant .review-message-body");
    expect(bodies).toHaveLength(1);
    expect(bodies[0]?.textContent).toContain("Respuesta del asistente · turno 2:");
    expect(bodies[0]?.querySelector("div")).toBeNull();

    source.questions[0]!.candidates[0]!.answer = [
      "Respuesta del asistente · turno 1:",
      "<!-- comentario inline -->",
      "<!-- comentario multilinea:",
      "Respuesta del asistente · turno 2:",
      "marcador literal",
      "-->",
    ].join("\n");
    dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    bodies = document.querySelectorAll<HTMLElement>(".candidate-card:first-child .review-message-assistant .review-message-body");
    expect(bodies).toHaveLength(1);
    expect(bodies[0]?.textContent).toContain("<!-- comentario inline -->");
    expect(bodies[0]?.textContent).toContain("Respuesta del asistente · turno 2:");
    expect(bodies[0]?.querySelector("div, script, img")).toBeNull();

    source.questions[0]!.candidates[0]!.answer = [
      "Respuesta del asistente · turno 1:",
      "<div>",
      "Respuesta del asistente · turno 2:",
      "marcador literal",
    ].join("\n");
    dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    bodies = document.querySelectorAll<HTMLElement>(".candidate-card:first-child .review-message-assistant .review-message-body");
    expect(bodies).toHaveLength(1);
    expect(bodies[0]?.textContent).toContain("Respuesta del asistente · turno 2:");
    expect(bodies[0]?.querySelector("div, script, img")).toBeNull();

    source.questions[0]!.candidates[0]!.answer = [
      "Respuesta del asistente · turno 1:",
      "<!--",
      "Respuesta del asistente · turno 2:",
      "marcador literal",
      "-->",
    ].join("\n");
    dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    bodies = document.querySelectorAll<HTMLElement>(".candidate-card:first-child .review-message-assistant .review-message-body");
    expect(bodies).toHaveLength(1);
    expect(bodies[0]?.textContent).toContain("Respuesta del asistente · turno 2:");
    expect([...bodies[0]!.childNodes].some((node) => node.nodeType === Node.COMMENT_NODE)).toBe(false);
  });

  it("shows application-context-rejected slots as not evaluable and without rating controls", () => {
    document.body.innerHTML = `
      <p id="question-position"></p><h2 id="question-text"></h2><p id="question-language"></p>
      <div id="expected-summary"></div><pre id="expected-answer"></pre><div id="candidate-list"></div>
      <button id="previous-question"></button><button id="next-question"></button>`;
    const source = sampleDataset();
    source.questions[0]!.expected = { application_context_rejected_aliases: ["A"] };
    source.questions[0]!.candidates[0]!.answer = null;
    source.available_count -= 1;
    const dataset = parseDataset(source);
    renderQuestion(dataset, 0, new Map(), false, true, () => undefined);
    const rejected = document.querySelector(".candidate-card:first-child");
    expect(rejected?.textContent).toContain("No evaluable: rechazado por el contexto de aplicación");
    expect(rejected?.querySelector(".rating-options")).toBeNull();
  });
});
