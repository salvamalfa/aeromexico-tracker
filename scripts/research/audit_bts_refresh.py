"""Offline audit of retained and refreshed official BTS ZIPs; never fits data."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd

TARGETS = {19534: "AEROMEXICO", 20250: "AEROMEXICO_CONNECT", 21342: "VIVA_AEROBUS", 21351: "VOLARIS"}
GRAIN = [
    "AIRLINE_ID",
    "UNIQUE_CARRIER",
    "ORIGIN",
    "DEST",
    "ORIGIN_COUNTRY",
    "DEST_COUNTRY",
    "YEAR",
    "MONTH",
    "CLASS",
]


def read_zip(path):
    content = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        csvs = [n for n in archive.namelist() if n.endswith(".csv") and "documentation" not in n.lower()]
        assert len(csvs) == 1
        raw = archive.read(csvs[0])
    frame = pd.read_csv(io.BytesIO(raw))
    return frame, raw, hashlib.sha256(content).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True, type=Path)
    parser.add_argument("--new", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {
        "official_release_url": "https://www.transtats.bts.gov/releaseinfo.asp",
        "metric": "DEPARTURES_PERFORMED",
        "regular_classes": ["F", "G"],
        "frames": {},
    }
    route_frames = {}
    for label, path in [("old", args.old), ("new", args.new)]:
        frame, raw, digest = read_zip(path)
        (args.out / f"{label}_T_T100I_SEGMENT_ALL_CARRIER.csv").write_bytes(raw)
        target = frame[frame.AIRLINE_ID.isin(TARGETS)].copy()
        target["carrier_key"] = target.AIRLINE_ID.map(TARGETS)
        offscope = target[
            ~(
                ((target.ORIGIN_COUNTRY == "MX") & (target.DEST_COUNTRY == "US"))
                | ((target.ORIGIN_COUNTRY == "US") & (target.DEST_COUNTRY == "MX"))
            )
        ]
        assert offscope.empty
        grouped = frame.groupby(GRAIN, dropna=False, as_index=False).agg(
            performed=("DEPARTURES_PERFORMED", "sum"), aircraft_rows=("DEPARTURES_PERFORMED", "size")
        )
        route_frames[label] = grouped
        grouped[grouped.AIRLINE_ID.isin(TARGETS)].sort_values(GRAIN).to_csv(
            args.out / f"{label}_route_direction_month_class.csv", index=False
        )
        monthly = target.groupby(
            ["AIRLINE_ID", "UNIQUE_CARRIER", "carrier_key", "MONTH", "CLASS"], as_index=False
        ).agg(performed=("DEPARTURES_PERFORMED", "sum"), rows=("DEPARTURES_PERFORMED", "size"))
        monthly.to_csv(args.out / f"{label}_target_carrier_month_class.csv", index=False)
        direction = target.groupby(
            ["AIRLINE_ID", "UNIQUE_CARRIER", "MONTH", "CLASS", "ORIGIN_COUNTRY", "DEST_COUNTRY"],
            as_index=False,
        ).DEPARTURES_PERFORMED.sum()
        direction.to_csv(args.out / f"{label}_direction_month_class.csv", index=False)
        q2 = (
            target[target.MONTH.isin([4, 5, 6])]
            .groupby(["AIRLINE_ID", "UNIQUE_CARRIER", "carrier_key", "CLASS"], as_index=False)
            .agg(performed=("DEPARTURES_PERFORMED", "sum"), rows=("DEPARTURES_PERFORMED", "size"))
        )
        q2.to_csv(args.out / f"{label}_q2_carrier_class.csv", index=False)
        summary["frames"][label] = {
            "zip": str(path),
            "sha256": digest,
            "zip_bytes": path.stat().st_size,
            "csv_sha256": hashlib.sha256(raw).hexdigest(),
            "csv_headers": list(frame.columns),
            "all_rows": len(frame),
            "months": sorted(frame.MONTH.unique().tolist()),
            "q2": q2.to_dict("records"),
        }
    delta = route_frames["old"].merge(
        route_frames["new"], on=GRAIN, how="outer", suffixes=("_old", "_new"), indicator=True
    )
    delta["performed_delta"] = delta.performed_new - delta.performed_old
    delta.sort_values(GRAIN).to_csv(args.out / "all_route_direction_month_class_comparison.csv", index=False)
    target_delta = delta[delta.AIRLINE_ID.isin(TARGETS)]
    target_delta.to_csv(args.out / "target_route_direction_month_class_comparison.csv", index=False)
    restatements = delta[(delta.MONTH <= 5) & ((delta._merge != "both") | (delta.performed_delta != 0))]
    restatements.to_csv(args.out / "common_month_restatements.csv", index=False)
    target_restatements = restatements[restatements.AIRLINE_ID.isin(TARGETS)]
    summary["restatements_through_may"] = {
        "all_changed_cells": len(restatements),
        "target_changed_cells": len(target_restatements),
        "april_may_target_changed_cells": len(target_restatements[target_restatements.MONTH.isin([4, 5])]),
    }
    summary["limits"] = [
        "F/G are regular; L/P remain separately classified.",
        "Missing month/cell is not a reported zero; comparison leaves absent values null.",
        "Direction counts can be asymmetric; retain reported directions and do not fabricate return flights.",
        "Connect is an independently reported operator; group aggregation must be explicit.",
        "BTS covers Mexico-US, not the worldwide international network.",
    ]
    (args.out / "bts-refresh-audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["restatements_through_may"]))


if __name__ == "__main__":
    main()
