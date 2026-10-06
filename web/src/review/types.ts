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

export type CutDisposition = "terminal" | "complete" | "partial";
export type MissingSlotDisposition = "no_answer" | "failed" | "held" | "not_attempted";

export interface SlotDisposition {
  question_id: string;
  alias: CandidateAlias;
  status: MissingSlotDisposition;
}

export interface ReviewCut {
  cut_id: string;
  version: string;
  label: string;
  disposition: CutDisposition;
  source_sha256: string;
  dataset_sha256: string;
  dataset_json: string;
  dataset: ReviewDataset;
  slot_dispositions: SlotDisposition[];
}

export interface ReviewBundle {
  schema_version: 1;
  bundle_id: string;
  bundle_version: string;
  title: string;
  cuts: ReviewCut[];
}

export interface BundleRatingsCut {
  cut_id: string;
  version: string;
  dataset_id: string;
  dataset_sha256: string;
  ratings: Rating[];
}

export interface BundleRatingsFile {
  schema_version: 2;
  bundle_id: string;
  bundle_version: string;
  bundle_content_sha256: string;
  cuts: BundleRatingsCut[];
}

export type RatingMap = Map<string, Rating>;

export function ratingKey(questionId: string, alias: CandidateAlias): string {
  return `${questionId}:${alias}`;
}
