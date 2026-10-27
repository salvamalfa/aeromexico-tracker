"""Physical observation universes, separate from publication dates or release lag.

The reviewed FIX methodology edition supports determination dates only. Its
noon announcement is not an observation's first-publication timestamp. Three
CSV originals alone intentionally retain the older, uncertified calendar.
"""

import csv
import hashlib
import io
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.ingest.macro.banxico import BANXICO_SERIES, SIE_EXPORT_URL
from src.source_updates.calendar import business_day, local_time
from src.source_updates.catalog import ROOT
from src.source_updates.collection import safe_workspace

METHOD_URL = "https://www.banxico.org.mx/tipcamb/tipCamMIAction.do?idioma=sp"
METHOD_SHA = "f49a330d41270450141c88c98fd4f7b6e5064c99e418a98f92b4c97db1f95071"
HOLIDAYS = ROOT / "config/source_update_holidays.json"
ROLES = {*BANXICO_SERIES, "fix_methodology"}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def methodology(body, row):
    from src.source_updates.series_native import normalized

    if (
        row.get("source_system") != "banxico_sie"
        or row.get("source_url") != METHOD_URL
        or row.get("logical_key") != "banxico_sie|SF43718_methodology|current|html"
        or row.get("http_status") != 200
        or row.get("bytes") != len(body)
        or row.get("sha256") != sha(body)
        or sha(body) != METHOD_SHA
    ):
        raise ValueError("FIX methodology must bind the reviewed physical official HTML edition")
    soup = BeautifulSoup(body.decode("latin1"), "html.parser")
    notes = [n for n in soup.select("td.notasNotas") if n.get_text(" ", strip=True).startswith("2/")]
    headers = [normalized(n.get_text(" ", strip=True)) for n in soup.select("td")]
    if (
        len(notes) != 1
        or "el tipo de cambio fix es determinado por el banco de mexico los dias habiles bancarios"
        not in normalized(notes[0].get_text(" ", strip=True))
        or not {"fix 2/", "publicacion dof 3/", "para pagos 4/"} <= set(headers)
    ):
        raise ValueError("Official note2 must identify FIX determination separately from DOF/payments")
    return "td.notasNotas[note=2/]"


def certify(inputs, period):
    from src.source_updates.series_native import banxico_file, binding, normalized, window

    if set(inputs) != ROLES:
        raise ValueError("Observation-calendar proof requires exactly three series plus FIX methodology")
    start, end, _ = window(period)
    locator = methodology(*inputs["fix_methodology"])
    holidays_body = HOLIDAYS.read_bytes()
    holidays = json.loads(holidays_body)
    if holidays.get("timezone") != "America/Mexico_City":
        raise ValueError("FIX requires the verified Mexican banking calendar")
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    expected = {
        "SF43718": {d for d in days if business_day(d, holidays)},
        "SF61745": set(days),
        "SP1": {d for d in days if d.day == 1},
    }
    sources, series = {}, {}
    for role, (body, row) in inputs.items():
        if row.get("sha256") != sha(body) or row.get("bytes") != len(body) or row.get("http_status") != 200:
            raise ValueError("Calendar proof requires physical bytes/hash and successful HTTP metadata")
        sources[role] = {
            k: row[k]
            for k in ("source_file", "source_system", "source_url", "logical_key", "sha256", "downloaded_at")
        }
        if role == "fix_methodology":
            continue
        binding(row, "banxico_sie", role, start, end)
        if row["source_url"] != SIE_EXPORT_URL or row["source_system"] != "banxico_sie":
            raise ValueError("Calendar observation role must bind its canonical Banxico response")
        if role == "SF43718":
            labels = list(csv.reader(io.StringIO(body.decode("latin1"))))
            titles = [normalized(r[1]) for r in labels if len(r) == 2 and r[0] == "Título"]
            if len(titles) != 1 or "fecha de determinacion (fix)" not in titles[0]:
                raise ValueError("FIX calendar applies to Fecha de determinación, not DOF/payments")
        frame = banxico_file(body, role)
        selected = frame.loc[frame.date.between(pd.Timestamp(start), pd.Timestamp(end))]
        observed = set(selected.date.dt.date)
        if observed and max(observed) > local_time(row["downloaded_at"]).date():
            raise ValueError("Calendar contains future observations relative to its original capture")
        series[role] = {
            "universe": {
                "SF43718": "MX_banking_days_FIX_determination",
                "SF61745": "all_calendar_days",
                "SP1": "one_native_month_anchor_day1",
            }[role],
            "completeness_basis": {
                "SF43718": "official_FIX_determination_banking_days_and_verified_MX_calendar",
                "SF61745": "full_daily_universe_sufficient_not_inferred_provider_schedule",
                "SP1": "native_monthly_frequency_with_day1_anchor",
            }[role],
            "provider_schedule_inferred": False,
            "expected_count": len(expected[role]),
            "observed_count": len(selected),
            "missing_dates": sorted(d.isoformat() for d in expected[role] - observed),
            "unexpected_dates": sorted(d.isoformat() for d in observed - expected[role]),
            "complete": observed == expected[role],
        }
    return {
        "version": 1,
        "period": period,
        "timezone": "America/Mexico_City",
        "date_basis": "native_date_labels_without_UTC_conversion",
        "inputs": sources,
        "fix_methodology_locator": locator,
        "banking_calendar": {
            "path": HOLIDAYS.relative_to(ROOT).as_posix(),
            "sha256": sha(holidays_body),
            "years": {str(start.year): holidays["years"][str(start.year)]},
        },
        "series": series,
        "calendar_completeness_certified": all(r["complete"] for r in series.values()),
        "first_publication_date": None,
        "release_lag_days": None,
    }


