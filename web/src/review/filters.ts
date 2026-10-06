import { type RatingMap, type ReviewDataset, ratingKey } from "./types";

export type QuestionFilter = "all" | "pending" | "reviewed" | "problems";

export function questionProgress(dataset: ReviewDataset, index: number, ratings: RatingMap): {
  available: number;
  reviewed: number;
  hasProblem: boolean;
} {
  const question = dataset.questions[index];
  if (!question) return { available: 0, reviewed: 0, hasProblem: false };
  const availableCandidates = question.candidates.filter((candidate) => candidate.answer !== null);
  const reviewed = availableCandidates.filter((candidate) => ratings.has(ratingKey(question.id, candidate.alias)));
  return {
    available: availableCandidates.length,
    reviewed: reviewed.length,
    hasProblem: reviewed.some((candidate) => ratings.get(ratingKey(question.id, candidate.alias))?.status === "problem"),
  };
}

export function visibleQuestionIndices(
  dataset: ReviewDataset,
  ratings: RatingMap,
  filter: QuestionFilter,
): number[] {
  return dataset.questions.flatMap((question, index) => {
    const progress = questionProgress(dataset, index, ratings);
    const matches = filter === "all"
      || (filter === "pending" && progress.available > 0 && progress.reviewed < progress.available)
      || (filter === "reviewed" && progress.available > 0 && progress.reviewed === progress.available)
      || (filter === "problems" && progress.hasProblem);
    return matches ? [index] : [];
  });
}
