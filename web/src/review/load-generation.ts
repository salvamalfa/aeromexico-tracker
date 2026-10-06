import { type ReviewBundle, type ReviewDataset } from "./types";

export interface RatingImportRequest {
  request: number;
  datasetVersion: number;
  dataset: ReviewDataset;
  bundle: ReviewBundle | null;
  bundleHash: string;
  contentHash: string;
}

export class ReviewLoadGeneration {
  private datasetSelection = 0;
  private datasetVersion = 0;
  private ratingsSelection = 0;

  beginDatasetSelection(): number { return ++this.datasetSelection; }
  isCurrentDatasetSelection(request: number): boolean { return request === this.datasetSelection; }

  commitDatasetSelection(): void {
    this.datasetVersion += 1;
    this.ratingsSelection += 1;
  }

  invalidateRatingsSelection(): void { this.ratingsSelection += 1; }

  beginRatingsSelection(
    dataset: ReviewDataset,
    bundle: ReviewBundle | null,
    bundleHash: string,
    contentHash: string,
  ): RatingImportRequest {
    return {
      request: ++this.ratingsSelection,
      datasetVersion: this.datasetVersion,
      dataset,
      bundle,
      bundleHash,
      contentHash,
    };
  }

  isCurrentRatingsSelection(
    token: RatingImportRequest,
    dataset: ReviewDataset | null,
    bundle: ReviewBundle | null,
    bundleHash: string,
    contentHash: string,
  ): boolean {
    return token.request === this.ratingsSelection
      && token.datasetVersion === this.datasetVersion
      && (token.bundle ? token.bundle === bundle : token.dataset === dataset)
      && token.bundleHash === bundleHash
      && token.contentHash === contentHash;
  }
}
