export type CandidateAlias = "A" | "B" | "C";
export type RatingStatus = "correct" | "problem" | "not_evaluable";

export interface CandidateAnswer {
  alias: CandidateAlias;
  answer: string | null;
}

export interface ReviewQuestion {
  id: string;
  question: string;
  language: string;
  expected: unknown;
  candidates: CandidateAnswer[];
}

export interface ReviewDataset {
  schema_version: 1;
  dataset_id: string;
  questions: ReviewQuestion[];
  available_count: number;
}

export interface Rating {
  question_id: string;
  alias: CandidateAlias;
  status: RatingStatus;
  notes: string;
}

export interface RatingsFile {
  schema_version: 1;
  dataset_id: string;
  dataset_content_sha256: string;
  ratings: Rating[];
}

export type RatingMap = Map<string, Rating>;

export function ratingKey(questionId: string, alias: CandidateAlias): string {
  return `${questionId}:${alias}`;
}
