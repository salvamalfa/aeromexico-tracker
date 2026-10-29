"""Strict source-observation Gold, full native parents and physically verified artifacts."""

from __future__ import annotations

import json

import pandas as pd
from jsonschema import Draft202012Validator

from src.source_updates.catalog import ROOT
from src.source_updates.viva_financial_checks import numeric, reconcile
from src.source_updates.viva_financial_spec import (
    BALANCE,
    CASH,
    DEBT,
    FLEET,
    GRAIN,
    INCOME,
    INDICATORS,
    NATIVE,
    TABLE,
    dossier_period,
    profile,
)
from src.transform.stage6_contracts import validate_table
from src.transform.stage9_lineage import (
    LineageSpec,
    add_record_ids,
    build_bridge_record_lineage,
    build_dim_source_artifact,
)
from src.transform.validate_stage9 import validate_lineage_frames

CONTRACT = ROOT / "contracts/source_updates/viva_financial_source.json"


def validate(frame, *, gold=False, period=None):
    if frame.empty or frame.duplicated(GRAIN).any():
        raise ValueError("Viva complete nonduplicate financial grain required")
    if period is None:
        period = max(set(frame.edition)) if gold else dossier_period(frame.edition)
    if period not in {"2026Q2", "2026Q3"}:
        raise ValueError("Viva supported primary financial period required")
    primary_q = int(period[-1])
    schema = json.loads(CONTRACT.read_text())
    validator = Draft202012Validator(schema["gold" if gold else "native"])
    definitions = dict(
        indicators=INDICATORS, income=INCOME, balance=BALANCE, cash_flow=CASH, debt=DEBT, fleet=FLEET
    )
    from src.source_updates.viva_financials import amount

    expected = set()
    for edition in [period] if gold else [f"2026Q{primary_q - 1}", period]:
        q = int(edition[-1])
        selected = profile(q)
        end = selected["end"]
        for statement, rows in definitions.items():
            kinds = (
                ["instant"]
                if statement in {"balance", "debt", "fleet"}
                else ["quarter", selected["cumulative_kind"]]
                if q in (2, 3)
                else ["quarter"]
            )
            for kind in kinds:
                dates = (
                    [(None, f"2026-{end}"), (None, "2025-12-31")]
                    if kind == "instant"
                    else [
                        (
                            f"{year}-{selected['quarter_start'] if kind == 'quarter' else '01-01'}",
                            f"{year}-{end}",
                        )
                        for year in (2026, 2025)
                    ]
                )
                if statement == "fleet":
                    dates = selected["fleet_dates"]
                for start, stop in dates:
                    expected.update(
                        (edition, statement, kind, start, stop, item[1], item[4])
                        for item in rows
                        if not gold or item[4] != "context_not_gold"
                    )
    if set(frame[GRAIN].itertuples(index=False, name=None)) != expected:
        raise ValueError("Viva financial complete edition/statement/period/metric domain changed")
    for row in frame.to_dict("records"):
        clean = {
            k: (v.isoformat() if isinstance(v, pd.Timestamp) else None if pd.isna(v) else v)
            for k, v in row.items()
        }
        validator.validate(clean)
        r = pd.Series(row)
        known = {(item[1], item[4]): item for item in definitions[r.statement]}
        definition = known.get((r.metric_key, r.segment))
        if definition is None or (r.unit, r.scale) != (definition[2], float(definition[3])):
            raise ValueError("Viva declared metric/segment/unit/scale differs from reviewed table semantics")
        raw = amount(r.source_value)
        if (r.unit == "fraction") != r.source_value.endswith("%") or (
            r.unit == "times_ltm"
        ) != r.source_value.endswith("x"):
            raise ValueError("Viva value token and explicit unit differ")
        financial = r.statement in {"income", "balance", "cash_flow"}
        if r.is_unaudited != (True if financial else None) or r.is_preliminary != (
            True if financial and r.period_end_date.startswith("2026") else None
        ):
            raise ValueError("Viva preliminary/unaudited flags differ from reported evidence")
        if r.report_date != profile(int(r.edition[-1]))["report_date"]:
            raise ValueError("Viva printed report date differs from edition")
        captured = pd.Timestamp(r.ingested_at)
        if captured.tzinfo is None or captured.date().isoformat() < r.report_date:
            raise ValueError("Viva capture must be zoned and not precede the printed report date")
        expected = numeric(r) if gold else raw
        if r.unit in {"aircraft", "sectors"} and (raw < 0 or raw != raw.to_integral_value()):
            raise ValueError("Viva reported aircraft/sector counts must be nonnegative integers")
        if r.value != float(expected):
            raise ValueError("Viva reported value or explicit unit conversion changed")
        if r.period_type == "instant":
            if r.period_start_date is not None:
                raise ValueError("Viva balance/fleet/debt instants must have no duration start")
        elif r.period_start_date != r.period_end_date[:4] + (
            "-" + profile(int(r.edition[-1]))["quarter_start"] if r.period_type == "quarter" else "-01-01"
        ):
            raise ValueError("Viva duration start is inconsistent with report edition")
        if (r.statement in {"balance", "debt", "fleet"}) != (r.period_type == "instant"):
            raise ValueError("Viva statement and period semantics differ")
        if gold and (r.edition != period or r.segment == "context_not_gold"):
            raise ValueError("Viva support or unverified macro context cannot enter Gold")
    if "record_id" in frame:
        add_record_ids(frame, table_name=TABLE if gold else NATIVE, natural_key_columns=GRAIN)
    return frame


