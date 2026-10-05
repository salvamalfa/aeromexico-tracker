import {
  type BundleRatingsFile,
  type CandidateAlias,
  type RatingMap,
  type ReviewBundle,
  type ReviewCut,
  type ReviewDataset,
  type SlotDisposition,
} from "./types";
import { parseDataset, parseRatings, ratingsFile } from "./validation";
import { ratingKey } from "./types";

const hashPattern = /^[a-f0-9]{64}$/;
const cutIdPattern = /^[a-z0-9][a-z0-9-]{0,63}$/;
const aliases: CandidateAlias[] = ["A", "B", "C"];
const missingStatuses = ["no_answer", "failed", "held", "not_attempted"] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function record(value: unknown, label: string, keys: string[]): Record<string, unknown> {
  if (!isRecord(value) || !exactKeys(value, keys)) throw new Error(`${label}: estructura inválida.`);
  return value;
}

function boundedText(value: unknown, label: string, max: number): string {
  if (typeof value !== "string" || !value.trim() || value.length > max) {
    throw new Error(`${label}: texto inválido.`);
  }
  return value;
}

/** Bytes emitted by scripts/chat/export_review_dataset.py for a normalized dataset. */
export function datasetFileBytes(dataset: ReviewDataset): Uint8Array {
  return new TextEncoder().encode(`${JSON.stringify(dataset, null, 2)}\n`);
}

export async function validateBundle(value: unknown, sha256: (bytes: Uint8Array) => Promise<string>): Promise<ReviewBundle> {
  const data = record(value, "Paquete de revisión", ["schema_version", "bundle_id", "bundle_version", "title", "cuts"]);
  if (data.schema_version !== 1) throw new Error("Versión de paquete no compatible.");
  const bundleId = boundedText(data.bundle_id, "Identificador de paquete", 100);
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(bundleId)) throw new Error("Identificador de paquete inválido.");
  const bundleVersion = boundedText(data.bundle_version, "Versión de paquete", 80);
  const title = boundedText(data.title, "Título de paquete", 160);
  if (!Array.isArray(data.cuts) || data.cuts.length < 1 || data.cuts.length > 10) {
    throw new Error("El paquete debe contener entre 1 y 10 cortes.");
  }
  const seenCutIds = new Set<string>();
  const cuts: ReviewCut[] = [];
  for (const [index, rawCut] of data.cuts.entries()) {
    const label = `Corte ${index + 1}`;
    const item = record(rawCut, label, [
      "cut_id", "version", "label", "disposition", "source_sha256", "dataset_sha256", "dataset", "slot_dispositions",
    ]);
    const cutId = boundedText(item.cut_id, `${label} identificador`, 64);
    if (!cutIdPattern.test(cutId) || seenCutIds.has(cutId)) throw new Error(`${label}: identificador inválido o repetido.`);
    seenCutIds.add(cutId);
    const version = boundedText(item.version, `${label} versión`, 80);
    const cutLabel = boundedText(item.label, `${label} nombre`, 120);
    if (!["terminal", "complete", "partial"].includes(String(item.disposition))) {
      throw new Error(`${label}: disposición inválida.`);
    }
    if (typeof item.source_sha256 !== "string" || !hashPattern.test(item.source_sha256)) {
      throw new Error(`${label}: digest de origen inválido.`);
    }
    if (typeof item.dataset_sha256 !== "string" || !hashPattern.test(item.dataset_sha256)) {
      throw new Error(`${label}: hash del conjunto inválido.`);
    }
    const dataset = parseDataset(item.dataset);
    if (item.source_sha256 !== dataset.dataset_id) {
      throw new Error(`${label}: el digest de origen no coincide con el conjunto.`);
    }
    const calculatedDatasetHash = await sha256(datasetFileBytes(dataset));
    if (item.dataset_sha256 !== calculatedDatasetHash) {
      throw new Error(`${label}: el conjunto cambió o su hash no coincide.`);
    }
    if (!Array.isArray(item.slot_dispositions) || item.slot_dispositions.length > dataset.questions.length * aliases.length) {
      throw new Error(`${label}: estados de respuestas faltantes inválidos.`);
    }
    const declared = new Map<string, SlotDisposition>();
    for (const [slotIndex, rawSlot] of item.slot_dispositions.entries()) {
      const slot = record(rawSlot, `${label}, estado ${slotIndex + 1}`, ["question_id", "alias", "status"]);
      if (typeof slot.question_id !== "string" || !/^Q\d{2}$/.test(slot.question_id)) {
        throw new Error(`${label}: pregunta de estado inválida.`);
      }
      if (typeof slot.alias !== "string" || !aliases.includes(slot.alias as CandidateAlias)) {
        throw new Error(`${label}: alias de estado inválido.`);
      }
      if (typeof slot.status !== "string" || !missingStatuses.includes(slot.status as typeof missingStatuses[number])) {
        throw new Error(`${label}: estado de respuesta inválido.`);
      }
      const key = ratingKey(slot.question_id, slot.alias as CandidateAlias);
      if (declared.has(key)) throw new Error(`${label}: estado de respuesta repetido.`);
      declared.set(key, {
        question_id: slot.question_id,
        alias: slot.alias as CandidateAlias,
        status: slot.status as SlotDisposition["status"],
      });
    }
    const expectedMissing = new Set<string>();
    for (const question of dataset.questions) {
      for (const candidate of question.candidates) {
        const key = ratingKey(question.id, candidate.alias);
        if (candidate.answer === null) expectedMissing.add(key);
        else if (declared.has(key)) throw new Error(`${label}: una respuesta disponible tiene una disposición de ausencia.`);
      }
    }
    if (expectedMissing.size !== declared.size || [...expectedMissing].some((key) => !declared.has(key))) {
      throw new Error(`${label}: cada espacio sin respuesta debe tener un estado explícito.`);
    }
    cuts.push({
      cut_id: cutId,
      version,
      label: cutLabel,
      disposition: item.disposition as ReviewCut["disposition"],
      source_sha256: item.source_sha256,
      dataset_sha256: item.dataset_sha256,
      dataset,
      slot_dispositions: [...declared.values()],
    });
  }
  return { schema_version: 1, bundle_id: bundleId, bundle_version: bundleVersion, title, cuts };
}

