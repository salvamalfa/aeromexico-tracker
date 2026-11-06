"""Prevent a site replacement from dropping the active official routes release."""

from pathlib import Path

from src.dashboard.official_routes_contract import PUBLIC_PATH

from . import manifest as manifests
from .records import PublicationRefused
from .source_data_scope import PROOF

CONTRACT = "official-routes.schema.json"


def require_preserved_release(site: Path, candidate: dict) -> None:
    if not (site / PUBLIC_PATH).is_file():
        manifest_path = site / manifests.MANIFEST_NAME
        if not manifest_path.is_file():
            return
        baseline = manifests.load_manifest(site)
        if not any(row["path"] == PUBLIC_PATH for row in baseline["files"]):
            return
    files = {row["path"] for row in candidate["files"]}
    if {PUBLIC_PATH, PROOF} <= files and candidate["contracts"].get(CONTRACT):
        return
    raise PublicationRefused(
        "The published official routes require their payload, contract pin and source-data proof. "
        "Use the typed issuer, movements or source-data publication for the reviewed change."
    )