def frames(workspace, product, period, native, details):
    if product != "viva_financials" or period not in {"2026Q2", "2026Q3"}:
        raise ValueError("Viva explicit Q2/Q3 dossier required")
    validate(native, period=period)
    details = reconcile(native)  # Never trust a caller's success flag.
    native = add_record_ids(native.copy(), table_name=NATIVE, natural_key_columns=GRAIN)
    validate(native, period=period)
    facts = (
        native.loc[native.edition.eq(period) & native.segment.ne("context_not_gold")]
        .drop(columns="record_id")
        .copy()
    )
    facts["value"] = [float(numeric(r)) for r in facts.itertuples(index=False)]
    facts["native_parent_record_id"] = native.loc[facts.index, "record_id"]
    facts["normalization"] = "reported_value_times_explicit_scale_no_currency_or_distance_conversion"
    facts = add_record_ids(facts, table_name=TABLE, natural_key_columns=GRAIN)
    validate(facts, gold=True, period=period)
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    by_file = artifacts.set_index("source_file").artifact_id.to_dict()
    hashes = artifacts.set_index("source_file").artifact_sha256.to_dict()
    if any(hashes.get(r.source_file) != r.source_hash for r in native.itertuples(index=False)):
        raise ValueError("Viva row hash does not match its selected physical artifact")
    specs = [
        LineageSpec(
            record_id=r.record_id,
            table_name=NATIVE,
            lineage_type="direct_artifact",
            artifact_ids=(by_file[r.source_file],),
            lineage_note="Retained native Viva reported row; exact edition, table, dates, "
            "printed scale and locator. No publication approval.",
        )
        for r in native.itertuples(index=False)
    ]
    specs += [
        LineageSpec(
            record_id=r.record_id,
            table_name=TABLE,
            lineage_type="derived",
            artifact_ids=(by_file[r.source_file],),
            parent_record_ids=(r.native_parent_record_id,),
            lineage_note=f"One true Q{period[-1]}-edition native parent; explicit scale only. Booked passengers, "
            "miles, scheduled LF, non-IFRS and preliminary flags preserved; "
            "no imputed Q1 or context FX.",
        )
        for r in facts.itertuples(index=False)
    ]
    bridge = validate_table("bridge_record_lineage", build_bridge_record_lineage(specs, artifacts))
    lineage = validate_lineage_frames(
        tables={NATIVE: native, TABLE: facts},
        artifacts=artifacts,
        bridge=bridge,
        contracts={"tables": {NATIVE: {"grain": GRAIN}, TABLE: {"grain": GRAIN}}},
    )
    if len(artifacts) != 2 or set(native.source_file) != set(artifacts.source_file):
        raise ValueError(
            "Viva native dossier must be supported by exactly the two selected physical editions"
        )
    return {
        "silver/viva_financial_native": native,
        f"gold/{TABLE}": facts.reset_index(drop=True),
        "gold/dim_source_artifact": artifacts,
        "gold/bridge_record_lineage": bridge,
    }, {
        **details,
        "lineage": lineage,
        "gold_rows": len(facts),
        "native_rows": len(native),
        f"support_Q{int(period[-1]) - 1}_rows_not_projected": int(
            native.edition.eq(f"2026Q{int(period[-1]) - 1}").sum()
        ),
        "primary_macro_rows_not_projected": int(
            (native.edition.eq(period) & native.segment.eq("context_not_gold")).sum()
        ),
        "latest_source_availability_verified": False,
    }
