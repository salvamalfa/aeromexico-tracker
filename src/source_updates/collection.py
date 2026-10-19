"""Bounded acquisitions to ignored candidate workspaces, with one OS-level writer."""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit
from uuid import uuid4

import httpx

from src.source_updates.catalog import ROOT, bronze_aliases, load_catalog, product_map


def safe_workspace(path: Path) -> Path:
    target = path.resolve()
    boundary = (ROOT / "tmp/source-updates").resolve()
    if target == boundary or not target.is_relative_to(boundary):
        raise ValueError("Candidate workspace must be a child of this checkout's tmp/source-updates/")
    if target != path.absolute() or any(child.is_symlink() for child in target.rglob("*")):
        raise ValueError("Candidate workspace cannot contain symlinks or traversal")
    return target


@contextmanager
def writer(path: Path):
    path = safe_workspace(path)
    path.mkdir(parents=True, exist_ok=True)
    lock = path / ".source-update.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def validate_url(url: str, allowed_hosts: list[str]) -> None:
    value = urlsplit(url)
    if (
        value.scheme != "https"
        or value.username
        or value.password
        or value.fragment
        or value.port not in {None, 443}
        or not value.hostname
        or not any(value.hostname == host or value.hostname.endswith("." + host) for host in allowed_hosts)
        or any(_credential_query_key(key) for key, _ in parse_qsl(value.query, keep_blank_values=True))
    ):
        raise ValueError("Only public HTTPS URLs on catalogue hosts without credentials are allowed")


def _credential_query_key(key: str) -> bool:
    # Bracket/dot nesting and qualifiers must not hide an inner credential.
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return any(
        component.casefold() in {"key", "auth", "pwd"}
        or re.search(
            r"(?i)(api[_-]?key|access[_-]?key|secret[_-]?key|token|password|passwd|secret|signature|credential|authorization)(?:s|[0-9]+)?$",
            component,
        )
        for component in re.split(r"[\W_]+", key)
        if component
    )


def selection_plan(selection: dict, workspace: Path) -> dict:
    safe_workspace(workspace)
    sources, products = load_catalog(), product_map()
    items = selection.get("items", [])
    if selection.get("version") != 1 or not items or len(items) > 50:
        raise ValueError("Selection v1 requires 1..50 explicitly selected artifacts")
    identifiers, calls = set(), 0
    for item in items:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", item["id"]) or item["id"] in identifiers:
            raise ValueError("Selection artifact IDs must be safe and unique")
        identifiers.add(item["id"])
        product = products[item["product"]]
        source = sources[product["source_key"]]
        if not source["is_active"] or not source["artifact_expected"]:
            raise ValueError("Inactive/error/internal sources cannot be collected")
        validate_url(item["url"], source["allowed_hosts"])
        if item.get("source_system") not in bronze_aliases(item["product"]):
            raise ValueError("source_system must be a parser-compatible Bronze alias for this product")
        if item.get("purpose") not in {"catalog", "data"}:
            raise ValueError("Declare catalog discovery or data acquisition explicitly")
        if not re.fullmatch(r"[a-z0-9]+", item.get("extension", "")):
            raise ValueError("Declare a safe extension")
        if not item.get("entity") or not item.get("period"):
            raise ValueError("Each artifact requires entity and period; use current only for catalogs")
        if item.get("relative_dir"):
            directory = Path(item["relative_dir"])
            if directory.is_absolute() or any(
                not re.fullmatch(r"[A-Za-z0-9_-]+", component) for component in directory.parts
            ):
                raise ValueError("relative_dir must be a safe Bronze-relative directory")
        mode = item.get("mode", "get")
        if mode not in {"get", "manual", "bts_year", "banxico_series"}:
            raise ValueError("Only get, manual, bts_year or banxico_series modes are supported")
        if mode != "manual" and product["source_key"] in {"sec_edgar", "aena_spain"}:
            raise ValueError("SEC identity / Aena authenticated exports require manual import here")
        if mode == "manual":
            relative = Path(item["local_file"])
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not (workspace / "imports" / relative)
                .resolve()
                .is_relative_to((workspace / "imports").resolve())
            ):
                raise ValueError("Manual inputs must be relative files inside candidate imports/")
            if not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")):
                raise ValueError("Manual input requires its SHA-256")
        elif mode == "bts_year":
            from src.ingest.bts.t100 import FORM_URL

            if (
                item["product"] != "bts_segments"
                or item["url"] != FORM_URL
                or not isinstance(item.get("year"), int)
                or not 1990 <= item["year"] <= 2100
                or item["period"] != str(item["year"])
                or item["extension"] != "zip"
                or item["purpose"] != "data"
            ):
                raise ValueError("BTS requires an explicit year/ZIP with the exact T-100 form URL")
            calls += 2
        elif mode == "banxico_series":
            from src.ingest.macro.banxico import BANXICO_SERIES, SIE_EXPORT_URL, START_DATE

            end = item.get("end_date", "")
            # Validate the ISO date before constructing the public export form.
            from datetime import date

            date.fromisoformat(end)
            if (
                item["product"] != "banxico"
                or item["url"] != SIE_EXPORT_URL
                or item["entity"] not in BANXICO_SERIES
                or item["extension"] != "csv"
                or item["period"] != f"{START_DATE}_{end}"
                or item["purpose"] != "data"
            ):
                raise ValueError("Banxico public export requires an exact known series and date window")
            calls += 1
        else:
            calls += 1
    return {
        "mode": "dry_run",
        "items": items,
        "base_requests": calls,
        "maximum_http_requests": calls * 5,
        "paid_requests": 0,
        "destinations": [str(workspace / "data/bronze"), str(workspace / "receipts")],
        "revalidation": "every_selected_url_including_current_and_historical_bts_years",
        "activation": "none",
        "latest_validated_period": None,
    }


