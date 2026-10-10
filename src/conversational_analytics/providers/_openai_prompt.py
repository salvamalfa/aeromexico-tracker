"""Versioned prompt derivation for current dashboard-period selection."""

from __future__ import annotations

import hashlib

PERIOD_SELECTION_POLICY_VERSION = "dashboard-period-priority-v2"
PERIOD_SELECTION_POLICY = f"""\
<prioridad_de_periodo version=\"{PERIOD_SELECTION_POLICY_VERSION}\">
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


def with_dashboard_period_policy(base_prompt: str) -> str:
    """Derive the prompt used for a provider session without editing its source.

    The approved F2.1 text remains intact as the prefix. This versioned policy
    is appended for the next pilot, and its full result is what session hashes
    identify.
    """
    if not isinstance(base_prompt, str) or not base_prompt.strip():
        raise ValueError("Las instrucciones del proveedor no pueden estar vacías")
    if PERIOD_SELECTION_POLICY in base_prompt:
        return base_prompt
    return f"{base_prompt.rstrip()}\n\n{PERIOD_SELECTION_POLICY}"


# Backward-compatible internal name while call sites move to the shared API.
effective_instructions = with_dashboard_period_policy


def prompt_sha256(prompt: str) -> str:
    """Hash the exact UTF-8 prompt text sent to the provider."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