export function parseBundleRatings(
  value: unknown,
  bundle: ReviewBundle,
  bundleHash: string,
): Map<string, RatingMap> {
  if (!hashPattern.test(bundleHash)) throw new Error("El hash del paquete no es válido.");
  const data = record(value, "Archivo de calificaciones", [
    "schema_version", "bundle_id", "bundle_version", "bundle_content_sha256", "cuts",
  ]);
  if (data.schema_version !== 2) throw new Error("Versión de calificaciones de paquete no compatible.");
  if (data.bundle_id !== bundle.bundle_id || data.bundle_version !== bundle.bundle_version) {
    throw new Error("Las calificaciones pertenecen a otro paquete.");
  }
  if (data.bundle_content_sha256 !== bundleHash) throw new Error("El archivo de paquete cambió; no se aplicaron las calificaciones.");
  if (!Array.isArray(data.cuts) || data.cuts.length !== bundle.cuts.length) {
    throw new Error("El archivo debe incluir exactamente todos los cortes del paquete.");
  }
  const byCut = new Map<string, RatingMap>();
  const seen = new Set<string>();
  for (const [index, rawCut] of data.cuts.entries()) {
    const row = record(rawCut, `Calificaciones del corte ${index + 1}`, [
      "cut_id", "version", "dataset_id", "dataset_sha256", "ratings",
    ]);
    if (typeof row.cut_id !== "string" || seen.has(row.cut_id)) throw new Error("El archivo contiene cortes repetidos o inválidos.");
    seen.add(row.cut_id);
    const cut = bundle.cuts.find((candidate) => candidate.cut_id === row.cut_id);
    if (!cut || row.version !== cut.version || row.dataset_id !== cut.dataset.dataset_id || row.dataset_sha256 !== cut.dataset_sha256) {
      throw new Error(`Las calificaciones del corte ${row.cut_id} no corresponden a este paquete.`);
    }
    const map = parseRatings({
      schema_version: 1,
      dataset_id: row.dataset_id,
      dataset_content_sha256: row.dataset_sha256,
      ratings: row.ratings,
    }, cut.dataset, cut.dataset_sha256);
    byCut.set(cut.cut_id, map);
  }
  if (seen.size !== bundle.cuts.length) throw new Error("Falta un corte en las calificaciones.");
  return byCut;
}

export function bundleRatingsFile(
  bundle: ReviewBundle,
  bundleHash: string,
  ratingsByCut: Map<string, RatingMap>,
): BundleRatingsFile {
  return {
    schema_version: 2,
    bundle_id: bundle.bundle_id,
    bundle_version: bundle.bundle_version,
    bundle_content_sha256: bundleHash,
    cuts: bundle.cuts.map((cut) => ({
      cut_id: cut.cut_id,
      version: cut.version,
      dataset_id: cut.dataset.dataset_id,
      dataset_sha256: cut.dataset_sha256,
      ratings: ratingsFile(cut.dataset, cut.dataset_sha256, ratingsByCut.get(cut.cut_id) ?? new Map()).ratings,
    })),
  };
}
