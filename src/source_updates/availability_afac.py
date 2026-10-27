"""AFAC published dossier availability, separate from observational completeness."""

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src.ingest.afac.download import DATATUR_CATALOG_URL, DATATUR_DATABASE_URL
from src.source_updates import availability as physical
from src.source_updates.calendar import local_time
from src.source_updates.catalog import bronze_aliases, load_catalog, product_map
from src.source_updates.collection import validate_url


def latest(index):
    soup = BeautifulSoup(index.read_bytes(), "html.parser")
    if soup.find("base", href=True):
        raise ValueError("AFAC official index base changed")
    periods, database = {}, set()
    for link in soup.select("a[href]"):
        url = urljoin(DATATUR_CATALOG_URL, link["href"])
        path = urlsplit(url).path
        label = link.get_text(" ", strip=True).casefold()
        document = path.lower().endswith((".pdf", ".zip", ".xlsx"))
        subject = "afac" in (path.casefold() + " " + label)
        topic = re.search(r"bolet[ií]n|tr[áa]fico|pasajeros|base de datos|\bpdf\b", label)
        dated = re.search(r"\b20\d{2}\b", label + " " + path)
        relevant = (
            "/documentoscompartidos/afac/" in path.casefold()
            or (subject and (document or dated or topic))
            or bool(topic and dated)
        )
        if not relevant:
            continue
        validate_url(url, ["datatur.sectur.gob.mx"])
        if url == DATATUR_DATABASE_URL:
            database.add(url)
            continue
        match = re.fullmatch(r"/Documentoscompartidos/afac/AFAC_(20\d{2})_(0[1-9]|1[0-2])\.pdf", path)
        if not match:
            raise ValueError("Unclassified AFAC bulletin/database link; discovery requires review")
        periods.setdefault(f"{match[1]}M{match[2]}", set()).add(url)
    if not periods or database != {DATATUR_DATABASE_URL}:
        raise ValueError("AFAC index must advertise monthly bulletins and its exact database ZIP")
    period = max(periods)
    if len(periods[period]) != 1:
        raise ValueError("Latest AFAC bulletin edition is ambiguous")
    return period, {"pdf": next(iter(periods[period])), "database": DATATUR_DATABASE_URL}


def verify(item, result, cutoff):
    binding = item["availability"]
    root = physical.preflight(binding, item["workspace"])
    if set(binding) != physical.MULTI_FIELDS:
        raise ValueError("AFAC availability requires both original roles, never a single PDF")
    before = physical.collection_inventory(root)
    receipt_path = root / "receipts" / f"collection-{binding['run_id']}.json"
    receipt_sha = physical.sha(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    required = dict(
        run_id=binding["run_id"],
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
    )
    if any(receipt.get(key) != value for key, value in required.items()):
        raise ValueError("AFAC availability requires its complete immutable collection receipt")
    aliases = bronze_aliases("afac_carriers")
    hosts = load_catalog()[product_map()["afac_carriers"]["source_key"]]["allowed_hosts"]
    roles = {"catalog": binding["catalog_item"], **binding["artifact_items"]}
    chosen, paths, records = {}, {}, {}
    for role, key in roles.items():
        matches = [r for r in receipt["items"] if r["id"] == key]
        status = "collected_catalog" if role == "catalog" else "collected_unvalidated"
        if (
            len(matches) != 1
            or matches[0].get("product") != "afac_carriers"
            or matches[0].get("status") != status
        ):
            raise ValueError("AFAC requires exact product-specific index and two distinct originals")
        row = chosen[role] = matches[0]
        paths[role], records[role] = physical.artifact(root, row, cutoff, hosts, receipt, aliases)
    if any(chosen["catalog"][key] != DATATUR_CATALOG_URL for key in ("source_url", "response_url")):
        raise ValueError("AFAC discovery must use the reviewed official index URL")
    period, urls = latest(paths["catalog"])
    if period != item["period"]:
        raise ValueError("AFAC candidate is not the latest advertised monthly bulletin")
    for role, url in urls.items():
        row = chosen[role]
        if row["requested_period"] != period or any(
            row[key] != url for key in ("source_url", "response_url")
        ):
            raise ValueError("AFAC original does not match the exact discovered dossier role/period")
        if local_time(records["catalog"]["downloaded_at"]) > local_time(records[role]["downloaded_at"]):
            raise ValueError("AFAC official discovery must precede both original captures")
    native = pd.read_parquet(Path(item["workspace"]) / "data/silver/afac_carriers_source_native.parquet")
    columns = {"source_file", "source_hash", "source_system"}
    if not columns <= set(native):
        raise ValueError("AFAC native dossier lacks physical identity columns")
    expected = {(chosen[r]["source_file"], chosen[r]["sha256"]) for r in urls}
    observed = set(native[["source_file", "source_hash"]].itertuples(index=False, name=None))
    if (
        result.get("monthly_coverage_verified") is not True
        or result.get("complete_month_certified") is not False
        or type(result.get("source_declares_incomplete_international_reporting")) is not bool
        or observed != expected
        or not set(native.source_system) <= set(aliases)
        or physical.collection_inventory(root) != before
        or physical.sha(receipt_path) != receipt_sha
    ):
        raise ValueError("AFAC physical discovery does not bind the completely replayed reported dossier")
    return dict(
        collection_receipt_sha256=receipt_sha,
        official_index_sha256=chosen["catalog"]["sha256"],
        source_artifacts={
            role: {k: chosen[role][k] for k in ("source_file", "sha256", "source_url")} for role in urls
        },
        latest_available_period=period,
        source_availability_observed_at=max((records[r]["downloaded_at"] for r in urls), key=local_time),
        round_as_of=cutoff,
        discovery_url=DATATUR_CATALOG_URL,
        discovery_contract_product="afac_carriers",
        physical_collection_files=before,
        reported_dossier_verified=True,
        complete_month_certified=False,
        source_declares_incomplete_international_reporting=result[
            "source_declares_incomplete_international_reporting"
        ],
        scope="published_reported_dossier_not_complete_observational_universe",
    )
