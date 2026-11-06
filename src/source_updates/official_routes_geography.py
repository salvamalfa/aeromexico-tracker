"""Replay the bounded reviewed city extract against the retained free GeoNames dump."""

from __future__ import annotations

import io
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


def verify_cities(cities: Path, raw: Path, raw_hash: str) -> dict:
    meta = json.loads(raw.with_suffix(raw.suffix + ".meta.json").read_bytes())
    if meta["sha256"] != raw_hash or meta["source_url"] != "https://download.geonames.org/export/dump/cities500.zip":
        raise ValueError("City extract requires the exact official GeoNames source")
    columns = ("geonameid name ascii aliases latitude longitude feature_class feature_code country_iso2 cc2 "
               "admin1 admin2 admin3 admin4 population elevation dem timezone modified").split()
    with ZipFile(raw) as archive:
        if archive.namelist() != ["cities500.txt"] or archive.getinfo("cities500.txt").file_size > 150_000_000:
            raise ValueError("GeoNames archive member/size changed")
        native = pd.read_csv(io.BytesIO(archive.read("cities500.txt")), sep="\t", names=columns,
                             dtype=str, keep_default_na=False).set_index("geonameid")
    selected = pd.read_csv(cities, dtype=str, keep_default_na=False)
    for row in selected.to_dict("records"):
        if not row["geonameid"]:  # An explicit unresolved label keeps null coordinates in the map/table.
            if row["latitude"] or row["longitude"] or row["match_method"] != "unresolved":
                raise ValueError("Unresolved city must not invent coordinates")
            continue
        source = native.loc[row["geonameid"]]
        if any(row[k] != source[k] for k in ("country_iso2", "admin1", "latitude", "longitude")) or (
            row["geonames_name"] != source["name"] or row["source_sha256"] != raw_hash
            or row["source_url"] != meta["source_url"] or row["captured_at"] != meta["downloaded_at"]
            or row["license"] != "CC BY 4.0"
        ):
            raise ValueError("Reviewed city location differs from its GeoNames native identity")
    return dict(rows=len(selected), unresolved=int(selected.geonameid.eq("").sum()),
                source_sha256=raw_hash, attribution="GeoNames, CC BY 4.0", source_url=meta["source_url"])
