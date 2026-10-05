import { describe, expect, it } from "vitest";
import { webcrypto } from "node:crypto";
import { bundleRatingsFile, datasetFileBytes, parseBundleRatings, validateBundle } from "./bundle";
import { sha256Hex } from "./bootstrap";
import { parseDataset } from "./validation";
import { type RatingMap } from "./types";

function fixtureDataset() {
  return {
    schema_version: 1,
    dataset_id: "a".repeat(64),
    available_count: 2,
    questions: [{
      id: "Q01", question: "Pregunta sintética", language: "es", expected: { value: 1 },
      candidates: [
        { alias: "A", answer: "Respuesta sintética A" },
        { alias: "B", answer: "Respuesta sintética B" },
        { alias: "C", answer: null },
      ],
    }],
  };
}

async function makeBundle() {
  const dataset = parseDataset(fixtureDataset());
  const datasetSha = await sha256Hex(datasetFileBytes(dataset).slice().buffer as ArrayBuffer);
  const cut = (cutId: string, version: string) => ({
    cut_id: cutId,
    version,
    label: `Corte sintético ${cutId}`,
    disposition: "complete",
    source_sha256: dataset.dataset_id,
    dataset_sha256: datasetSha,
    dataset,
    slot_dispositions: [{ question_id: "Q01", alias: "C", status: "not_attempted" }],
  });
  const raw = {
    schema_version: 1,
    bundle_id: "synthetic-bundle",
    bundle_version: "1.0.0",
    title: "Paquete sintético",
    cuts: [cut("first", "1.0.0"), cut("second", "2.0.0")],
  };
  const sha = async (bytes: Uint8Array) => sha256Hex(bytes.slice().buffer as ArrayBuffer, webcrypto.subtle as unknown as SubtleCrypto);
  return { raw, bundle: await validateBundle(raw, sha), sha };
}

describe("review bundles", () => {
  it("validates every missing slot and rejects duplicate cuts or a changed dataset hash", async () => {
    const { raw, sha } = await makeBundle();
    await expect(validateBundle(raw, sha)).resolves.toHaveProperty("cuts.length", 2);
    const duplicate = structuredClone(raw);
    duplicate.cuts[1].cut_id = duplicate.cuts[0].cut_id;
    await expect(validateBundle(duplicate, sha)).rejects.toThrow("identificador inválido o repetido");
    const wrongHash = structuredClone(raw);
    wrongHash.cuts[0].dataset_sha256 = "f".repeat(64);
    await expect(validateBundle(wrongHash, sha)).rejects.toThrow("conjunto cambió o su hash no coincide");
    const noDisposition = structuredClone(raw);
    noDisposition.cuts[0].slot_dispositions = [];
    await expect(validateBundle(noDisposition, sha)).rejects.toThrow("cada espacio sin respuesta debe tener un estado explícito");
  });

  it("exports and imports every cut with independent grades and exact bundle binding", async () => {
    const { bundle } = await makeBundle();
    const bundleHash = "b".repeat(64);
    const first: RatingMap = new Map([[
      "Q01:A", { question_id: "Q01", alias: "A", status: "problem", notes: "Revisar cita" },
    ]]);
    const second: RatingMap = new Map([[
      "Q01:A", { question_id: "Q01", alias: "A", status: "correct", notes: "Correcta en este corte" },
    ]]);
    const file = bundleRatingsFile(bundle, bundleHash, new Map([["first", first], ["second", second]]));
    expect(file.schema_version).toBe(2);
    expect(file.cuts).toHaveLength(2);
    expect(file.cuts[0].ratings[0]?.status).toBe("problem");
    expect(file.cuts[1].ratings[0]?.status).toBe("correct");
    expect(JSON.stringify(file)).not.toContain("Respuesta sintética");
    const imported = parseBundleRatings(file, bundle, bundleHash);
    expect(imported.get("first")).toEqual(first);
    expect(imported.get("second")).toEqual(second);
    expect(() => parseBundleRatings(file, bundle, "c".repeat(64))).toThrow("paquete cambió");
    const conflict = structuredClone(file);
    conflict.cuts[1].cut_id = "first";
    expect(() => parseBundleRatings(conflict, bundle, bundleHash)).toThrow("cortes repetidos");
  });
});
