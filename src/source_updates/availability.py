"""Bind reviewed official discovery to the exact bytes used by a candidate.

A successful download alone never proves latest availability. Unsupported source
families remain blocked until their official discovery contract is reviewed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from src.source_updates.calendar import local_time
from src.source_updates.catalog import bronze_aliases, load_catalog, product_map
from src.source_updates.collection import safe_workspace, validate_url

FIELDS = {"workspace", "run_id", "catalog_item", "artifact_item"}
MULTI_FIELDS = (FIELDS - {"artifact_item"}) | {"artifact_items"}
AIFA_INDEX = "https://www.aifa.aero/legal-y-finanzas/informes"
MONTHS = "Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic".split()
MONTH_NAMES = (
    "Enero Febrero Marzo Abril Mayo Junio Julio Agosto Septiembre Octubre Noviembre Diciembre".split()
)
ARCHIVES = {
    "https://aifa-website.s3.amazonaws.com/contenido/RJPyE/": {
        "Numeralia+Aeroportuaria+Marzo+-+Diciembre+2022+.pdf": "2022",
        "Numeralia-Aeroportuaria-Mar-Dic.-2022.xlsx": "2022",
    },
    "https://aifa-website.s3.us-east-1.amazonaws.com/contenido/RJPyE/": {
        "Numeralia%20Aeroportuaria%20Ene.%20a%20Dic.%202023.pdf": "2023",
        "Numeralia%20Aeroportuaria%20Ene.%20a%20Dic.%202023.xlsx": "2023",
        "Numeralia+Aeroportuaria+Ene.+a+Dic.+2024.pdf": "2024",
        "Numeralia+Aeroportuaria+Ene.+a+Dic.+2024.xlsx": "2024",
        "Numeralia+Aeroportuaria+Ene.+a+Dic.+2025.pdf": "2025",
        "Numeralia+Aeroportuaria+Ene.+a+Dic.+2025.xlsx": "2025",
    },
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(binding, candidate):
    if not isinstance(binding, dict) or set(binding) not in (FIELDS, MULTI_FIELDS):
        raise ValueError("Availability requires exact physical collection binding fields")
    identities = [binding[k] for k in ("workspace", "run_id", "catalog_item")]
    if set(binding) == MULTI_FIELDS:
        roles = binding["artifact_items"]
        if not isinstance(roles, dict) or set(roles) != {"pdf", "database"}:
            raise ValueError("Multi-original availability requires exact AFAC pdf/database roles")
        identities += list(roles.values())
    else:
        identities.append(binding["artifact_item"])
    if any(not isinstance(v, str) or not v for v in identities):
        raise ValueError("Availability binding values must be nonempty strings")
    if set(binding) == MULTI_FIELDS and len(set(identities[2:])) != 3:
        raise ValueError("Discovery and original collection item IDs must be distinct")
    if not re.fullmatch(r"[a-f0-9]{32}", binding["run_id"]):
        raise ValueError("Availability requires an exact collection run ID")
    root = safe_workspace(Path(binding["workspace"]))
    candidate = safe_workspace(Path(candidate))
    if root == candidate or root.is_relative_to(candidate) or candidate.is_relative_to(root):
        raise ValueError("Discovery collection and certified candidate must be disjoint")
    return root


def collection_inventory(root):
    safe_workspace(root)
    if (root / ".source-update.lock").exists():
        raise ValueError("Availability collection has an active writer")
    return {p.relative_to(root).as_posix(): sha(p) for p in root.rglob("*") if p.is_file()}


def artifact(root, row, cutoff, hosts, receipt, aliases):
    source = root / "data/bronze"
    relative = Path(row["source_file"])
    path = source / relative
    if relative.is_absolute() or ".." in relative.parts or path.is_symlink() or not path.is_file():
        raise ValueError("Availability artifact must be a physical Bronze file")
    records = [json.loads(line) for line in (source / "_manifest.jsonl").read_text().splitlines()]
    selected = [record for record in records if record["source_file"] == row["source_file"]]
    if len(selected) != 1:
        raise ValueError("Availability artifact requires exactly one manifest record")
    record = selected[0]
    sidecar = Path(str(path) + ".meta.json")
    if sidecar.is_symlink() or json.loads(sidecar.read_text()) != record:
        raise ValueError("Availability manifest and physical source sidecar differ")
    if (
        row.get("http_status") != 200
        or record.get("http_status") != 200
        or record.get("download_method") != "httpx"
        or record.get("source_system") not in aliases
        or record["sha256"] != row["sha256"]
        or sha(path) != row["sha256"]
        or record["source_url"] != row["source_url"]
        or row["bytes"] != path.stat().st_size
    ):
        raise ValueError("Availability artifact differs from a successful direct official capture")
    for url in (row["source_url"], row.get("response_url", "")):
        validate_url(url, hosts)
    stamp, as_of = local_time(record["downloaded_at"]), local_time(cutoff)
    started, finished = local_time(receipt["started_at"]), local_time(receipt["finished_at"])
    # Availability is asserted only on the round's local capture date. Older
    # retained discovery still proves history, never today's latest selection.
    if not started <= stamp <= finished <= as_of or stamp.date() != as_of.date():
        raise ValueError("Availability discovery/capture must belong to the explicit round date")
    return path, record


def latest_aifa(index_path):
    soup = BeautifulSoup(index_path.read_bytes(), "html.parser")
    if soup.find("base", href=True):
        raise ValueError("AIFA official discovery base changed")
    periods, all_periods = {}, set()
    for link in soup.find_all("a", href=True):
        url = urljoin(AIFA_INDEX, link["href"])
        label = " ".join(link.get_text(" ", strip=True).split())
        if "numeralia" not in (url + " " + label).casefold():
            continue
        historical = next(
            (
                year
                for prefix, entries in ARCHIVES.items()
                for name, year in entries.items()
                if url == prefix + name
            ),
            None,
        )
        if historical:
            if historical not in label or "Diciembre" not in label:
                raise ValueError("AIFA historical discovery label changed")
            continue
        match = re.fullmatch(
            r"https://aifa-repositorio\.s3\.us-east-1\.amazonaws\.com/PyE/"
            r"Numeralia-Aeroportuaria-([A-Z][a-z]{2})-(20\d{2})\.(pdf|xlsx)",
            url,
        )
        title = re.fullmatch(
            r"Numeralia Aeroportuaria de Enero a ([A-Za-z]+) (20\d{2}) - Formato (PDF|XLSX) \(PDF\)", label
        )
        if (
            not match
            or match[1] not in MONTHS
            or not title
            or title[1] != MONTH_NAMES[MONTHS.index(match[1])]
            or title[2] != match[2]
            or title[3].lower() != match[3]
        ):
            raise ValueError("AIFA official workbook discovery layout changed")
        period = f"{match[2]}M{MONTHS.index(match[1]) + 1:02d}"
        all_periods.add(period)
        if match[3] != "xlsx":
            continue
        if period in periods and periods[period] != url:
            raise ValueError("Ambiguous AIFA official workbook edition")
        periods[period] = url
    if not periods:
        raise ValueError("AIFA official index contains no reviewed workbook links")
    period = max(periods)
    if period != max(all_periods):
        raise ValueError("AIFA has a newer relevant report than the selected workbook")
    return period, periods[period]


def discovery_contract(product, adapter):
    """Reviewed provider/product bindings; no caller-selected native table/parser."""
    if product == "am_traffic_ir" and adapter == "am_traffic_ir":
        from src.source_updates.am_traffic import ENTRY, latest

        return ENTRY, latest, "silver/aeromexico_ir_monthly_metrics"
    if product == "aifa_traffic" and adapter == "government":
        return AIFA_INDEX, latest_aifa, "silver/government_native"
    if (product, adapter) in {("aicm_traffic", "government"), ("oma_traffic", "retained")}:
        from src.source_updates.availability_airports import latest
        from src.source_updates.recipes import describe

        table = (
            "silver/government_native" if adapter == "government" else "silver/source_products/oma_traffic"
        )
        return describe(product)["entry_url"], lambda p: latest(p, product), table
    if product == "viva_traffic" and adapter == "retained":
        from src.source_updates.availability_viva import ENTRY, latest

        return ENTRY, latest, "silver/source_products/viva_traffic"
    raise ValueError("Latest-source discovery contract is not yet implemented for this family")


def verify(item, result, cutoff):
    """Called only after complete offline candidate replay; never performs IO on the network."""
    if item["product"] == "bts_segments" and item["adapter"] == "bts":
        from src.source_updates.availability_bts import verify as verify_bts

        return verify_bts(item, result, cutoff)
    if item["product"] == "afac_carriers" and item["adapter"] == "carrier_source":
        from src.source_updates.availability_afac import verify as verify_afac

        return verify_afac(item, result, cutoff)
    binding = item["availability"]
    root = preflight(binding, item["workspace"])
    if set(binding) != FIELDS:
        raise ValueError("This product requires its single-original availability binding")
    collection_before = collection_inventory(root)
    entry, discover, native_table = discovery_contract(item["product"], item["adapter"])
    receipt_path = root / "receipts" / f"collection-{binding['run_id']}.json"
    before = sha(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    if (
        receipt.get("run_id") != binding["run_id"]
        or receipt.get("mode") != "collection"
        or receipt.get("status") != "collected_unvalidated"
        or receipt.get("activation") != "none"
        or receipt.get("publication") != "not_authorized"
    ):
        raise ValueError("Availability requires a complete immutable collection receipt")
    rows = receipt["items"]
    chosen = []
    for key, status in (("catalog_item", "collected_catalog"), ("artifact_item", "collected_unvalidated")):
        matches = [r for r in rows if r["id"] == binding[key]]
        if (
            len(matches) != 1
            or matches[0].get("product") != item["product"]
            or matches[0].get("status") != status
        ):
            raise ValueError("Availability requires exact product-specific discovery and artifact items")
        chosen.append(matches[0])
    index, data = chosen
    hosts = load_catalog()[product_map()[item["product"]]["source_key"]]["allowed_hosts"]
    aliases = bronze_aliases(item["product"])
    index_path, index_record = artifact(root, index, cutoff, hosts, receipt, aliases)
    data_path, data_record = artifact(root, data, cutoff, hosts, receipt, aliases)
    if index["source_url"] != entry or index["response_url"] != entry:
        raise ValueError("Availability requires its reviewed official discovery URL")
    period, url = discover(index_path)
    if (
        period != item["period"]
        or data["requested_period"] != period
        or data["source_url"] != url
        or data["response_url"] != url
    ):
        raise ValueError("Certified period/artifact is not the latest report in official discovery")
    if local_time(index_record["downloaded_at"]) > local_time(data_record["downloaded_at"]):
        raise ValueError("Latest official discovery must precede the selected capture")
    native = pd.read_parquet(Path(item["workspace"]) / f"data/{native_table}.parquet")
    if not {"source_file", "source_hash", "source_system"} <= set(native):
        raise ValueError("Native product lacks physical source identity columns")
    if (
        result.get("complete_month_certified") is not True
        or set(native.source_hash) != {data["sha256"]}
        or set(native.source_file) != {data["source_file"]}
        or not set(native.source_system) <= set(aliases)
        or sha(data_path) != data["sha256"]
        or sha(index_path) != index["sha256"]
        or sha(receipt_path) != before
        or collection_inventory(root) != collection_before
    ):
        raise ValueError("Discovery/capture bytes do not bind the completely verified native product")
    return {
        "collection_receipt_sha256": before,
        "official_index_sha256": index["sha256"],
        "source_artifact_sha256": data["sha256"],
        "latest_available_period": period,
        "source_availability_observed_at": data_record["downloaded_at"],
        "round_as_of": cutoff,
        "discovery_url": entry,
        "discovery_contract_product": item["product"],
        "physical_collection_files": collection_before,
    }
