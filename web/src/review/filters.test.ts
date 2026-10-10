import { describe, expect, it } from "vitest";
import { questionProgress, visibleQuestionIndices } from "./filters";
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

  it("counts and filters all four candidates, including alias D", () => {
    const source: ReviewDataset = {
      schema_version: 1, dataset_id: "b".repeat(64), available_count: 4,
      questions: [{
        id: "Q01", question: "Pregunta", language: "es", expected: null,
        candidates: ["A", "B", "C", "D"].map((alias) => ({ alias: alias as "A" | "B" | "C" | "D", answer: alias })),
      }],
    };
    const ratings: RatingMap = new Map([[
      ratingKey("Q01", "D"), { question_id: "Q01", alias: "D", status: "problem", notes: "" },
    ]]);
    expect(questionProgress(source, 0, ratings)).toEqual({ available: 4, reviewed: 1, hasProblem: true });
    expect(visibleQuestionIndices(source, ratings, "pending")).toEqual([0]);
    expect(visibleQuestionIndices(source, ratings, "problems")).toEqual([0]);
  });
});
