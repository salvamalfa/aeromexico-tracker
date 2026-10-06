import { describe, expect, it } from "vitest";
import { mergeEditedRatings } from "./cache";
import { ratingKey, type RatingMap } from "./types";

describe("review cache merge", () => {
  it("keeps saved independent grades while applying per-cut replacement and deletion tombstones", () => {
    const saved: RatingMap = new Map([
      [ratingKey("Q01", "A"), { question_id: "Q01", alias: "A", status: "problem", notes: "old" }],
      [ratingKey("Q02", "B"), { question_id: "Q02", alias: "B", status: "correct", notes: "untouched" }],
      [ratingKey("Q03", "C"), { question_id: "Q03", alias: "C", status: "correct", notes: "removed" }],
    ]);
    const edited: RatingMap = new Map([
      [ratingKey("Q01", "A"), { question_id: "Q01", alias: "A", status: "correct", notes: "new" }],
    ]);

    const merged = mergeEditedRatings(saved, edited, new Set([ratingKey("Q01", "A"), ratingKey("Q03", "C")]));

    expect(merged.get(ratingKey("Q01", "A"))).toEqual(edited.get(ratingKey("Q01", "A")));
    expect(merged.get(ratingKey("Q02", "B"))).toEqual(saved.get(ratingKey("Q02", "B")));
    expect(merged.has(ratingKey("Q03", "C"))).toBe(false);
  });
});