def _payload(content: bytes, extension: str) -> None:
    if not content:
        raise ValueError("Empty response")
    lower = content[:8192].lower()
    if any(token in lower for token in (b"access denied", b"captcha", b"cf-chl-", b"sign in to continue")):
        raise ValueError("Access challenge, not a valid source")
    if extension == "pdf" and not content.lstrip().startswith(b"%PDF"):
        raise ValueError("Expected PDF, possibly received a portal/error page")
    if extension in {"zip", "xlsx"}:
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if not archive.namelist() or archive.testzip():
                raise ValueError("Corrupt/empty ZIP")
    if extension == "json":
        json.loads(content)
    if extension in {"csv", "xls"} and (b"<html" in lower or b"<!doctype html" in lower):
        raise ValueError("Expected data, received HTML")


def collect(selection: dict, workspace: Path, *, execute: bool = False, client_factory=None) -> dict:
    """No network/writes in the default path. Collection never means validation."""
    workspace = safe_workspace(workspace)
    planned = selection_plan(selection, workspace)
    if not execute:
        return planned
    from src.common.http import SourceHttpClient
    from src.common.storage import save_bronze

    factory = client_factory or SourceHttpClient
    products, sources = product_map(), load_catalog()
    receipt = {
        "version": 1,
        "run_id": uuid4().hex,
        "mode": "collection",
        "started_at": datetime.now(UTC).isoformat(),
        "items": [],
        "activation": "none",
        "publication": "not_authorized",
        "paid_requests": 0,
    }
    with writer(workspace):
        for item in planned["items"]:
            product = products[item["product"]]
            source = sources[product["source_key"]]
            result = {
                "id": item["id"],
                "product": item["product"],
                "requested_period": item["period"],
                "source_url": item["url"],
                "published_at": item.get("published_at"),
                "latest_available_period": None,
                "latest_validated_period": None,
                "latest_published_period": None,
                "release_lag_days": None,
            }
            try:
                status, content_type = 200, "application/octet-stream"
                url = item["url"]
                if item.get("mode") == "manual":
                    content = (workspace / "imports" / item["local_file"]).read_bytes()
                    if hashlib.sha256(content).hexdigest() != item["sha256"]:
                        raise ValueError("Manual input hash mismatch")
                else:
                    rate = {
                        "bts_t100": "bts",
                        "afac": "afac",
                        "bmv": "bmv",
                        "banxico_sie": "banxico",
                        "aeromexico_ir": "aeromexico_ir",
                    }.get(product["source_key"], "default")
                    with factory(rate, max_attempts=1) as client:
                        # Redirect targets are checked BEFORE each request. Five total
                        # calls per operation, including redirects. TLS stays enabled.
                        def request(method, target, **kwargs):
                            for _ in range(5):
                                validate_url(target, source["allowed_hosts"])
                                try:
                                    response = client.request(
                                        method, target, follow_redirects=False, **kwargs
                                    )
                                except httpx.HTTPStatusError as exc:
                                    # SourceHttpClient raises on 3xx when redirects
                                    # are disabled; inspect without following them.
                                    if not exc.response.is_redirect:
                                        raise
                                    response = exc.response
                                if response.status_code in {301, 302, 303, 307, 308}:
                                    target = urljoin(target, response.headers["location"])
                                    if response.status_code == 303:
                                        method, kwargs = "GET", {}
                                    continue
                                if response.status_code != 200:
                                    raise ValueError(
                                        f"HTTP {response.status_code}: not complete source content"
                                    )
                                return response
                            raise ValueError("Redirect limit exceeded")

                        if item.get("mode") == "banxico_series":
                            from src.ingest.macro.banxico import sie_export_form

                            form = sie_export_form(item["entity"], item["end_date"])
                            result["public_request_form"] = form
                            response = request("POST", url, data=form)
                        else:
                            response = request("GET", url)
                        if item.get("mode") == "bts_year":
                            from src.ingest.bts.t100 import _post_payload

                            action, payload = _post_payload(response.text, year=item["year"])
                            response = request("POST", action, data=payload)
                        content, status = response.content, response.status_code
                        content_type = response.headers.get("content-type", content_type)
                        result["http_status"] = status
                _payload(content, item["extension"])
                directory = item.get("relative_dir")
                if item.get("mode") == "bts_year":
                    from src.ingest.bts.t100 import logical_source_url

                    # Existing parser selects archives by requested_year in the
                    # logical URL; retain the actual form URL separately.
                    url = logical_source_url(item["year"])
                    result["request_url"] = item["url"]
                    result["source_url"] = url
                    directory = directory or f"bts/t100/{item['year']}"
                path = save_bronze(
                    content,
                    item["source_system"],
                    item["entity"],
                    item["period"],
                    item["extension"],
                    url,
                    "manual" if item.get("mode") == "manual" else "httpx",
                    bronze_root=workspace / "data/bronze",
                    relative_dir=directory,
                    http_status=status,
                    content_type=content_type,
                    notes=(
                        f"Candidate only; product={item['product']}; purpose={item['purpose']}; unvalidated"
                    ),
                )
                result.update(
                    status="collected_catalog" if item["purpose"] == "catalog" else "collected_unvalidated",
                    sha256=hashlib.sha256(content).hexdigest(),
                    source_file=path.relative_to(workspace / "data/bronze").as_posix(),
                    bytes=len(content),
                )
                if item["purpose"] == "catalog" and item["extension"] in {"html", "htm"}:
                    from bs4 import BeautifulSoup

                    links = []
                    for anchor in BeautifulSoup(content, "html.parser").find_all("a", href=True):
                        candidate = urljoin(url, anchor["href"])
                        try:
                            validate_url(candidate, source["allowed_hosts"])
                        except ValueError:
                            continue
                        links.append({"url": candidate, "label": anchor.get_text(" ", strip=True)[:240]})
                    result["discovered_links"] = list({link["url"]: link for link in links}.values())
            except Exception as exc:
                # Never log arbitrary bodies, headers or credential-bearing exceptions.
                result.update(status="access_or_payload_failed", error_type=type(exc).__name__)
                if isinstance(exc, httpx.HTTPStatusError):
                    result["http_status"] = exc.response.status_code
                elif isinstance(exc, ValueError):
                    result["reason"] = str(exc)
            receipt["items"].append(result)
        receipt["status"] = (
            "collected_unvalidated"
            if all(row["status"].startswith("collected_") for row in receipt["items"])
            else "incomplete"
        )
        receipt["finished_at"] = datetime.now(UTC).isoformat()
        output = workspace / "receipts" / f"collection-{receipt['run_id']}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
