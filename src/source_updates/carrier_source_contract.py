"""Source observation contracts; never harmonize booked and transported passengers."""

from __future__ import annotations

import json
import re
from decimal import Decimal

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

from src.source_updates.catalog import ROOT
from src.transform.stage9_lineage import make_record_id

CONTRACT = ROOT / "contracts/source_updates/carrier-source-observation.json"
GRAIN = ["product", "edition", "source_hash", "source_locator"]
TABLES = {"volaris_sec": "fact_volaris_sec_source", "afac_carriers": "fact_afac_carrier_source"}
NATIVE = {p: p + "_source_native" for p in TABLES}
FIELDS = (
    "product edition entity_as_reported carrier_key statement period_type period_id "
    "period_start_date period_end_date metric_key segment service_type value unit scale "
    "source_value source_label source_locator source_excerpt source_table source_row_number "
    "source_column source_system source_file source_hash ingested_at parser_version "
    "is_preliminary is_unaudited source_estimated source_notes aviation_scope mapping_evidence "
    "source_group agent_eligible"
).split()


def amount(token):
    """A dash stays unknown, including when an identity could imply zero."""
    if token == "-":
        return None
    if isinstance(token, str) and (token.startswith("(") != token.endswith(")") or token.startswith("(-")):
        raise ValueError("Unbalanced or double-negative source number")
    if not isinstance(token, str) or not re.fullmatch(r"\(?-?\d[\d,]*(?:\.\d+)?(?:%|x)?\)?", token):
        raise ValueError("Unreviewed source numeric token")
    if not re.fullmatch(r"\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:%|x)?\)?", token):
        raise ValueError("Malformed source thousands separator")
    d = Decimal(token.strip("()%x").replace(",", ""))
    if token.startswith("("):
        d = -d
    if not d.is_finite() or abs(d) > 2**53 - 1:
        raise ValueError("Nonfinite or unsafe source number")
    return d


def record(
    product,
    original,
    *,
    edition,
    entity,
    statement,
    kind,
    period_id,
    start,
    end,
    metric,
    segment,
    service,
    token,
    unit,
    scale,
    label,
    locator,
    excerpt,
    table,
    row,
    column,
    notes,
    aviation,
    carrier=None,
    mapping=None,
    preliminary=None,
    unaudited=None,
    estimated=None,
    group=None,
):
    value = amount(token)
    return dict(
        zip(
            FIELDS,
            [
                product,
                edition,
                entity,
                carrier,
                statement,
                kind,
                period_id,
                start,
                end,
                metric,
                segment,
                service,
                None if value is None else float(value),
                unit,
                float(scale),
                token,
                label,
                locator,
                excerpt,
                table,
                row,
                column,
                original["source_system"],
                original["source_file"],
                original["sha256"],
                original["downloaded_at"],
                "carrier_source_v1",
                preliminary,
                unaudited,
                estimated,
                notes,
                aviation,
                mapping,
                group,
                False,
            ],
            strict=True,
        )
    )


def identifier(row, *, gold=False):
    table = TABLES[row["product"]] if gold else NATIVE[row["product"]]
    return make_record_id(table, {k: row[k] for k in GRAIN})


def clean(row):
    return {k: None if not isinstance(v, (list, dict)) and pd.isna(v) else v for k, v in row.items()}


def validate(frame, product, *, gold=False):
    if product not in TABLES or frame.empty or len(frame) > 30_000:
        raise ValueError("Bounded nonempty carrier source product required")
    schema = json.loads(CONTRACT.read_text())["gold" if gold else "native"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    seen = set()
    for raw in frame.to_dict("records"):
        r = clean(raw)
        validator.validate(r)
        if r["product"] != product or r["record_id"] != identifier(r, gold=gold):
            raise ValueError("Source product or record identity mismatch")
        if r["record_id"] in seen:
            raise ValueError("Duplicate carrier source observation")
        seen.add(r["record_id"])
        if pd.Timestamp(r["ingested_at"]).tzinfo is None:
            raise ValueError("Source capture needs an explicit timezone")
        if r["period_type"] == "instant":
            if r["period_start_date"] is not None:
                raise ValueError("An instant cannot acquire a duration start")
        elif r["period_start_date"] is None or r["period_start_date"] > r["period_end_date"]:
            raise ValueError("Source duration dates are inconsistent")
        if not gold:
            value = amount(r["source_value"])
            if (value is None) != (r["value"] is None) or value is not None and float(value) != r["value"]:
                raise ValueError("Native source token/value differ")
        else:
            raw_value = amount(r["source_value"])
            expected_unit = "fraction" if r["source_unit"] == "percent" else r["source_unit"]
            if (
                raw_value is None
                or r["value"] != float(raw_value * Decimal(str(r["scale"])))
                or r["unit"] != expected_unit
            ):
                raise ValueError("Gold numeric value/unit differ from explicit reported scale")
            from src.source_updates.carrier_source_gold import MODULES

            native_semantics = {k: r[k] for k in FIELDS}
            native_semantics.update(unit=r["source_unit"], value=float(raw_value))
            MODULES[product].validate_row(native_semantics)
            if product == "afac_carriers" and (
                r["period_id"] != r["edition"]
                or r["statement"] not in {"pdf_operator", "database_row"}
                or r["statement"] == "database_row"
                and r["service_type"] != "charter"
            ):
                raise ValueError("AFAC Gold is the current operator month, not totals or historical DB")
            parents = json.loads(r["native_parent_record_ids"])
            if (
                not isinstance(parents, list)
                or not parents
                or len(parents) != len(set(parents))
                or any(not isinstance(p, str) or not re.fullmatch(r"rec_[a-f0-9]{64}", p) for p in parents)
            ):
                raise ValueError("Gold needs exact unique native parents")
    return frame
