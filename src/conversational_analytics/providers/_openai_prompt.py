"""Approved runtime prompt and its versioned dashboard-period policy."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

APPROVED_BASE_PROMPT_SHA256 = "33b8f7a0900869812d98bba57daa2ce3ea2f6b5c02a86a7eb3b8e830c7f7694b"
APPROVED_EFFECTIVE_PROMPT_SHA256 = "439d24fd58a7b3c6c721e15a390824c1b477f52b2b568881dd68bd3655db22a5"
APPROVED_PROMPT_VERSION = "r1-final"
APPROVED_PROMPT_PATH = Path(__file__).resolve().parents[3] / "config/chat/system_prompt.txt"
R2_PROMPT_VERSION = "r2-proposed"
R2_PROMPT_PATH = Path(__file__).resolve().parents[3] / "config/chat/prompt_candidates/system_prompt_r2-proposed.txt"
R2_PROMPT_METADATA_PATH = R2_PROMPT_PATH.with_suffix(".json")
R2_PROMPT_SHA256 = "68961bc7a2dc7d0c79988352b56b2ded2ef7b55e515ce824dba3b2cf516a9edf"
PERIOD_SELECTION_POLICY_VERSION = "dashboard-period-priority-v2"
PERIOD_SELECTION_POLICY = f"""\
<prioridad_de_periodo version="{PERIOD_SELECTION_POLICY_VERSION}">
Para elegir el periodo, sigue esta prioridad: (1) el periodo explícito de la
pregunta actual; (2) el periodo anterior solo si la pregunta actual es un
seguimiento inequívoco de esa consulta; (3) el periodo seleccionado en el
contexto validado del dashboard para la pregunta actual. Si ninguno de esos
contextos aporta un periodo usable, pregunta cuál periodo necesita el usuario.
El contexto del dashboard es el valor predeterminado vigente, no reemplaza un
seguimiento inequívoco. Esta regla solo resuelve periodos omitidos: no infieras
otros campos a partir de esta prioridad de periodo. Para la métrica, pestaña,
entidad, fuente, denominador y filtros, aplica las demás instrucciones del
prompt: el contexto validado puede completar lo que omita la pregunta cuando
la selección sea inequívoca; por ejemplo, «esta gráfica» puede referirse a la
tarjeta activa. Usa el catálogo, las definiciones y ese contexto para resolver
el significado. Si queda una ambigüedad material, pregunta antes de consultar.
Si el periodo es ambiguo, aclara antes de consultar; no supongas el último
publicado ni otro periodo cercano.
</prioridad_de_periodo>"""


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def with_dashboard_period_policy(base_prompt: str) -> str:
    """Append the evaluated period policy once to the approved prompt source."""
    if not isinstance(base_prompt, str) or not base_prompt.strip():
        raise ValueError("Las instrucciones del proveedor no pueden estar vacías")
    if base_prompt.rstrip().endswith(PERIOD_SELECTION_POLICY):
        return base_prompt
    return f"{base_prompt}\n\n{PERIOD_SELECTION_POLICY}"


effective_instructions = with_dashboard_period_policy


def _read_prompt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError("No se pudo cargar el prompt versionado del chat") from exc


def _valid_approval_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _load_r2_instructions() -> str:
    receipt_path = Path(os.environ.get(
        "CHAT_PROMPT_APPROVAL_RECEIPT_PATH",
        str(R2_PROMPT_PATH.parents[1] / "prompt_approval.json"),
    )).resolve()
    expected_receipt_sha = os.environ.get("CHAT_PROMPT_APPROVAL_RECEIPT_SHA256", "").strip().lower()
    if not expected_receipt_sha:
        raise RuntimeError("R2 requiere un recibo de aprobación del prompt con hash fijado")
    try:
        receipt_bytes = receipt_path.read_bytes()
        metadata = json.loads(R2_PROMPT_METADATA_PATH.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("No se pudo verificar el recibo de aprobación de R2") from exc
    if hashlib.sha256(receipt_bytes).hexdigest() != expected_receipt_sha:
        raise RuntimeError("El recibo de aprobación de R2 no coincide con el hash fijado")
    try:
        prompt_path = _read_prompt(R2_PROMPT_PATH)
        prompt_hash = prompt_sha256(prompt_path)
        receipt_capabilities = receipt["capabilities"]
        expected_capabilities = metadata["capabilities"]
        if (
            metadata.get("status") != "proposed_not_approved_not_active"
            or metadata.get("version") != R2_PROMPT_VERSION
            or metadata.get("proposed_effective_prompt_sha256") != R2_PROMPT_SHA256
            or prompt_hash != R2_PROMPT_SHA256
            or receipt.get("schema_version") != 1
            or receipt.get("status") != "owner_approved"
            or receipt.get("version") != R2_PROMPT_VERSION
            or receipt.get("prompt_sha256") != R2_PROMPT_SHA256
            or receipt.get("prompt_path") != "config/chat/prompt_candidates/system_prompt_r2-proposed.txt"
            or not isinstance(receipt.get("decision_ref"), str)
            or not receipt["decision_ref"].strip()
            or receipt.get("owner") != "salvamalfa"
            or not isinstance(receipt.get("approved_at"), str)
            or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
                receipt["approved_at"],
            )
            or not _valid_approval_datetime(receipt["approved_at"])
            or receipt_capabilities != expected_capabilities
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("El recibo de aprobación de R2 no coincide con el prompt y sus capacidades") from exc
    return prompt_path


def load_active_system_instructions() -> str:
    """Load the selected prompt; R1 is default and R2 requires a pinned owner receipt."""
    selected_version = os.environ.get("CHAT_PROMPT_VERSION", APPROVED_PROMPT_VERSION).strip().lower()
    if selected_version == R2_PROMPT_VERSION:
        return _load_r2_instructions()
    if selected_version != APPROVED_PROMPT_VERSION:
        raise RuntimeError("CHAT_PROMPT_VERSION no corresponde a un prompt disponible")
    base_prompt = _read_prompt(APPROVED_PROMPT_PATH)
    if prompt_sha256(base_prompt) != APPROVED_BASE_PROMPT_SHA256:
        raise RuntimeError("El prompt base del chat no coincide con el SHA-256 aprobado")
    effective_prompt = with_dashboard_period_policy(base_prompt)
    if prompt_sha256(effective_prompt) != APPROVED_EFFECTIVE_PROMPT_SHA256:
        raise RuntimeError("El prompt efectivo del chat no coincide con el SHA-256 evaluado")
    return effective_prompt


def load_system_instructions(path: Path = APPROVED_PROMPT_PATH) -> str:
    """Load the exact R1 approved source; retained for compatibility and tests."""
    base_prompt = _read_prompt(path)
    if prompt_sha256(base_prompt) != APPROVED_BASE_PROMPT_SHA256:
        raise RuntimeError("El prompt base del chat no coincide con el SHA-256 aprobado")
    effective_prompt = with_dashboard_period_policy(base_prompt)
    if prompt_sha256(effective_prompt) != APPROVED_EFFECTIVE_PROMPT_SHA256:
        raise RuntimeError("El prompt efectivo del chat no coincide con el SHA-256 evaluado")
    return effective_prompt


SYSTEM_INSTRUCTIONS = load_active_system_instructions()


def effective_prompt_sha256() -> str:
    """Return the hash of the exact validated prompt sent to the provider."""
    return prompt_sha256(load_active_system_instructions())


def effective_prompt_version() -> str:
    """Return the version name bound to the approved effective prompt hash."""
    digest = effective_prompt_sha256()
    if digest == APPROVED_EFFECTIVE_PROMPT_SHA256:
        return APPROVED_PROMPT_VERSION
    if digest == R2_PROMPT_SHA256:
        return R2_PROMPT_VERSION
    raise RuntimeError("La versión del prompt no coincide con un contrato aprobado")
