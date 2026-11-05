"""Explicit consumers on a NEW private checkpoint; never migrate an active ledger."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

PROMPT_DELTA = (
    " Mapa oficial seleccionado explícitamente en esta continuación: afac_margins CONDITIONAL=true "
    "y consumer=official_routes. Conserva ID, horario, cadencia y vigencia existentes; no crees otro job. "
    "Adquiere AFAC SASE ciudad-ciudad y resumen por empresa de la misma edición; BTS FJE observado "
    "para los tres grupos, con revisiones de años retenidos y mes máximo real. No sustituyas SASE "
    "por DATATUR ni programación. Tras readiness, prepara/reproduce el paquete completo con ambos "
    "originales y observa el resultado en el outbox nuevo; conserva referencias del checkpoint anterior. "
    "source_dependency_assessment y candidate no acreditan publicación. official_routes source_data "
    "requiere autoridad exacta, gate y QA servida; periodo nuevo o cobertura distinta requiere aprobación "
    "normal. No-change debe reproducir official-routes.json completo y su baseline, nunca el mapa legacy."
)


def prompt_delta(state):
    return PROMPT_DELTA if "official_routes" in state.get("consumers", []) else ""


def preparation_options(request: dict) -> tuple[set[str], dict]:
    conditional = request.get("conditional_products", [])
    consumers = request.get("consumers", [])
    for values, allowed in ((conditional, {"afac_margins"}), (consumers, {"official_routes"})):
        if (
            not isinstance(values, list)
            or any(not isinstance(v, str) or v not in allowed for v in values)
            or len(values) != len(set(values))
        ):
            raise ValueError("Use explicit reviewed conditional_products/consumers without duplicates")
    if not conditional and not consumers and "continuation" not in request:
        return set(), {}
    run_id = request.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", run_id):
        raise ValueError("New consumer selection requires a new explicit run_id")
    if consumers and "afac_margins" not in conditional:
        raise ValueError("Official routes require explicitly selected conditional afac_margins")
    extras = {"run_id": run_id, "consumers": consumers, "conditional_products": conditional}
    continuation = request.get("continuation")
    if consumers and continuation is None:
        raise ValueError(
            "Continue the existing calendar with an exact previous_state reference; never create another"
        )
    if continuation is not None:
        if not isinstance(continuation, dict) or set(continuation) != {"previous_state"}:
            raise ValueError("Continuation requires only an exact previous_state reference")
        ref = continuation["previous_state"]
        previous = read_previous(ref)
        if set(previous.get("consumers", [])) - set(consumers):
            raise ValueError("Continuation cannot remove an existing selected consumer")
        if previous.get("run_id") == run_id:
            raise ValueError("Continuation requires a NEW run_id; retain the previous checkpoint")
        extras["continuation"] = {
            "previous_state": ref,
            "previous_run_id": previous.get("run_id", previous["request_sha256"]),
            "existing_automation_id": previous["automation_id"],
        }
    return set(conditional), extras


def read_previous(ref: dict) -> dict:
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Previous checkpoint requires path and SHA256")
    path = Path(ref["path"])
    if (
        not path.is_absolute()
        or path.resolve() != path
        or not path.is_file()
        or any(p.is_symlink() for p in (path, *path.parents))
    ):
        raise ValueError("Previous checkpoint must remain at its physical canonical path")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("Previous checkpoint changed; reconcile before continuing")
    previous = json.loads(raw)
    if (
        Path(previous["workspace"]) / "state.json" != path
        or previous.get("coordinator_id") != "airlines-tracker-source-calendar"
        or previous.get("activation_authorized") is not True
        or not previous.get("automation_id")
        or previous.get("active_task") is not None
        or previous.get("active_tasks")
        or any(
            task["selected"] and task["status"] in {"running", "retry_pending", "blocked_for_decision"}
            for task in previous["tasks"].values()
        )
    ):
        raise ValueError("Only a reconciled bound existing calendar can have a versioned continuation")
    return previous


def require_existing_id(state: dict, automation_id: str) -> None:
    continuation = state.get("continuation")
    if continuation:
        previous = read_previous(continuation["previous_state"])
        if (
            automation_id != continuation["existing_automation_id"]
            or automation_id != previous["automation_id"]
        ):
            raise ValueError("Continuation must reuse the existing automation ID, never create a replacement")


def finalize_preparation(state: dict, options: dict, cutoff) -> dict:
    state.update(options)
    if state.get("continuation"):
        previous = read_previous(state["continuation"]["previous_state"])
        future_rounds = [
            r for r in previous["monthly_rounds"] if date.fromisoformat(r["date"]) > cutoff.date()
        ]
        if state["monthly_rounds"] != future_rounds:
            raise ValueError(
                "Continuation must preserve the complete future monthly calendar and its horizon"
            )
        quarter = state["next_quarterly"]
        if quarter["date"] and date.fromisoformat(quarter["date"]) <= cutoff.date():
            old_quarter = [
                t
                for t in previous["tasks"].values()
                if t["selected"] and (t["cadence"], t["period"]) == ("quarterly", state["request"]["quarter"])
            ]
            if (
                not old_quarter
                or previous["request"]["quarter"] != state["request"]["quarter"]
                or previous["next_quarterly"]["date"] != quarter["date"]
                or any(
                    t["status"] != "completed"
                    or not t["due_date"]
                    or date.fromisoformat(t["due_date"]) > cutoff.date()
                    for t in old_quarter
                )
            ):
                raise ValueError("A past quarter must be the same original fully completed round")
        for key, task in previous["tasks"].items():
            if (
                key in state["tasks"]
                and task["selected"]
                and task["status"] == "completed"
                and task["due_date"]
                and date.fromisoformat(task["due_date"]) <= cutoff.date()
            ):
                del state["tasks"][key]
                state["continuation"].setdefault("retained_completed_task_keys", []).append(key)
                continue
            if (
                task["selected"]
                and task["status"] != "completed"
                and (key not in state["tasks"] or not state["tasks"][key]["selected"])
            ):
                raise ValueError("Continuation cannot omit an existing selected pending task")
            if (
                task["selected"]
                and task["status"] in {"planned", "retry_pending"}
                and task["due_date"]
                and date.fromisoformat(task["due_date"]) <= cutoff.date()
            ):
                raise ValueError("Reconcile overdue tasks in the previous checkpoint before continuing")
            if key in state["tasks"] and state["tasks"][key]["due_date"] != task["due_date"]:
                raise ValueError("Continuation cannot change an existing task date or cadence")
            if (
                key in state["tasks"]
                and task["selected"]
                and (
                    task["status"] != "planned"
                    or task["reschedules"]
                    or task["dispatches"]
                    or task["receipts"]
                )
            ):
                raise ValueError(
                    "Continue an attempted task in its original checkpoint; never reset its history"
                )
        if any(
            t["selected"] and t["due_date"] and date.fromisoformat(t["due_date"]) <= cutoff.date()
            for t in state["tasks"].values()
        ):
            raise ValueError("Continuation cannot add an uncompleted historical task")
        from scripts.source_update_coordinator import install_events

        state["events"] = {}
        install_events(state, [*state["monthly_rounds"], {"kind": "quarterly", **state["next_quarterly"]}])
        state["events"] = {key: event for key, event in state["events"].items() if event["task_keys"]}
    return state


def bind_existing(state: dict, action: dict) -> None:
    if (
        not state.get("continuation")
        or state["automation_id"] is not None
        or state["automation_creation"] is not None
        or state["activation_authorized"]
    ):
        raise ValueError("Bind an existing automation only on its new inactive continuation checkpoint")
    for field in ("automation_id", "authorization_reference", "reconciliation_reference"):
        if not isinstance(action.get(field), str) or not action[field].strip():
            raise ValueError(f"Existing automation continuation requires {field}")
    require_existing_id(state, action["automation_id"])
    state.update(
        automation_id=action["automation_id"],
        activation_authorized=True,
        authorization_reference=action["authorization_reference"],
        automation_binding={
            "kind": "existing_automation_continuation",
            "reconciliation_reference": action["reconciliation_reference"],
        },
    )
