"""Private dispatch ledger; never calls sources, messaging, automations or publication.

Run as ``python -m scripts.source_update_coordinator``. Calendar, product planning,
bounded retries and the exclusive filesystem writer remain the existing ones.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from src.source_updates import calendar
from src.source_updates.catalog import ROOT, plan
from src.source_updates.collection import safe_workspace, writer
from src.source_updates.global_readiness import REQUIRED


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def holidays() -> dict:
    return load(ROOT / "config/source_update_holidays.json")


def persist(workspace: Path, state: dict) -> None:
    """Caller holds writer. A crash leaves the last complete state and a stale lock."""
    target = workspace / "state.json"
    staging = workspace / ".state.pending"
    body = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    descriptor = os.open(staging, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, target)
    if os.name == "posix":
        directory = os.open(workspace, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def install_events(state: dict, rounds: list[dict]) -> None:
    """Freeze grouping before dispatch, keeping original member dates for audit."""
    for event in calendar.combine(rounds):
        if not event["date"]:
            continue
        members = event.get("members", [event])
        keys = sorted(
            key
            for member in members
            for key, task in state["tasks"].items()
            if task["selected"] and (task["cadence"], task["period"]) == (member["kind"], member["period"])
        )
        event_id = digest({"date": event["date"], "task_keys": keys})
        state["events"][event_id] = {"date": event["date"], "members": members, "task_keys": keys}
        for key in keys:
            state["tasks"][key].update(event_id=event_id, due_date=event["date"])


def prepare(request: dict) -> dict:
    cutoff = calendar.local_time(request["as_of"])
    start = date.fromisoformat(request["start"] + "-01")
    count = request["months"]
    if type(count) is not int or not 1 <= count <= 12:
        raise ValueError("months must be an integer in 1..12")
    bank = holidays()
    rounds = []
    for offset in range(count):
        index = start.year * 12 + start.month - 1 + offset
        due = calendar.monthly(index // 12, index % 12 + 1, bank)
        if due <= cutoff.date():
            raise ValueError("Preparation only accepts future rounds; no historical replay")
        period = (due.replace(day=1) - timedelta(days=1)).strftime("%YM%m")
        rounds.append({"kind": "monthly", "date": due.isoformat(), "period": period})
    quarter = calendar.quarterly(request["quarter"], request.get("releases", []), request["as_of"], bank)
    if quarter["date"] and date.fromisoformat(quarter["date"]) <= cutoff.date():
        raise ValueError("Past quarterly round needs an explicit recovery decision")
    rounds.append({"kind": "quarterly", **quarter})
    tasks = {}
    for member in rounds:
        # Monthly product planning must use the dispatch month, not today's month.
        planned_at = f"{member['date']}T08:00:00-06:00" if member["date"] else request["as_of"]
        products = plan(
            member["kind"], planned_at, request["quarter"] if member["kind"] == "quarterly" else None
        )
        for product in products["calendar_tasks"]:
            if product["status"] == "not_due_this_round":
                continue
            cadence = product.get("target_cadence", product["cadence"])
            period = product.get("target_period", product.get("period"))
            selected = product["id"] in REQUIRED[cadence] or product["id"] == "editorial_news"
            key = f"{cadence}:{period}:{product['id']}"
            tasks[key] = {
                "cadence": cadence,
                "period": period,
                "product": product["id"],
                "selected": selected,
                "due_date": member["date"],
                "status": "planned",
                "reschedules": 0,
                "dispatches": [],
                "receipts": [],
                "certification": None,
                "publication_authorized": False,
            }
    state = {
        "version": 1,
        "request_sha256": digest(request),
        "request": request,
        "releases": request.get("releases", []),
        "prepared_as_of": request["as_of"],
        "timezone": "America/Mexico_City",
        "activation_authorized": False,
        "authorization_reference": None,
        "automation_id": None,
        "publication_authorized": False,
        "coordinator_id": "airlines-tracker-source-calendar",
        "automation_creation": None,
        "holiday_sha256": digest(bank),
        "monthly_rounds": rounds[:-1],
        "next_monthly": rounds[0],
        "next_quarterly": quarter,
        "tasks": tasks,
        "active_task": None,
        "active_tasks": {},
        "operations": {},
        "reschedules": {},
        "events": {},
    }
    install_events(state, rounds)
    return state


def trigger(state: dict, now: str) -> dict:
    """Declarative one-shot payload only. No native task is created or updated."""
    today = calendar.local_time(now).date()
    pending = [
        task
        for task in state["tasks"].values()
        if task["selected"] and task["status"] in {"planned", "retry_pending"} and task["due_date"]
    ]
    if not pending:
        return {"payload": None, "reason": "no_dated_pending_tasks"}
    due = min(task["due_date"] for task in pending)
    events = [event for event in state["events"].values() if event["date"] == due]
    members = [member for event in events for member in event["members"]]
    keys = sorted({key for event in events for key in event["task_keys"]})
    identity = {"date": due, "task_keys": keys}
    event_id = digest(identity)
    pending_keys = [
        key
        for key in keys
        if state["tasks"][key]["status"] in {"planned", "retry_pending"}
        and state["tasks"][key]["due_date"] == due
    ]
    result = {
        "event_id": event_id,
        "date": due,
        "members": members,
        "task_keys": keys,
        "pending_task_keys": pending_keys,
        "activation_authorized": state["activation_authorized"],
    }
    if state["active_task"] is not None or state.get("active_tasks"):
        return {**result, "payload": None, "reason": "active_writer_requires_reconciliation"}
    if date.fromisoformat(due) <= today:
        return {**result, "payload": None, "reason": "due_or_overdue_requires_reconciliation"}
    payload = {
        "title": "Calendario único Airlines Tracker",
        "prompt": (
            f"Procesa el evento {event_id}, claves pendientes {', '.join(pending_keys)}. "
            f"Coordinador airlines-tracker-source-calendar; estado canónico {state['workspace']}/state.json. "
            "Lee .agents/skills/airline-update-coordinator/SKILL.md y el estado privado canónico. "
            "Sigue esa skill: materializa el manifiesto con python -m scripts.source_update_dispatch "
            "y ejecuta jobs[].native_call mediante herramientas nativas de subagentes reales. "
            "Si la capacidad nativa o el estado no están disponibles, "
            "devuelve el bloqueo sin simular envíos. "
            "Comprueba autorización, ID único y bloqueo; registra intención antes de delegar. "
            "Reconcílialo por mensaje/turno/recibo antes de repetir un envío incierto. "
            "Reutiliza plan/calendar/retry, conserva resultados independientes y originales. "
            "Noticias pertenece al calendario único; ejecútala solo si figura en las claves del evento. "
            "Usa búsquedas nativas y navegador autorizado, "
            "con originales transferidos por Library. No crees otro monitor Viva. "
            "Aerocivil conserva sus supuestos operacionales documentados y confirmación oficial pendiente; "
            "comprueba datos, disponibilidad y recibos requeridos sin sustituir faltantes por supuestos. "
            "No publiques ni actives datos, noticias o tesis. Actualiza este mismo ID al próximo evento."
        ),
        "schedule": (
            f"BEGIN:VEVENT\nDTSTART;TZID=America/Mexico_City:{due.replace('-', '')}T080000\nEND:VEVENT"
        ),
        "timing_mode": "flexible_schedule",
        "default_timezone": "America/Mexico_City",
    }
    return {**result, "payload": payload}


def text_field(action: dict, field: str) -> str:
    value = action.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Nonempty {field} is required")
    return value


def owner_reference(action: dict) -> str:
    """Use an explicitly local lease when the host does not expose a native turn ID."""
    if action.get("owner_lease_id") is not None:
        lease = text_field(action, "owner_lease_id")
        if not lease.startswith("local_lease:"):
            raise ValueError("A local owner lease must be labelled local_lease:")
        return lease
    return text_field(action, "owner_turn_id")


def optional_identifier(action: dict, field: str) -> str | None:
    return None if action.get(field) is None else text_field(action, field)


def transition(state: dict, action: dict, workspace: Path) -> None:
    """Record observed actions, never perform them. Authorization is an operator assertion."""
    kind = action["action"]
    stamp = text_field(action, "at")
    calendar.local_time(stamp)
    active = state.setdefault("active_tasks", {})
    if state["active_task"] is not None and not active:
        previous = state["active_task"]
        active[previous] = state["tasks"][previous]["dispatches"][-1]["intent_id"]
    if any(state["tasks"][key]["dispatches"][-1]["intent_id"] != intent for key, intent in active.items()):
        raise ValueError("Active worker references differ; reconcile before dispatch")
    unresolved = {
        key
        for key, entry in state["tasks"].items()
        if entry["status"] in {"running", "blocked_for_decision"}
        and entry["dispatches"]
        and entry["dispatches"][-1]["delivery"] in {"uncertain", "acknowledged"}
    }
    if set(active) != unresolved or (active and state["active_task"] not in active):
        raise ValueError("Unresolved workers differ from the persistent coordinator lease")
    if kind == "record_conditional_authorization":
        from src.source_updates.aerocivil_operational import POLICY

        if state["automation_id"] is not None or state["automation_creation"] is not None or active:
            raise ValueError("Reconcile the existing automation before changing preparation conditions")
        if action.get("operational_policy_id") != POLICY:
            raise ValueError("Use the exact documented operational policy")
        state["conditional_activation_authorization"] = {
            "authorization_reference": text_field(action, "authorization_reference"),
            "status": "authorized_after_verified_viva_required_data_and_native_dispatch",
            "operational_policy_id": POLICY,
            "recorded_at": stamp,
            "scope": "single_calendar_candidate_updates_no_automatic_publication",
        }
        return
    if kind == "refresh_reports":
        if state["active_task"] is not None or active:
            raise ValueError("Cannot change dates while a task is running")
        releases = list(state["releases"])
        for release in action["releases"]:
            if not any(digest(previous) == digest(release) for previous in releases):
                releases.append(release)
        quarter = calendar.quarterly(state["next_quarterly"]["period"], releases, stamp, holidays())
        if state["next_quarterly"]["date"] is not None:
            raise ValueError("A dated quarterly round requires explicit reconciliation, not redating")
        state["next_quarterly"] = quarter
        state["releases"] = releases
        for task in state["tasks"].values():
            if task["cadence"] == "quarterly" and task["status"] == "planned":
                task["due_date"] = quarter["date"]
        if quarter["date"]:
            untouched = [
                member
                for member in state["monthly_rounds"]
                if all(
                    not task["dispatches"]
                    for task in state["tasks"].values()
                    if (task["cadence"], task["period"]) == ("monthly", member["period"])
                )
            ]
            for event_id, event in list(state["events"].items()):
                if any(member in untouched for member in event["members"]):
                    del state["events"][event_id]
            install_events(state, [*untouched, {"kind": "quarterly", **quarter}])
        return
    if kind == "activation_intent":
        if action.get("activation_authorized") is not True:
            raise ValueError("Explicit activation authorization is required")
        reference = text_field(action, "authorization_reference")
        if state.get("conditional_activation_authorization"):
            expected = {
                "viva_financials_verified",
                "required_round_data_verified",
                "single_coordinator_reconciled",
                "native_dispatch_verified",
            }
            verified = action.get("verified_conditions")
            if (
                not isinstance(verified, dict)
                or set(verified) != expected
                or any(value is not True for value in verified.values())
            ):
                raise ValueError(
                    "Conditional activation needs Viva, required data, native dispatch and one coordinator"
                )
            conditions_reference = text_field(action, "conditions_verified_reference")
        else:
            conditions_reference = None
        if state["automation_id"] is not None or state["automation_creation"] is not None:
            raise ValueError("Existing or uncertain automation; reconcile before another create")
        state.update(activation_authorized=True, authorization_reference=reference)
        state["automation_creation"] = {
            "intent_id": action["operation_id"],
            "at": stamp,
            "owner_turn_id": optional_identifier(action, "owner_turn_id"),
            "owner_lease_id": owner_reference(action),
            "native_owner_turn_id": optional_identifier(action, "native_owner_turn_id")
            or optional_identifier(action, "owner_turn_id"),
            "outcome": "uncertain",
            "conditions_verified_reference": conditions_reference,
        }
        return
    if kind in {"bind_authorized_automation", "activation_not_created"}:
        creation = state["automation_creation"]
        if (
            state["activation_authorized"] is not True
            or not creation
            or creation["outcome"] != "uncertain"
            or action.get("intent_id") != creation["intent_id"]
        ):
            raise ValueError("First reconcile the exact authorized creation intent")
        reference = text_field(action, "reconciliation_reference")
        if kind == "activation_not_created":
            if action.get("confirmed_not_created") is not True:
                raise ValueError("Uncertain creation must not be repeated")
            state["automation_creation"] = None
        else:
            state["automation_id"] = text_field(action, "automation_id")
            creation.update(outcome="bound", reconciliation_reference=reference)
        return
    if state["activation_authorized"] is not True or not state["automation_id"]:
        raise ValueError("Calendar activation is not authorized or bound")
    if action.get("automation_id") != state["automation_id"]:
        raise ValueError("Wrong coordinator automation ID")
    key = text_field(action, "task_key")
    task = state["tasks"][key]
    if kind == "dispatch_intent":
        owner = owner_reference(action)
        isolated = action.get("execution_mode") == "isolated_skill_worker"
        if action.get("execution_mode") not in {None, "serial_writer", "isolated_skill_worker"}:
            raise ValueError("Unknown worker execution mode")
        if not isolated and action.get("worker_workspace") is not None:
            raise ValueError("Worker workspace requires explicit isolated skill execution")
        for prior_key in active:
            prior = state["tasks"][prior_key]["dispatches"][-1]
            if (
                not isolated
                or prior.get("execution_mode") != "isolated_skill_worker"
                or prior.get("owner_lease_id", prior.get("owner_turn_id")) != owner
            ):
                raise ValueError("Another task owns the single writer; reconcile it first")
        worker = None
        if isolated:
            worker = safe_workspace(Path(text_field(action, "worker_workspace")))
            prior_workspaces = [
                workspace,
                *[
                    Path(dispatch["worker_workspace"])
                    for old_task in state["tasks"].values()
                    for dispatch in old_task["dispatches"]
                    if dispatch.get("worker_workspace")
                ],
            ]
            if any(
                worker == prior or worker.is_relative_to(prior) or prior.is_relative_to(worker)
                for prior in prior_workspaces
            ):
                raise ValueError(
                    "Worker workspace overlaps the coordinator or a reserved historical candidate"
                )
            if worker.exists() and any(worker.iterdir()):
                raise ValueError("A new isolated worker needs an empty candidate workspace")
        if not task["selected"] or task["status"] not in {"planned", "retry_pending"} or not task["due_date"]:
            raise ValueError("Task cannot be dispatched")
        if calendar.local_time(stamp).date() < date.fromisoformat(task["due_date"]):
            raise ValueError("Task is not due")
        event = trigger(state, stamp)
        if (
            key not in event.get("pending_task_keys", [])
            or action.get("event_id") != event.get("event_id")
            or date.fromisoformat(event["date"]) > calendar.local_time(stamp).date()
        ):
            raise ValueError("Dispatch must match the next event date and members")
        task["dispatches"].append(
            {
                "intent_id": action["operation_id"],
                "owner_turn_id": optional_identifier(action, "owner_turn_id"),
                "owner_lease_id": owner,
                "native_owner_turn_id": optional_identifier(action, "native_owner_turn_id")
                or optional_identifier(action, "owner_turn_id"),
                "at": stamp,
                "delivery": "uncertain",
                "message_id": None,
                "worker_turn_id": None,
                "native_task_name": None,
                "execution_mode": "isolated_skill_worker" if isolated else "serial_writer",
                "worker_workspace": str(worker) if worker else None,
            }
        )
        task["status"] = "running"
        active[key] = action["operation_id"]
        state["active_task"] = next(iter(active))
    elif kind in {"acknowledge", "complete", "retry", "uncertain"}:
        if task["status"] not in {"running", "blocked_for_decision"} or key not in active:
            raise ValueError("Only the active running task can be reconciled")
        dispatch = task["dispatches"][-1]
        if owner_reference(action) != dispatch.get("owner_lease_id", dispatch.get("owner_turn_id")):
            raise ValueError("Wrong writer owner; handover needs a reconciled record")
        if kind == "acknowledge":
            if dispatch["delivery"] != "uncertain":
                raise ValueError("Delivery is already acknowledged")
            if action.get("native_task_name"):
                native_name = text_field(action, "native_task_name")
                if any(
                    prior is not dispatch and prior.get("native_task_name") == native_name
                    for entry in state["tasks"].values()
                    for prior in entry["dispatches"]
                ):
                    raise ValueError("Native worker already belongs to another dispatch intention")
                response_hash = text_field(action, "native_response_sha256")
                if len(response_hash) != 64 or any(char not in "0123456789abcdef" for char in response_hash):
                    raise ValueError("Native tool response needs its exact SHA-256")
                dispatch.update(
                    delivery="acknowledged",
                    native_task_name=native_name,
                    native_response_sha256=response_hash,
                    message_id=optional_identifier(action, "message_id"),
                    worker_turn_id=optional_identifier(action, "worker_turn_id"),
                )
            else:
                dispatch.update(
                    delivery="acknowledged",
                    message_id=text_field(action, "message_id"),
                    worker_turn_id=text_field(action, "worker_turn_id"),
                )
            return
        if kind == "complete":
            # This is an operational receipt, never a certification of financial numbers.
            path = (workspace / text_field(action, "receipt_file")).resolve()
            if not path.is_relative_to(workspace) or not path.is_file() or path.is_symlink():
                raise ValueError("Receipt must be a retained file inside the private workspace")
            receipt_bytes = path.read_bytes()
            actual = hashlib.sha256(receipt_bytes).hexdigest()
            if actual != action.get("receipt_sha256"):
                raise ValueError("Receipt hash differs")
            receipt = json.loads(receipt_bytes)
            if receipt.get("task_key") != key or receipt.get("intent_id") != dispatch["intent_id"]:
                raise ValueError("Receipt belongs to a different task or dispatch")
            task["receipts"].append(
                {
                    "file": path.relative_to(workspace).as_posix(),
                    "sha256": actual,
                    "receipt_id": text_field(receipt, "receipt_id"),
                    "recorded_at": stamp,
                }
            )
            task["status"] = "completed"
            dispatch["delivery"] = "reconciled_completed"
        elif kind == "retry":
            if action.get("confirmed_stopped_or_not_sent") is not True:
                raise ValueError("Uncertain delivery cannot be retried")
            dispatch["reconciliation_reference"] = text_field(action, "reconciliation_reference")
            batch = f"{task['cadence']}:{task['period']}"
            proposed = calendar.retry_date(
                today=calendar.local_time(stamp).date(),
                attempts=state["reschedules"].get(batch, 0),
                reason=action["reason"],
                holidays=holidays(),
                announced_date=date.fromisoformat(action["announced_date"])
                if action.get("announced_date")
                else None,
            )
            task.update(
                status="retry_pending" if proposed["date"] else "blocked_for_decision",
                due_date=proposed["date"],
                reschedules=proposed["reschedules"],
            )
            state["reschedules"][batch] = proposed["reschedules"]
            if proposed["date"]:
                event_id = digest({"date": proposed["date"], "task_keys": [key]})
                state["events"][event_id] = {
                    "date": proposed["date"],
                    "task_keys": [key],
                    "members": [
                        {"kind": task["cadence"], "period": task["period"], "date": proposed["date"]}
                    ],
                }
                task["event_id"] = event_id
            dispatch["delivery"] = "reconciled_stopped_or_not_sent"
        else:
            dispatch["reconciliation_reference"] = text_field(action, "reconciliation_reference")
            task["status"] = "blocked_for_decision"
            return  # An unacknowledged worker might still be writing. Keep the persisted owner.
        del active[key]
        state["active_task"] = next(iter(active), None)
    else:
        raise ValueError("Unknown coordinator transition")


def run(workspace: Path, *, request: dict | None = None, action: dict | None = None, now: str) -> dict:
    workspace = safe_workspace(workspace)
    if request is not None or action is not None:
        with writer(workspace):
            target = workspace / "state.json"
            if request is not None:
                if target.exists():
                    state = load(target)
                    if state["request_sha256"] != digest(request):
                        raise ValueError("Existing ledger cannot be replaced or counters reset")
                else:
                    state = prepare(request)
                    state["workspace"] = str(workspace)
                    persist(workspace, state)
            else:
                state = load(target)
                if state["workspace"] != str(workspace):
                    raise ValueError("Ledger was moved or copied; reconcile the canonical coordinator")
                if state["holiday_sha256"] != digest(holidays()):
                    raise ValueError("Verified holiday inputs changed; reconcile before recording")
                if calendar.local_time(action["at"]) > calendar.local_time(now):
                    raise ValueError("Cannot record a future action")
                operation = text_field(action, "operation_id")
                previous = state["operations"].get(operation)
                if previous:
                    if previous["sha256"] != digest(action):
                        raise ValueError("Operation ID reused with different arguments")
                else:
                    if calendar.local_time(action["at"]) < calendar.local_time(
                        state.get("last_recorded_at", state["prepared_as_of"])
                    ):
                        raise ValueError("Action predates the last recorded transition")
                    transition(state, action, workspace)
                    state["operations"][operation] = {"sha256": digest(action), "action": action}
                    state["last_recorded_at"] = action["at"]
                    persist(workspace, state)
    else:
        state = load(workspace / "state.json")
    if state["workspace"] != str(workspace):
        raise ValueError("Ledger was moved or copied; reconcile the canonical coordinator")
    if state["holiday_sha256"] != digest(holidays()):
        raise ValueError("Verified holiday inputs changed; reconcile before scheduling")
    return {
        "state": state,
        "next_trigger": trigger(state, now),
        "network_requests": 0,
        "scheduled_executions": 0,
        "publication_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--prepare", type=Path, help="Write private plan once; never activate")
    operation.add_argument("--record", type=Path, help="Record an observed action; never send it")
    parser.add_argument("--now", default=datetime.now(UTC).isoformat())
    args = parser.parse_args()
    try:
        output = run(
            args.workspace,
            request=load(args.prepare) if args.prepare else None,
            action=load(args.record) if args.record else None,
            now=args.now,
        )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, OSError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "scheduled_executions": 0}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
