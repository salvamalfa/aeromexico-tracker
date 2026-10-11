"""Approved runtime prompt and its versioned dashboard-period policy."""

from __future__ import annotations

import hashlib
from pathlib import Path

APPROVED_BASE_PROMPT_SHA256 = "33b8f7a0900869812d98bba57daa2ce3ea2f6b5c02a86a7eb3b8e830c7f7694b"
APPROVED_EFFECTIVE_PROMPT_SHA256 = "439d24fd58a7b3c6c721e15a390824c1b477f52b2b568881dd68bd3655db22a5"
APPROVED_PROMPT_PATH = Path(__file__).resolve().parents[3] / "config/chat/system_prompt.txt"
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


def load_system_instructions(path: Path = APPROVED_PROMPT_PATH) -> str:
    """Fail closed if the versioned source or its evaluated derivation drifts."""
    try:
        base_prompt = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError("No se pudo cargar el prompt aprobado del chat") from exc
    if prompt_sha256(base_prompt) != APPROVED_BASE_PROMPT_SHA256:
        raise RuntimeError("El prompt base del chat no coincide con el SHA-256 aprobado")
    effective_prompt = with_dashboard_period_policy(base_prompt)
    if prompt_sha256(effective_prompt) != APPROVED_EFFECTIVE_PROMPT_SHA256:
        raise RuntimeError("El prompt efectivo del chat no coincide con el SHA-256 evaluado")
    return effective_prompt


SYSTEM_INSTRUCTIONS = load_system_instructions()


def effective_prompt_sha256() -> str:
    """Return the hash of the exact validated prompt sent to the provider."""
    return prompt_sha256(SYSTEM_INSTRUCTIONS)
