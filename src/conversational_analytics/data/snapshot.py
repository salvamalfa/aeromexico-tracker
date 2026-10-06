"""Verified, immutable reader for the public Pages snapshot."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from src.web_export.privacy import check_file_size, check_privacy, load_privacy_rules
from src.web_export.schemas import (
    ANALYSIS_SCHEMA,
    EXECUTIVE_SCHEMA,
    MARKET_SCHEMA,
    NETWORK_FILE_SCHEMA,
    QUARTERS_FILE_SCHEMA,
)


class SnapshotError(ValueError):
    """The published site snapshot is incomplete, altered, or unsafe."""


# (file sha256, schema digest) pairs that already passed validation in this
# process. Bytes are hash-checked against the manifest before validation and
# JSON Schema validation is deterministic, so identical pairs never need a
# second pass; tests and long-lived processes load the same site repeatedly.
_VALIDATED_PAYLOADS: set[tuple[str, str]] = set()


def data_version(manifest: dict[str, Any]) -> str:
    """Identify the data a conversation is pinned to, not the page that shows it.

    Only `data/` file hashes, contract hashes and the approved analysis manifest
    count. Republishing UI assets or a new `code_commit` keeps the version, so
    open conversations and pinned evaluations survive interface-only releases.
    """
    pinned = {
        "files": sorted(
            (
                {"path": entry["path"], "sha256": entry["sha256"], "bytes": entry["bytes"]}
                for entry in manifest["files"]
                if entry["path"].startswith("data/")
            ),
            key=lambda entry: entry["path"],
        ),
        "contracts": manifest.get("contracts", {}),
        "analysis_manifest": manifest.get("analysis_manifest", []),
    }
    encoded = json.dumps(pinned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class Snapshot:
    """Load `site/` once, verify its manifest, and expose read-only public data.

    `root` is the site root containing publication_manifest.json and data/v1/.
    No path outside that tree is followed and no warehouse is opened.
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.project_root = next(
            (
                parent
                for parent in (self.root.parent, *self.root.parent.parents)
                if (parent / "contracts/web").is_dir() and (parent / "config/chat").is_dir()
            ),
            Path(__file__).resolve().parents[3],
        )
        manifest_path = self.root / "publication_manifest.json"
        if not manifest_path.is_file():
            raise SnapshotError("No existe publication_manifest.json en la raíz del sitio")
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
        self._validate_schema(self.project_root / "contracts/web/publication_manifest.schema.json", manifest)
        self.manifest = MappingProxyType(manifest)
        self.version = data_version(manifest)
        files = manifest["files"]
        paths: dict[str, dict[str, Any]] = {}
        for entry in files:
            rel = entry["path"]
            pure = PurePosixPath(rel)
            if pure.is_absolute() or ".." in pure.parts or "\\" in rel:
                raise SnapshotError(f"Ruta insegura en manifiesto: {rel}")
            if rel in paths:
                raise SnapshotError(f"Ruta duplicada en manifiesto: {rel}")
            paths[rel] = entry
        contracts_dir = self.project_root / "contracts/web"
        for name, expected in manifest["contracts"].items():
            contract = (contracts_dir / name).resolve()
            if contracts_dir.resolve() not in contract.parents or not contract.is_file():
                raise SnapshotError(f"Contrato de publicación no disponible: {name}")
            if hashlib.sha256(contract.read_bytes()).hexdigest() != expected:
                raise SnapshotError(f"Hash de contrato distinto al manifiesto: {name}")
        privacy_rules = load_privacy_rules(contracts_dir / "privacy.yaml")
        actual_data_files = {
            p.relative_to(self.root).as_posix() for p in (self.root / "data/v1").rglob("*") if p.is_file()
        }
        declared_data_files = {p for p in paths if p.startswith("data/v1/")}
        if actual_data_files != declared_data_files:
            missing = sorted(declared_data_files - actual_data_files)
            extra = sorted(actual_data_files - declared_data_files)
            raise SnapshotError(
                f"Inventario data/v1 distinto al manifiesto (faltan={missing[:3]}, extra={extra[:3]})"
            )

        payloads: dict[str, Any] = {}
        for rel in sorted(declared_data_files):
            path = (self.root / rel).resolve()
            if self.root not in path.parents:
                raise SnapshotError(f"Ruta fuera del sitio: {rel}")
            raw = path.read_bytes()
            try:
                check_file_size(path, privacy_rules)
            except ValueError as exc:
                raise SnapshotError(f"Tamaño excedido: {rel}") from exc
            entry = paths[rel]
            if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise SnapshotError(f"Hash o tamaño incorrecto: {rel}")
            if rel.endswith(".json"):
                try:
                    payloads[rel] = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise SnapshotError(f"JSON inválido: {rel}") from exc
                try:
                    check_privacy(payloads[rel], privacy_rules)
                except ValueError as exc:
                    raise SnapshotError(f"Violación de privacidad en {rel}: {exc}") from exc
        schema_map = {
            "data/v1/executive.json": EXECUTIVE_SCHEMA,
            "data/v1/market.json": MARKET_SCHEMA,
            "data/v1/flights/quarters.json": QUARTERS_FILE_SCHEMA,
        }
        for rel, schema in schema_map.items():
            if rel in payloads:
                self._validate_payload(paths[rel]["sha256"], schema, payloads[rel])
        for rel, payload in payloads.items():
            if rel.startswith("data/v1/analysis/"):
                self._validate_payload(paths[rel]["sha256"], ANALYSIS_SCHEMA, payload)
            if rel.startswith("data/v1/flights/") and rel != "data/v1/flights/quarters.json":
                self._validate_payload(paths[rel]["sha256"], NETWORK_FILE_SCHEMA, payload)
        self._payloads = MappingProxyType(payloads)
        self._catalog = self._load_catalog()
        semantic_digest = hashlib.sha256()
        semantic_files = [
            *sorted((self.project_root / "config/chat").glob("*.yaml")),
            self.project_root / "contracts/chat/semantic.schema.json",
        ]
        for path in semantic_files:
            semantic_digest.update(path.relative_to(self.project_root).as_posix().encode())
            semantic_digest.update(b"\0")
            semantic_digest.update(path.read_bytes())
            semantic_digest.update(b"\0")
        self.semantic_version = semantic_digest.hexdigest()

    @staticmethod
    def _validate_schema(schema_path: Path, value: Any) -> None:
        if not schema_path.is_file():
            raise SnapshotError(f"No se encuentra el esquema {schema_path.name}")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema).iter_errors(value))
        if errors:
            err = errors[0]
            raise SnapshotError(f"{schema_path.name}: {err.json_path}: {err.message}")

    @staticmethod
    def _load_catalog() -> dict[str, Any]:
        base = Path(__file__).resolve().parents[3]
        catalog = {}
        for name in ("entities", "metrics", "question_examples"):
            catalog[name] = yaml.safe_load(
                (base / "config/chat" / f"{name}.yaml").read_text(encoding="utf-8")
            )
        metric_meta = catalog["metrics"]["metadata"]
        for metric in catalog["metrics"]["metrics"]:
            for key in ("owner", "review_status", "effective_from"):
                metric[key] = metric_meta[key]
        schema = json.loads((base / "contracts/chat/semantic.schema.json").read_text(encoding="utf-8"))
        Snapshot._validate_schema_value(schema, catalog)
        return catalog

    @staticmethod
    def _validate_payload(file_sha256: str, schema: dict[str, Any], value: Any) -> None:
        schema_digest = hashlib.sha256(
            json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        key = (file_sha256, schema_digest)
        if key in _VALIDATED_PAYLOADS:
            return
        Snapshot._validate_schema_value(schema, value)
        _VALIDATED_PAYLOADS.add(key)

    @staticmethod
    def _validate_schema_value(schema: dict[str, Any], value: Any) -> None:
        errors = list(Draft202012Validator(schema).iter_errors(value))
        if errors:
            err = errors[0]
            raise SnapshotError(f"semantic.schema.json: {err.json_path}: {err.message}")

    def catalog(self) -> dict[str, Any]:
        return copy.deepcopy(self._catalog)

    def payload(self, rel: str) -> Any:
        """Internal adapter access; return a detached copy."""
        try:
            return copy.deepcopy(self._payloads[rel])
        except KeyError as exc:
            raise SnapshotError(f"Dato público no disponible: {rel}") from exc

    def execute(
        self, tool_name: str, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Convenience entry point; tools remain a separate testable layer."""
        from src.conversational_analytics.tools.registry import ToolRegistry

        return ToolRegistry(self).invoke(tool_name, arguments, context)


__all__ = ["Snapshot", "SnapshotError"]
