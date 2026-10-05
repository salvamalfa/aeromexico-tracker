import { describe, expect, it } from "vitest";
import { visibleQuestionIndices } from "./filters";
import { type RatingMap, type ReviewDataset, ratingKey } from "./types";

function dataset(): ReviewDataset {
  const questions = Array.from({ length: 40 }, (_, index) => ({
    id: `Q${String(index + 1).padStart(2, "0")}`,
    question: `Pregunta ${index + 1}`,
    language: "es",
    expected: null,
    candidates: ["A", "B", "C"].map((alias, candidateIndex) => ({
      alias: alias as "A" | "B" | "C",
      answer: index < 24 || (index === 24 && candidateIndex < 2) ? `Respuesta ${index}-${alias}` : null,
    })),
  }));
  return { schema_version: 1, dataset_id: "a".repeat(64), questions, available_count: 74 };
}

describe("question filters", () => {
  it("keeps global question indices and distinguishes pending, fully reviewed, and problem questions", () => {
    const source = dataset();
    const ratings: RatingMap = new Map();
    for (const alias of ["A", "B", "C"] as const) {
      ratings.set(ratingKey("Q01", alias), { question_id: "Q01", alias, status: "correct", notes: "" });
    }
    ratings.set(ratingKey("Q02", "A"), {
      question_id: "Q02", alias: "A", status: "problem", notes: "Falta detalle.",
    });
    ratings.set(ratingKey("Q02", "B"), {
      question_id: "Q02", alias: "B", status: "not_evaluable", notes: "",
    });

    expect(visibleQuestionIndices(source, ratings, "all")).toHaveLength(40);
    expect(visibleQuestionIndices(source, ratings, "reviewed")).toEqual([0]);
    expect(visibleQuestionIndices(source, ratings, "pending")).toContain(1);
    expect(visibleQuestionIndices(source, ratings, "problems")).toEqual([1]);
    expect(visibleQuestionIndices(source, ratings, "pending")).not.toContain(39);
  });
});
