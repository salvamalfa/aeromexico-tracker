"""Replay AFAC's retained database into existing passenger charts only.

Never mutates Gold or warehouse. Missing services are not zero-filled; all
reported Mexican charter operators, including unmapped names, remain in totals.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator

from src.dashboard.market import _month_label, _segment_block
from src.pipeline.offline import block_network
from src.source_updates import readiness
from src.source_updates.catalog import ROOT
from src.source_updates.closed_editions import accepted
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.writer import dumps_deterministic

PRODUCTS = frozenset({"afac_carriers"})
TARGETS = ("data/v1/flights/quarters.json", "data/v1/market.json")
CONTRACTS = ("flights.schema.json", "market.schema.json")
MEMBERS = {"AEROMEXICO", "AEROMEXICO_CONNECT", "VIVA_AEROBUS", "VOLARIS"}
UNIVERSE = "afac_reported_mexican_all_services_v1"
SCOPE = "reported_Mexican_carrier_passengers_scheduled_and_charter_not_foreign_or_route_estimates"
NOTE = (
    "Ediciones AFAC retenidas: los puntos nuevos suman servicio regular y fletamento "
    "de las empresas mexicanas reportadas, incluidos nombres de chárter sin mapeo. "
    "El grupo Aeroméxico es una suma calculada de Aerovías y Connect, separados en la fuente. "
    "Son cifras preliminares; la advertencia internacional del boletín permanece en "
    "la evidencia. No certifican la totalidad observacional ni generan un trimestre incompleto. "
    "Los puntos históricos publicados no se recalculan. La cobertura del denominador nuevo "
    "incluye fletamento mexicano sin mapeo que podía faltar en el histórico; no atribuir "
    "la diferencia de cobertura a un cambio del negocio."
)


def _read(candidate, name, checked):
    path = candidate / "data" / (name + ".parquet")
    if path.is_symlink() or not path.is_file():
        raise ValueError("AFAC bridge requires its regular, replayed native file")
    if hashlib.sha256(path.read_bytes()).hexdigest() != checked["output_sha256"].get(name):
        raise ValueError("AFAC native bytes changed after replay")
    return pd.read_parquet(path)


def _number(series):
    if series.isna().any() or any(not float(x).is_integer() or x < 0 for x in series):
        raise ValueError("AFAC passenger observations must be nonnegative reported integers")
    return float(series.sum())


def monthly_values(native, period):
    """Literal DB universe; subtotal labels never identify operator observations."""
    rows = native[
        native.statement.eq("database_row")
        & native.period_id.eq(period)
        & native.period_type.eq("month")
        & native.source_group.eq("Mexicana")
    ].copy()
    if rows.empty or not rows.metric_key.eq("passengers_transported").all():
        raise ValueError("No reported Mexican monthly passenger universe")
    if not rows.unit.eq("passengers_transported").all() or not rows.scale.eq(1).all():
        raise ValueError("AFAC native units or scale changed")
    if set(rows.segment) != {"domestic", "international"} or set(rows.service_type) != {
        "scheduled",
        "charter",
    }:
        raise ValueError("Both observed markets and service types are required")
    grain = ["entity_as_reported", "segment", "service_type"]
    if rows.duplicated(grain).any():
        raise ValueError("Duplicate AFAC operator/market/service observation")
    if rows.entity_as_reported.str.match(r"(?i)^total(?:\s|$)").any():
        raise ValueError("A subtotal cannot enter the operator denominator")
    for segment in ("domestic", "international"):
        for carrier in MEMBERS:
            block = rows[rows.segment.eq(segment) & rows.carrier_key.eq(carrier)]
            if set(block.service_type) != {"scheduled", "charter"} or len(block) != 2:
                raise ValueError("A target operator needs both literal service cells; absence is not zero")
    result, operators = {}, {}
    for segment, part in rows.groupby("segment", sort=True):
        denominator = _number(part.value)
        values = {}
        for name, group in part.groupby("entity_as_reported", sort=True):
            keys = set(group.carrier_key.dropna())
            if len(keys) > 1:
                raise ValueError("One AFAC reported operator has conflicting identity")
            key = next(iter(keys), "UNMAPPED:" + name)
            values[key] = _number(group.value)
        values["AEROMEXICO"] += values.pop("AEROMEXICO_CONNECT")
        result[segment] = {"values": values, "denominator": denominator}
        operators[segment] = sorted(part.loc[part.carrier_key.isna(), "entity_as_reported"].unique())
    keys = set(result["domestic"]["values"]) | set(result["international"]["values"])
    total = {}
    for key in keys:
        # Only sum a member whose two market observations really exist.
        if key in result["domestic"]["values"] and key in result["international"]["values"]:
            total[key] = result["domestic"]["values"][key] + result["international"]["values"][key]
    result["total"] = {"values": total, "denominator": sum(x["denominator"] for x in result.values())}
    return result, operators


def _check_current_gold(native, gold, period):
    selected = native[native.statement.eq("database_row") & native.period_id.eq(period)]
    for row in gold.itertuples(index=False):
        if row.statement == "pdf_operator":
            matched = selected[
                selected.entity_as_reported.eq(row.entity_as_reported)
                & selected.segment.eq(row.segment)
                & selected.service_type.eq("scheduled")
            ]
            if matched.empty and row.value == 0:
                continue  # Explicit, already certified PDF zero; never add a DB zero.
        else:
            matched = selected[
                selected.entity_as_reported.eq(row.entity_as_reported)
                & selected.segment.eq(row.segment)
                & selected.service_type.eq(row.service_type)
            ]
        if len(matched) != 1 or float(matched.value.iloc[0]) != row.value:
            raise ValueError("AFAC Gold month does not agree with its verified database support")


def project(native, gold, period, before, source):
    q, market = (json.loads(before[path]) for path in TARGETS)
    old_records, old_months = q["monthly_passengers"]["records"], market["months"]
    end = old_records[-1]["period_id"]
    editions = market["metadata"].get("source_editions", [])
    own = [
        row
        for row in editions
        if row["edition"] == period and row["database_sha256"] == source["database_sha256"]
    ]
    if len(own) > 1:
        raise ValueError("Duplicate AFAC source-edition identity")
    if end != old_months[-1]["period_id"] or end > period or end == period and not own:
        raise ValueError("AFAC baseline month needs reconciliation or is already current")
    if own:
        end = own[0]["previous_period"]
    if not re.fullmatch(r"2026M(?:0[1-9]|1[0-2])", period):
        raise ValueError("AFAC bridge currently admits the verified 2026 database format")
    _check_current_gold(native, gold, period)
    overlap, _ = monthly_values(native, end)
    prior_record = next(row for row in old_records if row["period_id"] == end)
    prior_market = next(row for row in old_months if row["period_id"] == end)
    for segment in ("domestic", "international"):
        if overlap[segment]["values"]["AEROMEXICO"] != prior_record[segment]:
            raise ValueError(
                "New AFAC edition revises the historical boundary; explicit revision review required"
            )
        for carrier, entry in prior_market["segments"][segment]["carriers"].items():
            if overlap[segment]["values"].get(carrier) != entry["passengers"]:
                raise ValueError("AFAC member values differ from the existing market universe")
    periods = [
        str(x).replace("-", "M")
        for x in pd.period_range(end.replace("M", "-"), period.replace("M", "-"), freq="M")
    ][1:]
    records, months, unmapped = [], [], {}
    for month in periods:
        values, unknown = monthly_values(native, month)
        domestic = values["domestic"]["values"]["AEROMEXICO"]
        international = values["international"]["values"]["AEROMEXICO"]
        records.append(
            {
                "period_id": month,
                "date": month.replace("M", "-") + "-01",
                "period_type": "month",
                "domestic": domestic,
                "international": international,
                "total_segment_sum": domestic + international,
                "reported_total": domestic + international,
                "reconciliation_delta": 0.0,
                "source_id": "afac-retained-database-" + period,
                "source_hash": source["database_sha256"],
                "cutoff_date": None,
                "agent_eligible": False,
                "availability": "reported_operator_cells_group_sum",
            }
        )
        months.append(
            {
                "period_id": month,
                "period_label": _month_label(month),
                "segments": {
                    segment: _segment_block(part["values"], part["denominator"])
                    for segment, part in values.items()
                },
            }
        )
        unmapped[month] = unknown
    return {
        "product": "afac_carriers",
        "edition": period,
        "previous_period": end,
        "periods": periods,
        "records": records,
        "months": months,
        "unmapped_operators": unmapped,
        "source": source,
        "quality_note": NOTE,
    }


def _validate(payload, filename, definition=None):
    schema = json.loads((ROOT / "contracts/web" / filename).read_bytes())
    if definition:
        from src.web_export.schemas import split_flight_schemas

        schema = split_flight_schemas(schema)[0]
    Draft202012Validator(schema).validate(payload)
    check_privacy(payload, load_privacy_rules())


def public_outputs(before, projection):
    if (
        set(before) != set(TARGETS)
        or projection["product"] != "afac_carriers"
        or projection["quality_note"] != NOTE
    ):
        raise ValueError("AFAC bridge has a fixed two-payload scope")
    q, market = (json.loads(before[path]) for path in TARGETS)
    result, revised = copy.deepcopy(q), copy.deepcopy(market)
    series = result["monthly_passengers"]
    last = series["records"][-1]["period_id"]
    periods = projection["periods"]
    if not periods or periods != sorted(set(periods)):
        raise ValueError("AFAC monthly append cannot replace existing historical points")
    if periods != [row["period_id"] for row in projection["records"]] or periods != [
        row["period_id"] for row in projection["months"]
    ]:
        raise ValueError("AFAC projected period identities differ")
    if all(p <= last for p in periods):
        for name, existing, proposed in (
            ("AM", series["records"], projection["records"]),
            ("market", market["months"], projection["months"]),
        ):
            by_period = {row["period_id"]: row for row in existing}
            if any(by_period.get(row["period_id"]) != row for row in proposed):
                raise ValueError(f"AFAC {name} retry differs from its published source version")
        return dict(before)
    if any(p <= last for p in periods):
        raise ValueError("Do not mix AFAC historical replacement with a monthly append")
    series["records"].extend(copy.deepcopy(projection["records"]))
    series.update(
        period_end=str(pd.Period(periods[-1].replace("M", "-"), freq="M").end_time.date()),
        source_id="afac-historical-and-retained-editions",
        observed_months=len(series["records"]),
        calendar_months=len(
            pd.period_range(
                series["records"][0]["period_id"].replace("M", "-"), periods[-1].replace("M", "-"), freq="M"
            )
        ),
        as_of=projection["source"]["captured_at"],
        agent_eligible=False,
        eligibility_reason=NOTE,
    )
    if series["observed_months"] != series["calendar_months"]:
        raise ValueError("Do not silently bridge a missing AFAC month")
    revised["months"].extend(copy.deepcopy(projection["months"]))
    revised["metadata"]["last_period"] = periods[-1]
    revised["metadata"]["data_as_of"] = projection["source"]["captured_at"][:10]
    if NOTE not in revised["metadata"]["method_note"]:
        revised["metadata"]["method_note"] += " " + NOTE
    editions = revised["metadata"].setdefault("source_editions", [])
    if not any(row["universe_version"] == UNIVERSE for row in editions):
        revised["metadata"].setdefault("method_breaks", []).append(periods[0])
    edition = {
        **projection["source"],
        "edition": projection["edition"],
        "previous_period": projection["previous_period"],
        "published_months": periods,
        "universe_version": UNIVERSE,
        "unmapped_operators": projection["unmapped_operators"],
    }
    editions.append(edition)
    # No September means no Q3: all existing quarter metrics remain byte-identical.
    _validate(result, "flights.schema.json", "quarters")
    _validate(revised, "market.schema.json")
    return {
        TARGETS[0]: (dumps_deterministic(result) + "\n").encode(),
        TARGETS[1]: (dumps_deterministic(revised) + "\n").encode(),
    }


def replay(profile, baseline):
    if (
        set(profile) != {"schema_version", "item", "as_of"}
        or profile["schema_version"] != "afac_carrier_chart_source_v1"
    ):
        raise ValueError("Unsupported AFAC chart source profile")
    item = profile["item"]
    if item["product"] != "afac_carriers" or item["adapter"] != "carrier_source":
        raise ValueError("AFAC needs its dedicated verified native dossier")
    allowed = {
        "id",
        "product",
        "period",
        "adapter",
        "workspace",
        "receipt_id",
        "required",
        "candidate_as_of",
        "availability",
        "source_period",
        "cadence",
        "used",
        "depends_on",
    }
    if (
        set(item) - allowed
        or item.get("cadence", "monthly") != "monthly"
        or item.get("used", True) is not True
        or item.get("depends_on", []) != []
        or item.get("required", True) is not True
    ):
        raise ValueError("AFAC monthly source requirements must remain explicit")
    native_period = item.get("source_period", item["period"])
    if (
        not all(
            isinstance(value, str) and re.fullmatch(r"2026M(?:0[1-9]|1[0-2])", value)
            for value in (native_period, item["period"])
        )
        or native_period > item["period"]
    ):
        raise ValueError("An AFAC native month cannot be later than its review task")
    native_item = {
        key: value
        for key, value in item.items()
        if key not in {"source_period", "cadence", "used", "depends_on"}
    }
    native_item.update(period=native_period, required=True)
    recipe = {"version": 1, "as_of": profile["as_of"], "required_items": [item["id"]], "items": [native_item]}
    with block_network():
        selected = readiness.preflight(recipe, ROOT / "tmp/source-updates/afac-chart-check")[0]
        checked = readiness.check_task(selected, item["candidate_as_of"], profile["as_of"])
        if not accepted(selected, checked):
            raise ValueError("AFAC source availability needs its historical physical acceptance")
        candidate = Path(selected["workspace"])
        native = _read(candidate, "silver/afac_carriers_source_native", checked)
        gold = _read(candidate, "gold/fact_afac_carrier_source", checked)
        artifacts = _read(candidate, "gold/dim_source_artifact", checked)
        database = artifacts[artifacts.source_file.str.endswith(".zip")]
        pdf = artifacts[artifacts.source_file.str.endswith(".pdf")]
        if len(database) != 1 or len(pdf) != 1:
            raise ValueError("AFAC projection needs the exact paired PDF and database")
        original = candidate / "data/bronze" / str(database.source_file.iloc[0])
        metadata = json.loads(original.with_suffix(original.suffix + ".meta.json").read_bytes())
        source = {
            "database_sha256": str(database.artifact_sha256.iloc[0]),
            "pdf_sha256": str(pdf.artifact_sha256.iloc[0]),
            "source_url": str(database.source_url.iloc[0]),
            "captured_at": metadata["downloaded_at"],
            "scope": SCOPE,
        }
        before = {name: (baseline / name).read_bytes() for name in TARGETS}
        projection = project(native, gold, native_period, before, source)
        files = []
        for directory in [candidate, Path(item["availability"]["workspace"])]:
            if directory.resolve() != directory or not directory.is_dir():
                raise ValueError("AFAC input roots must be physical directories")
            for path in directory.rglob("*"):
                if path.is_symlink():
                    raise ValueError("Symlink in AFAC source closure")
                if path.is_file():
                    files.append(path)
    binding = {key: item[key] for key in ("product", "period", "receipt_id", "candidate_as_of")}
    binding["period"] = native_period
    binding["output_sha256"] = checked["output_sha256"]
    return {"source_binding": binding, "projection": projection, "input_files": sorted(set(files))}
