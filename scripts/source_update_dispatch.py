"""Materialize source/skill handoffs for the single calendar without dispatching them.\n
The coordinating *agent* invokes the returned native tool envelopes. Python does
not invoke agent tools, acquire sources, install schedules, or claim execution.\n"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from scripts import source_update_coordinator as coordinator
from src.source_updates.calendar import local_time, report_day
from src.source_updates.catalog import FAMILIES, ROOT, load_catalog, product_map
from src.source_updates.checks import period_end
from src.source_updates.collection import safe_workspace
from src.source_updates.recipes import acquisition_config, resolve_entry

SKILLS = {
    "corporate": "airline-update-corporate",
    "traffic": "airline-update-traffic",
    "airports": "airline-update-airports",
    "macro_market": "airline-update-macro-market",
    "routes": "airline-update-routes",
    "context": "airline-update-context",
    "news": "airline-update-news",
    "internal": "airline-update-internal",
}
NATIVE_TOOL = "collaboration.spawn_agent"
FINANCIALS = {"am_financials": "AEROMEXICO", "volaris_sec": "VOLARIS", "viva_financials": "VIVA_AEROBUS"}


def skill(family: str) -> dict:
    relative = Path(".agents/skills") / SKILLS[family] / "SKILL.md"
    path = ROOT / relative
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Required source skill is missing: {relative.as_posix()}")
    return {
        "name": SKILLS[family],
        "path": relative.as_posix(),
        "absolute_path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def source_map() -> dict:
    """All catalogue products, including unselected ones; no URL/source requests."""
    if set(SKILLS) != set(FAMILIES):
        raise ValueError("Skill families differ from the source catalogue")
    sources = load_catalog()
    acquisition = acquisition_config()["products"]
    mapped = []
    for key, product in sorted(product_map().items()):
        source = sources[product["source_key"]]
        recipe = acquisition[key]
        entry_url = resolve_entry(recipe["entry_ref"])
        discovery_url = resolve_entry(recipe["discovery_ref"]) if recipe.get("discovery_ref") else entry_url
        mapped.append(
            {
                "product": key,
                "source_key": product["source_key"],
                "source_name": source["display_name"],
                "family": product["family"],
                "skill": skill(product["family"]),
                "cadence": product["cadence"],
                "provider_publication_frequency": source["update_frequency"],
                "official_publication_date": None,
                "publication_trigger": (
                    "Confirmar documento financiero real del trimestre; aviso inmediato independiente y "
                    "preparación acotada autorizada. El lote trimestral se fecha con los tres reportes."
                    if key in FINANCIALS
                    else (
                        "Descubrir novedades/revisiones en la ronda consolidada; "
                        "no instalar sondeo por publicación."
                    )
                ),
                "source_catalogue_discovery_page": source["official_page_url"],
                "acquisition_entry_url": entry_url,
                "discovery_page": discovery_url,
                "acquisition_reference": "config/source_update_acquisition.json",
                "entry_reference": recipe["entry_ref"],
                "procedure": recipe["procedure"],
                "acquisition_state": recipe["state"],
                "limitation": product["limitation"],
                "handoff_eligible": product["cadence"] != "never"
                and source["is_active"]
                and recipe["state"] != "disabled",
                "parser_step_from_catalogue": product["parser_step"],
            }
        )
    mapped.append(
        {
            "product": "editorial_news",
            "source_key": "native_editorial_review",
            "source_name": "Búsqueda nativa y lectura de editor/comunicado",
            "family": "news",
            "skill": skill("news"),
            "cadence": "monthly",
            "provider_publication_frequency": "Por evento",
            "official_publication_date": None,
            "publication_trigger": "Revisión editorial del mes objetivo en la misma ronda mensual de datos.",
            "discovery_page": None,
            "source_catalogue_discovery_page": None,
            "acquisition_entry_url": None,
            "acquisition_reference": "src/source_updates/editorial_news.py",
            "entry_reference": "native_search_and_publisher_reading",
            "procedure": (
                "Aplicar la skill de Noticias y su contrato editorial; el CLI verifica evidencia nativa real."
            ),
            "acquisition_state": "native_editorial_review_required",
            "limitation": (
                "Sin cuota fija ni exhaustividad; RSS/GDELT opcionales; no guardar artículos completos."
            ),
            "handoff_eligible": True,
            "parser_step_from_catalogue": None,
        }
    )
    return {
        "version": 1,
        "catalogue_sources": len(sources),
        "families": {k: skill(k) for k in SKILLS},
        "products": mapped,
        "network_requests": 0,
        "writes": [],
    }


def validate_task(key: str, task: dict, mapped: dict, as_of: str, execution: bool) -> None:
    cadence, period, product = key.split(":")
    if (cadence, period, product) != (task.get("cadence"), task.get("period"), task.get("product")):
        raise ValueError("Task key differs from its product/cadence/period")
    if cadence not in {"monthly", "quarterly"} or product not in mapped:
        raise ValueError("Unknown source task or cadence")
    definition = mapped[product]
    if not definition["handoff_eligible"] or definition["cadence"] not in {cadence, "both"}:
        raise ValueError("Product is not eligible for the selected skill handoff/cadence")
    pattern = r"\d{4}M(?:0[1-9]|1[0-2])" if cadence == "monthly" else r"\d{4}Q[1-4]"
    if not re.fullmatch(pattern, period):
        raise ValueError("Task needs its explicit native calendar period")
    if task.get("selected") is not True or task.get("status") not in {"planned", "retry_pending"}:
        raise ValueError("Only selected pending tasks may receive a handoff")
    count = task.get("reschedules")
    if type(count) is not int or not 0 <= count <= 2 or task["status"] == "retry_pending" and count == 0:
        raise ValueError("Preserve the bounded reschedule counter for this task")
    dispatches = task.get("dispatches", [])
    if dispatches and dispatches[-1].get("delivery") != "reconciled_stopped_or_not_sent":
        raise ValueError("Reconcile the existing dispatch before preparing another send")
    if execution and period_end(period) >= local_time(as_of).date():
        raise ValueError("Execution cannot use a period which has not closed")


def worker_message(job: dict, state: dict | None, as_of: str, rehearsal: bool) -> str:
    mode = (
        "ENSAYO REAL DE DELEGACIÓN: solo leer la skill y ejecutar las vistas previas/ayuda indicadas. "
        "No red, búsqueda, captura, transformaciones, datos ni publicación. "
        "No afirmar que el periodo está verificado."
        if rehearsal
        else "EJECUCIÓN CANDIDATA AUTORIZADA POR EL COORDINADOR: adquirir y validar "
        "solo el producto/periodo indicado "
        "según el alcance autorizado; ningún resultado queda aprobado para publicación."
    )
    commands = "\n".join(" ".join(command) for command in job["preflight_commands"])
    identity = (
        f"Evento {job['event_id']}"
        if job["is_scheduled_event"]
        else "Ensayo explícito no programado; ninguna fecha calendario se ha creado"
    )
    ledger = (
        f"Estado canónico: {state['workspace']}/state.json; no lo modifiques."
        if state
        else "Este ensayo no tiene ledger de ejecución; no crees uno ni actives nada."
    )
    return (
        f"{mode}\n{identity}; tarea {job['task_key']}; corte declarado {as_of}. Responsable lógico "
        f"{job['logical_agent_name']}. Lee AGENTS.md, .agents/skills/source-updates-common.md y la skill "
        f"exacta {job['skill']['absolute_path']} (SHA {job['skill']['sha256']}). Verifica el SHA de la skill "
        "antes de operar; si cambió, devuelve el bloqueo. La skill es un procedimiento que debes leer y "
        f"ejecutar mediante herramientas; no es un programa.\nProducto {job['product']}, fuente "
        f"{job['source_key']}, cadencia {job['cadence']}, periodo solicitado {job['period']}. Trabaja desde "
        f"{ROOT}; escribe solamente en {job['workspace']}. No cambies código ni archivos compartidos, no "
        f"hagas commits o push. {ledger}\nEl coordinador aplica .agents/skills/airline-update-coordinator/"
        "SKILL.md para ejecutar los envelopes; el CLI solo los materializa. Tú ejecutas únicamente la skill "
        f"de fuente indicada.\nVistas previas reales a ejecutar:\n{commands}\nUsa el intérprete absoluto "
        "incluido en argv[0], el mismo que compiló este manifiesto. No lo sustituyas por python del PATH ni "
        "combines argv[0] con otro executable. Conserva cualquier fallo previo y su argv como evidencia "
        "antes de corregir el entorno.\nSi el mes solicitado aún no cerró o el plan devuelve otro periodo, "
        "registra esa diferencia y mantén pendiente el producto; una vista previa no verifica datos futuros. "
        "En ejecución, revisa plan y recipe del producto; selecciona documentos primarios reales, muestra "
        "collect/retención --dry-run y usa solo el certificador dedicado que corresponda. No invoques un "
        "rebuild universal ni supongas que todo producto tiene el mismo build.\nCada skill produce su "
        "candidato Bronze/Silver/Gold y linaje cuando su adaptador lo admite; las rutas son destinos de "
        "candidato, no afirmación de que sus capas existan. Conserva selección, originales y sidecars en "
        "Bronze, intermedios en Silver, salidas/linaje en Gold, evidencia y recibos en las rutas del job. "
        "Noticias conserva evidencia editorial nativa y su candidato propio; no inventes capas tabulares o "
        "bytes HTTP para artículos leídos.\nSi falla la adquisición programática durante ejecución "
        "autorizada, verifica capacidades reales y usa navegador nativo cloud/local autorizado y navegación "
        "oficial normal. Si no está disponible, devuelve handoff al coordinador con URL, producto, periodo y "
        "recibo del fallo. Transfiere originales mediante Library y coteja identidad/bytes/SHA en el "
        "consumidor. Preserva URL, método, fecha y hash originales; importación no es captura nueva. SEC/"
        "manual/Aena y reconstrucciones conservan sus contratos específicos; no eludas 403, autenticación, "
        "CAPTCHA, TLS o denegaciones.\nSin API pagada, credenciales nuevas, backfill total, horarios diarios/"
        "semanales o segundo calendario. No dupliques el monitor de Viva. Reconcilia responsables y "
        "candidatos ya existentes antes de adquirir. Si detectas un financiero real, separa detección, "
        "confirmación primaria, aviso al coordinador e incorporación; no inventes fecha oficial ni cambies "
        "el disparo consolidado. RSS/GDELT siguen opcionales. Los supuestos Aerocivil no son confirmación "
        "oficial ni sustituyen datos ausentes. No actives datos, noticias, evidencias o tesis; no publiques "
        "nada.\nDevuelve tu resultado JSON intacto en la ruta del job con task_key, event_id, mode, skill_"
        "path, skill_sha256, comandos realmente ejecutados, resultados/errores, requested_period, observed_"
        "plan_periods, capas realmente producidas (o vacías), hashes y recibos nativos, y bloqueo/fallback "
        "pendiente. En ensayo declara data_verified=false. No inventes intent_id, recibos de proveedor o "
        "agent_id. El coordinador conserva tus bytes y construye un wrapper local ligado a su intención real,"
        " sin reescribir tu resultado ni los originales. El coordinador obtiene el ID de la herramienta "
        "nativa y registra acuse. Él reúne resultados independientes y verifica readiness/global y "
        "dependencias; la consolidación y el estado común tienen un solo escritor."
    )


def confirmed_publications(state: dict, product: str, period: str, as_of: str) -> list[dict]:
    """Copy prior confirmed release records; this never confirms a new publication."""
    entity = FINANCIALS.get(product)
    if entity is None:
        return []
    return [
        {
            "published_on": report_day(release, as_of).isoformat(),
            "published_at": release.get("published_at"),
            "publication_precision": release.get("publication_precision", "timestamp"),
            "document_url": release.get("document_url"),
            "source_sha256": release.get("source_sha256"),
            "basis": "confirmed_coordinator_record_not_new_source_verification",
        }
        for release in state.get("releases", [])
        if release.get("entity") == entity
        and release.get("period") == period
        and release.get("kind") == "financial_report"
        and release.get("confirmed") is True
    ]


def make_job(
    task: dict,
    key: str,
    definition: dict,
    root: Path,
    run_id: str,
    as_of: str,
    *,
    state: dict | None = None,
    event_id: str | None = None,
    event_date: str | None = None,
    execution_handoff: bool = False,
) -> dict:
    cutoff = local_time(as_of)
    logical = f"source_{task['product']}_{task['cadence']}_{task['period'].lower()}_{run_id[:10]}"
    folder = root / logical / ("candidate" if execution_handoff else "rehearsal")
    plan_command = [
        sys.executable,
        "-m",
        "src.source_updates",
        "plan",
        "--round",
        task["cadence"],
        "--as-of",
        as_of,
        "--family",
        definition["family"],
    ]
    if task["cadence"] == "quarterly":
        plan_command += ["--quarter", task["period"]]
    recipe_command = (
        [sys.executable, "-m", "src.source_updates.editorial_news", "--help"]
        if task["product"] == "editorial_news"
        else [sys.executable, "-m", "src.source_updates", "recipe", "--product", task["product"]]
    )
    publications = confirmed_publications(state or {}, task["product"], task["period"], as_of)
    job = {
        "task_key": key,
        "event_id": event_id,
        "is_scheduled_event": event_id is not None,
        "product": task["product"],
        "source_key": definition["source_key"],
        "family": definition["family"],
        "cadence": task["cadence"],
        "period": task["period"],
        "as_of": as_of,
        "skill": definition["skill"],
        "logical_agent_name": logical,
        "owner_native_id": None,
        "workspace": str(folder),
        "lease_fields": {"execution_mode": "isolated_skill_worker", "worker_workspace": str(folder)},
        "preflight_commands": [plan_command, recipe_command],
        "official_publication_date": max((row["published_on"] for row in publications), default=None),
        "confirmed_publications": publications,
        "publication_trigger": definition["publication_trigger"],
        "consolidated_execution_date": event_date,
        "period_closed_at_cutoff": period_end(task["period"]) < cutoff.date(),
        "destinations": {
            name: str(folder / relative)
            for name, relative in {
                "evidence": "evidence",
                "receipts": "receipts",
                "bronze": "data/bronze",
                "silver": "data/silver",
                "gold": "data/gold",
                "operational_receipt": "receipts/worker-result.json",
            }.items()
        },
        "limits": definition["limitation"],
        "acquisition_state": definition["acquisition_state"],
    }
    job["native_call"] = {
        "tool": NATIVE_TOOL,
        "arguments": {
            "task_name": logical,
            "fork_turns": "all",
            "message": worker_message(job, state, as_of, not execution_handoff),
        },
    }
    return job


def envelope_metadata(as_of: str, jobs: list[dict]) -> dict:
    return {
        "version": 1,
        "as_of": as_of,
        "jobs": jobs,
        "native_capability_required": NATIVE_TOOL,
        "native_capability_verified": False,
        "native_dispatch_instructions": [
            "El coordinador comprueba que la herramienta nativa existe en el host; si falta, bloquea.",
            (
                "Antes del envío, registra dispatch_intent con IDs reales y lease_fields del job. "
                "En un ensayo no programado no uses el ledger de ejecución."
            ),
            "Invoca directamente el envelope mediante la herramienta nativa; Python no lo ejecuta.",
            (
                "Guarda native_task_name y native_response_sha256 reales en acknowledge; "
                "message_id/worker_turn_id quedan nulos si el proveedor no los expone. "
                "No repitas envíos inciertos."
            ),
            (
                "Retén el resultado original intacto y construye wrapper local con task_key, intent_id y "
                "receipt_id local-operational-wrapper ligado a evidencia real; no reescribas worker/original."
            ),
            (
                "El coordinador consolida con readiness/global y un escritor; "
                "no transforma todo con un rebuild universal."
            ),
        ],
        "native_calls_performed": 0,
        "network_requests": 0,
        "scheduled_executions": 0,
        "writes": [],
        "publication_authorized": False,
    }


def manifest(
    state: dict,
    event_id: str,
    as_of: str,
    *,
    execution_handoff: bool = False,
    worker_root: Path | None = None,
    state_file: Path | None = None,
    coordinator_owner_turn_id: str | None = None,
    coordinator_owner_lease_id: str | None = None,
) -> dict:
    cutoff = local_time(as_of)
    if coordinator_owner_lease_id is not None and (
        not isinstance(coordinator_owner_lease_id, str)
        or not coordinator_owner_lease_id.startswith("local_lease:")
        or not coordinator_owner_lease_id.removeprefix("local_lease:").strip()
    ):
        raise ValueError("A local coordinator owner lease must be labelled local_lease:<token>")
    owner = coordinator_owner_lease_id or coordinator_owner_turn_id
    if type(execution_handoff) is not bool:
        raise ValueError("Execution handoff must be an explicit boolean")
    if not re.fullmatch(r"[a-f0-9]{64}", event_id):
        raise ValueError("Expected the exact event SHA-256")
    if (
        state.get("coordinator_id") != "airlines-tracker-source-calendar"
        or type(state.get("version")) is not int
        or state["version"] != 1
    ):
        raise ValueError("Unsupported coordinator state")
    if state.get("timezone") != "America/Mexico_City" or not isinstance(state.get("workspace"), str):
        raise ValueError("Canonical coordinator identity/timezone is required")
    if state.get("publication_authorized") is not False:
        raise ValueError("Dispatch never carries publication authorization")
    if state.get("active_task") is not None or state.get("active_tasks"):
        active = state.get("active_tasks", {})
        if (
            not active
            or not owner
            or any(
                state["tasks"][key]["dispatches"][-1].get("execution_mode") != "isolated_skill_worker"
                or state["tasks"][key]["dispatches"][-1].get(
                    "owner_lease_id", state["tasks"][key]["dispatches"][-1].get("owner_turn_id")
                )
                != owner
                for key in active
            )
        ):
            raise ValueError("Reconcile the persisted active writer before another dispatch")
    current = coordinator.trigger(state, as_of)
    if current.get("event_id") != event_id:
        raise ValueError("Event is not the next calendar event with its exact date and members")
    pending = current.get("pending_task_keys", [])
    if not pending or len(set(pending)) != len(pending):
        raise ValueError("Event must contain unique pending task keys")
    expected_pending = {
        key
        for key, task in state["tasks"].items()
        if task.get("selected") is True
        and task.get("status") in {"planned", "retry_pending"}
        and task.get("due_date") == current["date"]
    }
    if set(pending) != expected_pending:
        raise ValueError("Pending source tasks and frozen event membership differ")
    if execution_handoff:
        if (
            state.get("activation_authorized") is not True
            or not isinstance(state.get("automation_id"), str)
            or not state["automation_id"].strip()
        ):
            raise ValueError("Native execution requires authorized, bound calendar activation")
        if (
            not isinstance(state.get("automation_creation"), dict)
            or state["automation_creation"].get("outcome") != "bound"
        ):
            raise ValueError("Reconcile uncertain automation creation before source execution")
        if cutoff.date() != date.fromisoformat(current["date"]):
            raise ValueError("Execution requires the event date; reconcile overdue or future events")
        canonical = Path(state["workspace"]) / "state.json"
        if state_file is None or state_file.resolve() != canonical.resolve():
            raise ValueError("Execution requires the canonical state, never a copied ledger")
    root = safe_workspace(worker_root or (ROOT / "tmp/source-updates/dispatch" / event_id))
    if (
        root == Path(state["workspace"])
        or root.is_relative_to(Path(state["workspace"]))
        or Path(state["workspace"]).is_relative_to(root)
    ):
        raise ValueError("Worker output and coordinator ledger must be disjoint")
    mapped = {row["product"]: row for row in source_map()["products"]}
    jobs = []
    for key in pending:
        task = state["tasks"][key]
        validate_task(key, task, mapped, as_of, execution_handoff)
        definition = mapped[task["product"]]
        jobs.append(
            make_job(
                task,
                key,
                definition,
                root,
                event_id,
                as_of,
                state=state,
                event_id=event_id,
                event_date=current["date"],
                execution_handoff=execution_handoff,
            )
        )
    return {
        **envelope_metadata(as_of, jobs),
        "mode": "execution_handoff" if execution_handoff else "rehearsal_plan_only",
        "is_scheduled_event": True,
        "coordinator_id": state["coordinator_id"],
        "event_id": event_id,
        "state_input": str(state_file) if state_file else None,
        "canonical_state": str(Path(state["workspace"]) / "state.json"),
        "event_date": current["date"],
        "members": current["members"],
    }


def closed_task(product: str, definition: dict, as_of: str) -> tuple[str, dict]:
    today = local_time(as_of).date()
    month_end = today.replace(day=1) - timedelta(days=1)
    quarter_end = today.replace(month=(today.month - 1) // 3 * 3 + 1, day=1) - timedelta(days=1)
    cadence = "monthly" if definition["cadence"] in {"monthly", "both"} else definition["cadence"]
    period = (
        month_end.strftime("%YM%m")
        if cadence == "monthly"
        else f"{quarter_end.year}Q{(quarter_end.month - 1) // 3 + 1}"
    )
    task = dict(
        product=product,
        cadence=cadence,
        period=period,
        selected=True,
        status="planned",
        dispatches=[],
        reschedules=0,
    )
    return f"{cadence}:{period}:{product}", task


def rehearsal_products(products: list[str]) -> dict:
    mapped = {row["product"]: row for row in source_map()["products"]}
    if (
        not isinstance(products, list)
        or not 1 <= len(products) <= 44
        or not all(isinstance(p, str) for p in products)
        or len(set(products)) != len(products)
    ):
        raise ValueError("Choose unique explicit rehearsal products")
    if any(product not in mapped for product in products):
        raise ValueError("Unknown rehearsal product")
    return mapped


def rehearsal_manifest(as_of: str, products: list[str]) -> dict:
    """Explicit dry source-skill selection; never create a fictitious calendar event."""
    local_time(as_of)
    mapped = rehearsal_products(products)
    identity = coordinator.digest(
        {"mode": "unscheduled_skill_rehearsal", "as_of": as_of, "products": products}
    )
    root = safe_workspace(ROOT / "tmp/source-updates/skill-rehearsal" / identity)
    jobs = []
    for product in products:
        key, task = closed_task(product, mapped[product], as_of)
        validate_task(key, task, mapped, as_of, False)
        jobs.append(make_job(task, key, mapped[product], root, identity, as_of))
    return {
        **envelope_metadata(as_of, jobs),
        "mode": "unscheduled_skill_rehearsal",
        "is_scheduled_event": False,
        "rehearsal_id": identity,
        "event_id": None,
        "event_date": None,
        "coordinator_id": None,
        "canonical_state": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--event-id")
    parser.add_argument("--as-of")
    parser.add_argument("--source-map", action="store_true")
    parser.add_argument("--rehearse-product", action="append")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execution-handoff", action="store_true")
    parser.add_argument("--worker-root", type=Path)
    parser.add_argument("--coordinator-owner-turn-id")
    parser.add_argument("--coordinator-owner-lease-id")
    args = parser.parse_args()
    try:
        if args.rehearse_product:
            if not args.as_of or args.state or args.event_id or args.execution_handoff or args.source_map:
                raise ValueError(
                    "Unscheduled rehearsal needs --as-of and explicit products, without execution/state"
                )
            result = rehearsal_manifest(args.as_of, args.rehearse_product)
        elif args.source_map:
            result = source_map()
        else:
            if not args.state or not args.event_id or not args.as_of:
                raise ValueError("Declare --state, --event-id and the real zoned --as-of")
            if args.state.resolve() != args.state.absolute() or not args.state.is_file():
                raise ValueError("State input must be a regular physical file without symlink/traversal")
            result = manifest(
                json.loads(args.state.read_text(encoding="utf-8")),
                args.event_id,
                args.as_of,
                execution_handoff=args.execution_handoff,
                worker_root=args.worker_root,
                state_file=args.state,
                coordinator_owner_turn_id=args.coordinator_owner_turn_id,
                coordinator_owner_lease_id=args.coordinator_owner_lease_id,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": str(exc),
                    "native_calls_performed": 0,
                    "network_requests": 0,
                    "scheduled_executions": 0,
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
