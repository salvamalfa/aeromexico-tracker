import { describe, expect, it } from "vitest";
import { webcrypto } from "node:crypto";
import { bundleRatingsFile, parseBundleRatings, validateBundle } from "./bundle";
import { sha256Hex } from "./bootstrap";
import { parseDataset } from "./validation";
import { type RatingMap } from "./types";

function fixtureDataset() {
  return {
    schema_version: 1,
    dataset_id: "a".repeat(64),
    available_count: 3,
    questions: [{
      id: "Q01", question: "Pregunta sintética", language: "es", expected: { "10": "diez", "2": "dos", value: 1 },
      candidates: [
        { alias: "A", answer: "Respuesta sintética A" },
        { alias: "B", answer: "Respuesta sintética B" },
        { alias: "C", answer: null },
        { alias: "D", answer: "Respuesta sintética D" },
      ],
    }],
  };
}

async function makeBundle() {
  const dataset = parseDataset(fixtureDataset());
  const reordered = {
    questions: dataset.questions,
    available_count: dataset.available_count,
    dataset_id: dataset.dataset_id,
    schema_version: dataset.schema_version,
  };
  const sourceText = JSON.stringify(reordered, null, 2);
  const datasetJson = `${sourceText.replace(/"2": "dos",\n(\s*)"10": "diez",/, '"10": "diez",\n$1"2": "dos",').replace('"value": 1', '"value": 1.0')}\n`;
  const datasetBytes = new TextEncoder().encode(datasetJson);
  const datasetSha = await sha256Hex(datasetBytes.slice().buffer as ArrayBuffer);
  const cut = (cutId: string, version: string) => ({
    cut_id: cutId,
    version,
    label: `Corte sintético ${cutId}`,
    disposition: "complete",
    source_sha256: dataset.dataset_id,
    dataset_sha256: datasetSha,
    dataset_json: datasetJson,
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
    const { raw, bundle, sha } = await makeBundle();
    expect(raw.cuts[0]?.dataset_json).toContain('"value": 1.0');
    expect(raw.cuts[0]?.dataset_json.indexOf('"10": "diez"')).toBeLessThan(raw.cuts[0]?.dataset_json.indexOf('"2": "dos"'));
    await expect(validateBundle(raw, sha)).resolves.toHaveProperty("cuts.length", 2);
    expect(bundle.cuts[0]?.dataset_json).toBe(raw.cuts[0]?.dataset_json);
    expect(bundle.cuts[0]?.dataset.questions[0]?.expected).toEqual({ "10": "diez", "2": "dos", value: 1 });
    const duplicate = structuredClone(raw);
    duplicate.cuts[1].cut_id = duplicate.cuts[0].cut_id;
    await expect(validateBundle(duplicate, sha)).rejects.toThrow("identificador inválido o repetido");
    const wrongHash = structuredClone(raw);
    wrongHash.cuts[0].dataset_sha256 = "f".repeat(64);
    await expect(validateBundle(wrongHash, sha)).rejects.toThrow("conjunto cambió o su hash no coincide");
    const changedWhitespace = structuredClone(raw);
    changedWhitespace.cuts[0].dataset_json += " ";
    await expect(validateBundle(changedWhitespace, sha)).rejects.toThrow("conjunto cambió o su hash no coincide");
    const noDisposition = structuredClone(raw);
    noDisposition.cuts[0].slot_dispositions = [];
    await expect(validateBundle(noDisposition, sha)).rejects.toThrow("cada espacio sin respuesta debe tener un estado explícito");
  });

  it("exports and imports every cut with independent grades and exact bundle binding", async () => {
    const { bundle } = await makeBundle();
    const bundleHash = "b".repeat(64);
    const first: RatingMap = new Map([[
      "Q01:D", { question_id: "Q01", alias: "D", status: "problem", notes: "Revisar cita" },
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
