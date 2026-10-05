import { type RatingMap, type ReviewDataset } from "./types";
import { parseRatings, ratingsFile } from "./validation";

const PREFIX = "airline-tracker-review:v1:";

export function storageKey(datasetId: string, contentHash: string): string {
  return `${PREFIX}${datasetId}:${contentHash}`;
}

export function bundleStorageKey(bundleHash: string, cutId: string, datasetHash: string): string {
  return `${PREFIX}bundle:${bundleHash}:${cutId}:${datasetHash}`;
}

export function loadRatings(dataset: ReviewDataset, contentHash: string, storage: Storage): RatingMap {
  const raw = storage.getItem(storageKey(dataset.dataset_id, contentHash));
  if (!raw) return new Map();
  return parseRatings(JSON.parse(raw) as unknown, dataset, contentHash);
}

export function saveRatings(dataset: ReviewDataset, contentHash: string, ratings: RatingMap, storage: Storage): void {
  const file = ratingsFile(dataset, contentHash, ratings);
  storage.setItem(storageKey(dataset.dataset_id, contentHash), JSON.stringify(file));
}
