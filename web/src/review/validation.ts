import {
  type CandidateAlias,
  type Rating,
  type RatingMap,
  type RatingStatus,
  type RatingsFile,
  type ReviewDataset,
  ratingKey,
} from "./types";

const aliases: CandidateAlias[] = ["A", "B", "C"];
const statuses: RatingStatus[] = ["correct", "problem", "not_evaluable"];
const hashPattern = /^[a-f0-9]{64}$/;
const questionPattern = /^Q\d{2}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function requireRecord(value: unknown, label: string, keys: string[]): Record<string, unknown> {
  if (!isRecord(value) || !hasExactKeys(value, keys)) {
    throw new Error(`${label}: estructura inválida.`);
  }
  return value;
}

export function parseDataset(value: unknown): ReviewDataset {
  const data = requireRecord(value, "Archivo de respuestas", [
    "schema_version", "dataset_id", "questions", "available_count",
  ]);
  if (data.schema_version !== 1) throw new Error("Versión de archivo no compatible.");
  if (typeof data.dataset_id !== "string" || !hashPattern.test(data.dataset_id)) {
    throw new Error("El archivo no incluye un hash SHA-256 válido.");
  }
  if (!Number.isSafeInteger(data.available_count) || (data.available_count as number) < 0) {
    throw new Error("El total de respuestas disponibles no es válido.");
  }
  if (!Array.isArray(data.questions) || data.questions.length === 0 || data.questions.length > 74) {
    throw new Error("El archivo debe contener entre 1 y 74 preguntas.");
  }

  const ids = new Set<string>();
  let availableAnswers = 0;
  const questions = data.questions.map((rawQuestion, index) => {
    const label = `Pregunta ${index + 1}`;
    const question = requireRecord(rawQuestion, label, [
      "id", "question", "language", "expected", "candidates",
    ]);
    if (typeof question.id !== "string" || !questionPattern.test(question.id) || ids.has(question.id)) {
      throw new Error(`${label}: identificador ausente, inválido o repetido.`);
    }
    ids.add(question.id);
    if (typeof question.question !== "string" || !question.question.trim() || question.question.length > 10_000) {
      throw new Error(`${label}: texto de pregunta inválido.`);
    }
    if (typeof question.language !== "string" || !question.language.trim() || question.language.length > 40) {
      throw new Error(`${label}: idioma inválido.`);
    }
    if (!Array.isArray(question.candidates) || question.candidates.length < 2 || question.candidates.length > aliases.length) {
      throw new Error(`${label}: se esperan dos o tres candidatos anónimos.`);
    }
    const seen = new Set<CandidateAlias>();
    const candidates = question.candidates.map((rawCandidate, candidateIndex) => {
      const candidate = requireRecord(rawCandidate, `${label}, candidato ${candidateIndex + 1}`, ["alias", "answer"]);
      if (typeof candidate.alias !== "string" || !aliases.includes(candidate.alias as CandidateAlias)) {
        throw new Error(`${label}: alias de candidato inválido.`);
      }
      const alias = candidate.alias as CandidateAlias;
      if (seen.has(alias)) throw new Error(`${label}: alias de candidato repetido.`);
      seen.add(alias);
      if (candidate.answer !== null && typeof candidate.answer !== "string") {
        throw new Error(`${label}, candidato ${alias}: la respuesta debe ser texto o null.`);
      }
      if (typeof candidate.answer === "string") availableAnswers += 1;
      return { alias, answer: candidate.answer as string | null };
    });
    if (seen.size !== candidates.length) throw new Error(`${label}: falta un alias de candidato.`);
    return {
      id: question.id,
      question: question.question,
      language: question.language,
      expected: question.expected,
      candidates,
    };
  });
  if (availableAnswers !== data.available_count) {
    throw new Error(`El archivo declara ${data.available_count} respuestas, pero contiene ${availableAnswers}.`);
  }
  return {
    schema_version: 1,
    dataset_id: data.dataset_id,
    questions,
    available_count: data.available_count as number,
  };
}

export function parseRatings(value: unknown, dataset: ReviewDataset, contentHash: string): RatingMap {
  if (!hashPattern.test(contentHash)) throw new Error("El hash del archivo de respuestas no es válido.");
  const data = requireRecord(value, "Archivo de calificaciones", [
    "schema_version", "dataset_id", "dataset_content_sha256", "ratings",
  ]);
  if (data.schema_version !== 1) throw new Error("Versión de calificaciones no compatible.");
  if (data.dataset_id !== dataset.dataset_id) throw new Error("Las calificaciones pertenecen a otro conjunto de respuestas.");
  if (data.dataset_content_sha256 !== contentHash) {
    throw new Error("El contenido del archivo de respuestas cambió; no se aplicaron estas calificaciones.");
  }
  if (!Array.isArray(data.ratings) || data.ratings.length > dataset.available_count) {
    throw new Error("La lista de calificaciones no es válida.");
  }
  const answers = new Set<string>();
  for (const question of dataset.questions) {
    for (const candidate of question.candidates) {
      if (candidate.answer !== null) answers.add(ratingKey(question.id, candidate.alias));
    }
  }
  const ratings: RatingMap = new Map();
  for (const [index, rawRating] of data.ratings.entries()) {
    const item = requireRecord(rawRating, `Calificación ${index + 1}`, [
      "question_id", "alias", "status", "notes",
    ]);
    if (typeof item.question_id !== "string" || !questionPattern.test(item.question_id)) {
      throw new Error(`Calificación ${index + 1}: pregunta inválida.`);
    }
    if (typeof item.alias !== "string" || !aliases.includes(item.alias as CandidateAlias)) {
      throw new Error(`Calificación ${index + 1}: alias inválido.`);
    }
    if (typeof item.status !== "string" || !statuses.includes(item.status as RatingStatus)) {
      throw new Error(`Calificación ${index + 1}: decisión inválida.`);
    }
    if (typeof item.notes !== "string" || item.notes.length > 2_000) {
      throw new Error(`Calificación ${index + 1}: las notas exceden el límite permitido.`);
    }
    const alias = item.alias as CandidateAlias;
    const key = ratingKey(item.question_id, alias);
    if (!answers.has(key)) throw new Error(`Calificación ${index + 1}: no existe una respuesta para ese alias.`);
    if (ratings.has(key)) throw new Error(`Calificación ${index + 1}: registro duplicado.`);
    ratings.set(key, {
      question_id: item.question_id,
      alias,
      status: item.status as RatingStatus,
      notes: item.notes,
    });
  }
  return ratings;
}

export function ratingsFile(dataset: ReviewDataset, contentHash: string, ratings: RatingMap): RatingsFile {
  const order = new Map(dataset.questions.map((question, index) => [question.id, index]));
  const aliasOrder = new Map(aliases.map((alias, index) => [alias, index]));
  const entries = [...ratings.values()].sort((left, right) => {
    const questionDifference = (order.get(left.question_id) ?? Number.MAX_SAFE_INTEGER)
      - (order.get(right.question_id) ?? Number.MAX_SAFE_INTEGER);
    return questionDifference || (aliasOrder.get(left.alias) ?? 0) - (aliasOrder.get(right.alias) ?? 0);
  });
  return {
    schema_version: 1,
    dataset_id: dataset.dataset_id,
    dataset_content_sha256: contentHash,
    ratings: entries,
  };
}