def verify_workspace(workspace, period, proof):
    """Recompute the proof from physical originals rather than trust a result flag."""
    workspace = safe_workspace(Path(workspace))
    if not isinstance(proof, dict) or set(proof.get("inputs", {})) != ROLES:
        raise ValueError("Missing physical observation-calendar evidence")
    bronze = workspace / "data/bronze"
    manifest = bronze / "_manifest.jsonl"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Calendar manifest must be a regular physical file")
    rows = [json.loads(s) for s in manifest.read_text().splitlines()]
    by_file = {r["source_file"]: r for r in rows}
    if (
        len(rows) != 4
        or len(by_file) != 4
        or set(by_file) != {r["source_file"] for r in proof["inputs"].values()}
    ):
        raise ValueError("Calendar manifest must identify exactly its four distinct original roles")
    inputs = {}
    for role, identity in proof["inputs"].items():
        relative = identity["source_file"]
        path = bronze / relative
        if (
            Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not path.resolve().is_relative_to(bronze.resolve())
        ):
            raise ValueError("Calendar original must remain inside candidate Bronze")
        row = by_file[relative]
        sidecar = Path(str(path) + ".meta.json")
        if any(p.is_symlink() or not p.is_file() for p in (path, sidecar)):
            raise ValueError("Calendar original and sidecar must be regular physical files")
        meta = json.loads(sidecar.read_text())
        if any(row.get(k) != v for k, v in identity.items()) or any(
            meta.get(k) != row.get(k) for k in (*identity, "http_status", "bytes")
        ):
            raise ValueError("Calendar physical original/sidecar/evidence identity changed")
        inputs[role] = path.read_bytes(), row
    actual = certify(inputs, period)
    if actual != proof:
        raise ValueError("Observation-calendar evidence changed on physical replay")
    return actual


def verify_candidate(item, result, cutoff):
    from src.source_updates.retained import originals
    from src.source_updates.series_native import read

    if not item.get("receipt_id"):
        raise ValueError("Calendar availability requires the actual retained-original receipt")
    inputs, receipt_sha = originals(Path(item["workspace"]), "banxico", item["receipt_id"], cutoff)
    if result.get("retention_receipt_sha256") != receipt_sha:
        raise ValueError("Calendar proof is not bound to the accepted retention receipt")
    silver, details = read("banxico", inputs, item["period"])
    proof = verify_workspace(item["workspace"], item["period"], result.get("observation_calendar"))
    if (
        details["observation_calendar"] != proof
        or result.get("calendar_completeness_certified") is not proof["calendar_completeness_certified"]
    ):
        raise ValueError("Calendar result differs from physical series/methodology replay")
    try:
        pd.testing.assert_frame_equal(
            pd.read_parquet(Path(item["workspace"]) / "data/silver/macro_indicators.parquet"),
            silver["macro_indicators"],
            check_exact=True,
        )
    except AssertionError as exc:
        raise ValueError("Calendar native observations differ from exact source replay") from exc
    return proof
