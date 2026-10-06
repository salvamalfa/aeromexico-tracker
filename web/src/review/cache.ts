import { bundleStorageKey } from "./storage";
import { type RatingMap, type ReviewBundle, type ReviewCut } from "./types";
import { parseRatings, ratingsFile } from "./validation";

export function mergeEditedRatings(
  stored: RatingMap,
  current: RatingMap,
  modifiedKeys: Set<string>,
): RatingMap {
  const merged = new Map(stored);
  for (const key of modifiedKeys) {
    const currentRating = current.get(key);
    if (currentRating) merged.set(key, currentRating);
    else merged.delete(key);
  }
  return merged;
}

export function persistBundleRatings(
  bundle: ReviewBundle,
  bundleHash: string,
  ratingsByCut: Map<string, RatingMap>,
  storage: Storage,
): void {
  for (const cut of bundle.cuts) {
    const values = ratingsByCut.get(cut.cut_id) ?? new Map();
    storage.setItem(bundleStorageKey(bundleHash, cut.cut_id, cut.dataset_sha256),
      JSON.stringify(ratingsFile(cut.dataset, cut.dataset_sha256, values)));
  }
}

export function loadCutRatings(cut: ReviewCut, bundleHash: string, storage: Storage): RatingMap {
  const raw = storage.getItem(bundleStorageKey(bundleHash, cut.cut_id, cut.dataset_sha256));
  if (!raw) return new Map();
  try {
    return parseRatings(JSON.parse(raw) as unknown, cut.dataset, cut.dataset_sha256);
  } catch {
    throw new Error("El guardado local está dañado; no se modificó.");
  }
}

export function loadMissingBundleRatings(
  bundle: ReviewBundle,
  bundleHash: string,
  current: Map<string, RatingMap>,
  alreadyLoaded: Set<string>,
  modifiedByCut: Map<string, Set<string>>,
  storage: Storage,
): { ratingsByCut: Map<string, RatingMap>; loadedCuts: Set<string> } {
  const ratingsByCut = new Map(current);
  const loadedCuts = new Set(alreadyLoaded);
  for (const cut of bundle.cuts) {
    if (loadedCuts.has(cut.cut_id)) continue;
    const stored = loadCutRatings(cut, bundleHash, storage);
    const edits = modifiedByCut.get(cut.cut_id) ?? new Set<string>();
    ratingsByCut.set(cut.cut_id, mergeEditedRatings(stored, ratingsByCut.get(cut.cut_id) ?? new Map(), edits));
    loadedCuts.add(cut.cut_id);
  }
  return { ratingsByCut, loadedCuts };
}
