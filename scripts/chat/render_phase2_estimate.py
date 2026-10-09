"""Render reproducible offline F2.9 budget estimates; never creates a provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.conversational_analytics.evaluation import phase_cases
from src.conversational_analytics.evaluation_budget import CANDIDATES, estimate_stage, specs_from_model_catalog

PROMPT_COMMIT = "2f45994962b227b62e542b75b851c731b671329e"
PROMPT_PATH = "docs/chat/revision-fase-2/F2.1-prompt-propuesto.md"
BUSINESS_FIXTURE = ROOT / "tests/fixtures/chat_evals/business_proposed.json"
SAFETY_FIXTURE = ROOT / "tests/fixtures/chat_evals/safety_current.json"
OUT_JSON = ROOT / "docs/chat/estimacion-f2-9-presupuesto.json"
OUT_MD = ROOT / "docs/chat/estimacion-f2-9-presupuesto.md"
DEFAULT_CATALOG = ROOT / "config/chat/models.json"

INPUT_RANGE = (60_000, 100_000)
MARGIN = 0.25
DEVELOPMENT_RANGE_USD = (3.0, 5.0)
CACHE_SCENARIOS = (0.0, 0.8)
CANDIDATES_BY_STAGE = {
    1: {"gpt-6-luna@medium": 2},
    2: {candidate: 1 for candidate in CANDIDATES},
    3: {candidate: (2 if "gpt-6-luna" in candidate else 1) for candidate in CANDIDATES},
}


def _load_catalog(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if payload.get("schema_version") != 1 or not isinstance(payload.get("models"), dict):
        raise ValueError(f"Catálogo de modelos inválido: {path}")
    return payload, hashlib.sha256(raw).hexdigest()


def _read_prompt_document() -> str:
    result = subprocess.run(
        ["git", "show", f"{PROMPT_COMMIT}:{PROMPT_PATH}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def _measure(source: str, value: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "source": source,
        "characters_exact": len(value),
        "utf8_bytes_exact": len(value.encode("utf-8")),
        "tokenizer": "unavailable",
        "token_count_status": "heuristic_only_tiktoken_unavailable",
        "tokens": None,
        "tokens_heuristic_chars_div_4": round(len(value) / 4),
    }
    try:
        import tiktoken  # type: ignore[import-not-found]

        try:
            encoder = tiktoken.encoding_for_model("gpt-6-luna")
            row["token_count_status"] = "encoding_for_model"
        except KeyError:
            encoder = tiktoken.get_encoding("o200k_base")
            row["token_count_status"] = "proxy_encoding_o200k_base_model_mapping_unavailable"
        row["tokens"] = len(encoder.encode(value))
        row["encoding"] = getattr(encoder, "name", "unknown")
        row["tokenizer"] = getattr(tiktoken, "__version__", "tiktoken")
    except ImportError:
        pass
    return row


def _ceil_dollar(amount: float) -> int:
    return math.ceil(amount)


def _catalog_path_label(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return f"external input file: {path.name}"


def render(model_catalog_path: Path = DEFAULT_CATALOG) -> tuple[dict[str, Any], str]:
    business = json.loads(BUSINESS_FIXTURE.read_text(encoding="utf-8"))
    safety = json.loads(SAFETY_FIXTURE.read_text(encoding="utf-8"))
    catalog, catalog_sha = _load_catalog(model_catalog_path)
    specs = specs_from_model_catalog(catalog["models"])

    from src.conversational_analytics.data.snapshot import Snapshot
    from src.conversational_analytics.tools.registry import ToolRegistry

    prompt_document = _read_prompt_document()
    prompt_match = re.search(r"```text\s*(.*?)\s*```", prompt_document, flags=re.DOTALL)
    prompt = prompt_match.group(1) if prompt_match else ""
    serialized_tools = json.dumps(
        ToolRegistry(Snapshot(ROOT / "site")).tool_specs(), ensure_ascii=False, separators=(",", ":")
    )
    gold = json.dumps([c.get("expected", {}).get("rows", []) for c in business["cases"]], ensure_ascii=False, separators=(",", ":"))
    measurements = {
        "tokenizer_note": "tiktoken is used if installed; an unavailable model mapping falls back to labeled o200k_base proxy. Character/4 is a planning heuristic. These are source payload sizes, not billed prefills.",
        "f2_1_prompt": _measure(f"F2.1 prompt fenced text from commit {PROMPT_COMMIT}", prompt),
        "f2_1_prompt_source": {
            "commit": PROMPT_COMMIT,
            "path": PROMPT_PATH,
            "sha256": hashlib.sha256(prompt_document.encode("utf-8")).hexdigest(),
            "immutable_url": f"https://github.com/salvamalfa/aeromexico-tracker/blob/{PROMPT_COMMIT}/{PROMPT_PATH}",
        },
        "tool_schemas": _measure("ToolRegistry(Snapshot(site)).tool_specs() serialized JSON", serialized_tools),
        "fixture_gold_rows": _measure("business_proposed.json expected.rows serialized JSON", gold),
        "fixtures": {
            "business_path": str(BUSINESS_FIXTURE.relative_to(ROOT)),
            "business_sha256": hashlib.sha256(BUSINESS_FIXTURE.read_bytes()).hexdigest(),
            "safety_path": str(SAFETY_FIXTURE.relative_to(ROOT)),
            "safety_sha256": hashlib.sha256(SAFETY_FIXTURE.read_bytes()).hexdigest(),
            "business_expected_versions": business.get("expected_versions", {}),
            "safety_expected_versions": safety.get("expected_versions", {}),
        },
        "model_catalog": {
            "path": _catalog_path_label(model_catalog_path),
            "sha256": catalog_sha,
            "source": catalog.get("source"),
            "pricing_as_of": {key: value.get("pricing_as_of") for key, value in catalog["models"].items()},
            "pricing_dates_utc": sorted({value.get("pricing_as_of") for value in catalog["models"].values()}),
            "model_sources": {key: value.get("source") for key, value in catalog["models"].items()},
            "owner_local_review_date": "2026-10-08 America/Mexico_City",
        },
        "historical_anchor": {
            "input_tokens_per_user_question": 40_000,
            "status": "observed historical aggregate across internal provider calls; not measured on this fixture",
            "source": "prior live validation dated 2026-10-04, linked from fase-2-agente-analitico.md",
        },
    }

    selections = {stage: phase_cases(business["cases"], safety["cases"], stage) for stage in (1, 2, 3)}
    estimates = []
    for cache_rate in CACHE_SCENARIOS:
        stages = []
        for stage, selected in selections.items():
            result = estimate_stage(
                selected,
                CANDIDATES_BY_STAGE[stage],
                input_tokens_per_user_message=INPUT_RANGE,
                cache_hit_rate=cache_rate,
                candidate_specs=specs,
            )
            result["stage"] = stage
            result["selected_case_ids"] = [case["id"] for case in selected]
            result["extra_multiturn_user_messages_per_case_run"] = result["user_messages_per_case_run"] - len(selected)
            stages.append(result)
        total = [
            sum(row["estimated_cost_usd_range"][index] for stage in stages for row in stage["candidate_estimates"])
            for index in (0, 1)
        ]
        estimates.append({
            "mode": "offline_modelled_estimate",
            "cache_hit_rate_scenario": cache_rate,
            "stages": stages,
            "all_stage_cost_usd_range": [round(v, 4) for v in total],
        })

    stage_reserves = []
    for stage in estimates[0]["stages"]:
        high = sum(row["estimated_cost_usd_range"][1] for row in stage["candidate_estimates"])
        stage_reserves.append({
            "stage": stage["stage"],
            "modeled_upper_cost_no_cache_usd": round(high, 4),
            "margin_rate": MARGIN,
            "funds_to_have_available_if_zero_verified_balance_usd": _ceil_dollar(high * (1 + MARGIN)),
            "net_topup_rule": "max(0, stage reserve - reconciled available balance); current balance is unreconciled",
        })
    low, high = estimates[0]["all_stage_cost_usd_range"]
    roadmap = {
        "development_reference_usd": list(DEVELOPMENT_RANGE_USD),
        "development_note": "The F2 plan says roughly five Luna-M rounds for F2.1–F2.8; without concrete run plans this estimate remains separate from stage budgets.",
        "stages_no_cache_usd": [low, high],
        "stages_plus_development_usd": [round(low + DEVELOPMENT_RANGE_USD[0], 4), round(high + DEVELOPMENT_RANGE_USD[1], 4)],
        "plus_development_and_25_percent_margin_usd": [
            round((low + DEVELOPMENT_RANGE_USD[0]) * 1.25, 4),
            round((high + DEVELOPMENT_RANGE_USD[1]) * 1.25, 4),
        ],
        "global_planning_reference_usd": _ceil_dollar((high + DEVELOPMENT_RANGE_USD[1]) * 1.25),
        "all_work_funds_scope": "global planning reference only: one margin is applied to the high estimate for all three stages plus the development reference, then rounded up; it is not an authorized budget or an operational campaign cap",
        "stage_reserves": stage_reserves,
        "stage_3_is_provisional": True,
        "available_balance_usd": None,
        "balance_status": "unreconciled; the historical ~US$7 figure is not current available balance",
    }
    payload = {
        "status": "planning_only_pending_owner_approval",
        "reviewed_at_owner_local": "2026-10-08 America/Mexico_City",
        "tariff_source": catalog.get("source"),
        "tariff_basis": "Authoritative model catalog prices, USD per million input/cached/write/output tokens; short-context scenarios.",
        "measurements": measurements,
        "assumptions": {
            "input_tokens_per_user_message_range": list(INPUT_RANGE),
            "output_ranges_include_reasoning_once": True,
            "cache_scenarios": list(CACHE_SCENARIOS),
            "cache_write_usage": "unknown; not assumed zero",
            "long_context": "Catalog thresholds/multipliers are recorded, but request-level token usage is unknown; modeled costs do not apply the long-context premium.",
            "margin_rate": MARGIN,
        },
        "campaign_budget_scope": {
            "scope": "one shared operational budget per stage campaign",
            "details": "Within a stage, prompt variants, candidates, repetitions, and resumed runs share one campaign ledger. Each stage has its own authorization and budget_usd; there is no single live ledger spanning all three stages.",
            "resume": "resume requires the same campaign identity and budget; interrupted provider work with unknown spend blocks replay",
            "limit": "operational stop only; it does not guarantee a maximum invoice",
        },
        "estimates": estimates,
        "roadmap_budget": roadmap,
        "limitations": [
            "No paid API was called and no credentials were read. No live usage, latency, cache rates, or invoice were measured.",
            "The historical ~40k input tokens per user question aggregates internal provider calls. The 60k–100k per user message interval is modeled, not a billed prompt measurement.",
            "Output ranges include reasoning and are applied to every user message, including explicit follow-ups.",
            "Cache scenarios price each input token once as normal or cached. Cache-write usage remains unknown, not zero.",
            "Long-context pricing applies per provider request above 272k input tokens. Request-level token counts are unavailable; an actual request crossing this threshold would cost more.",
            "The 25% planning margin is not a spending ceiling or invoice guarantee.",
            "The live account balance is unreconciled; no deduction is made from the former ~US$7 reference.",
            "The 3–5 USD development estimate is a rough plan reference and is not assigned to stage reserves without concrete calls.",
        ],
    }
    return payload, _render_markdown(payload)


def _format_measurement(name: str, value: dict[str, Any]) -> str:
    tokens = value.get("tokens")
    if tokens is None:
        tokens = value["tokens_heuristic_chars_div_4"]
        label = "tokens heurísticos char/4 (no tokenizados)"
    else:
        label = f"tokens ({value['token_count_status']}, {value.get('encoding', 'encoding')})"
    return f"- `{name}`: {value['characters_exact']:,} caracteres, {value['utf8_bytes_exact']:,} bytes; {tokens:,} {label}."


def _render_markdown(payload: dict[str, Any]) -> str:
    ms = payload["measurements"]
    roadmap = payload["roadmap_budget"]
    no_cache, cached = payload["estimates"]
    rows = [
        "# Estimación offline F2.9 (borrador)",
        "",
        "**Estado: estimación modelada; fixture, rúbrica, prompt, alcance y presupuesto siguen pendientes de aprobación. No hubo llamadas pagadas ni uso de credenciales.**",
        "",
        f"Fecha de tarifas declarada por catálogo (UTC): {', '.join(ms['model_catalog']['pricing_dates_utc'])}; revisión local: {ms['model_catalog']['owner_local_review_date']}. Catálogo `{ms['model_catalog']['path']}`, SHA-256 `{ms['model_catalog']['sha256']}`. Fichas oficiales: "
        + ", ".join(f"[{model}]({source})" for model, source in ms["model_catalog"]["model_sources"].items()) + ".",
        "",
        "## Insumos offline",
        "",
        _format_measurement("prompt F2.1", ms["f2_1_prompt"]),
        f"- Fuente inmutable del prompt: [{ms['f2_1_prompt_source']['path']} @ {ms['f2_1_prompt_source']['commit']}]({ms['f2_1_prompt_source']['immutable_url']}); SHA-256 del documento `{ms['f2_1_prompt_source']['sha256']}`.",
        _format_measurement("schemas de herramientas", ms["tool_schemas"]),
        _format_measurement("filas gold", ms["fixture_gold_rows"]),
        "",
        "Los tamaños de prompt, esquemas y gold describen sus payloads fuente; no son tokens facturados de los prefills acumulados. El histórico medido fue ~40,000 tokens de entrada por pregunta sumando llamadas internas. Para la fase futura se modelan 60,000–100,000 tokens por cada mensaje del usuario.",
        "",
        "## Casos y corridas",
        "",
        "| Etapa | Casos seleccionados | Mensajes por corrida | Corridas de candidato | Casos-ejecución |",
        "|---|---:|---:|---:|---:|",
    ]
    for stage in no_cache["stages"]:
        count = len(stage["selected_case_ids"])
        runs = sum(CANDIDATES_BY_STAGE[stage["stage"]].values())
        case_runs = sum(row["case_runs"] for row in stage["candidate_estimates"])
        rows.append(f"| {stage['stage']} | {count} | {stage['user_messages_per_case_run']} | {runs} | {case_runs} |")
    rows.extend([
        "",
        "`evaluation.phase_cases` selecciona los casos por etapa. El conteo toma `turns` del fixture: N24 tiene 3 mensajes y N25/N26 tienen 2. La etapa 1 tiene dos corridas de candidato (prompt actual y propuesto), la etapa 2 una por cada uno de los cuatro candidatos y la etapa 3 seis corridas: dos por cada Luna y una por cada Sol. `Casos-ejecución` multiplica casos por corridas; los mensajes por corrida ya cuentan los seguimientos.",
        "",
        "## Costo modelado por candidato",
        "",
        "La salida incluye razonamiento una sola vez. Cada mensaje de seguimiento suma input y output. Los precios proceden del catálogo versionado. Cache writes son desconocidos y no se tratan como costo cero.",
        "",
    ])
    for scenario in (no_cache, cached):
        rate = scenario["cache_hit_rate_scenario"]
        rows.extend([
            f"### Cache hit modelado: {rate:.0%}",
            "",
            "| Etapa | Candidato | Casos ejecutados | Mensajes | Input tokens | Output + razonamiento | USD |",
            "|---|---|---:|---:|---:|---:|---:|",
        ])
        for stage in scenario["stages"]:
            for estimate in stage["candidate_estimates"]:
                a, b = estimate["estimated_input_tokens_range"]
                c, d = estimate["modeled_output_plus_reasoning_tokens_range"]
                e, f = estimate["estimated_cost_usd_range"]
                rows.append(f"| {stage['stage']} | {estimate['candidate']} | {estimate['case_runs']} | {estimate['user_messages']} | {a:,}–{b:,} | {c:,}–{d:,} | ${e:.2f}–${f:.2f} |")
        a, b = scenario["all_stage_cost_usd_range"]
        rows.extend(["", f"Total de tres etapas en el escenario: **${a:.2f}–${b:.2f}**.", ""])
    rows.extend([
        "## Fondos por cargar antes de cada etapa",
        "",
        "Cada etapa es una campaña separada con su propia autorización y `budget_usd`. Dentro de la etapa, sus prompts, candidatos, repeticiones y reanudaciones comparten un solo ledger; no hay un ledger operativo único para las tres etapas. Se usa el costo alto sin caché y se agrega 25%, redondeando al siguiente dólar. No se resta saldo porque no está reconciliado. Si se confirma saldo disponible, carga `max(0, reserva − saldo disponible)`.",
        "",
        "| Etapa | Costo alto sin caché | Con margen | Fondos necesarios si saldo verificado es US$0 |",
        "|---|---:|---:|---:|",
    ])
    for reserve in roadmap["stage_reserves"]:
        rows.append(f"| {reserve['stage']} | ${reserve['modeled_upper_cost_no_cache_usd']:.2f} | ${reserve['modeled_upper_cost_no_cache_usd'] * 1.25:.2f} | **US${reserve['funds_to_have_available_if_zero_verified_balance_usd']}** |")
    rows.extend([
        "",
        f"El plan mantiene aparte US${roadmap['development_reference_usd'][0]:.0f}–${roadmap['development_reference_usd'][1]:.0f} para unas cinco rondas Luna-M de F2.1–F2.8; aún no hay un run plan para convertirlas en calls. La suma orientativa de las tres proyecciones más esa referencia es ${roadmap['stages_plus_development_usd'][0]:.2f}–${roadmap['stages_plus_development_usd'][1]:.2f} antes del margen y ${roadmap['plus_development_and_25_percent_margin_usd'][0]:.2f}–${roadmap['plus_development_and_25_percent_margin_usd'][1]:.2f} con margen. La referencia global de **US${roadmap['global_planning_reference_usd']}** aplica una vez 25% al extremo alto más desarrollo y redondea al dólar; no es presupuesto autorizado ni un tope operativo. Las reservas recomendadas por etapa se redondean por separado a US$3, US$11 y US$54; su suma (US$68) usa otro redondeo y no incluye desarrollo.",
        "",
        "La etapa 3 es provisional y debe recalcularse después del piloto con el uso medido y la lista final de candidatos. La campaña de cada etapa comparte presupuesto entre sus corridas. Reanudar requiere la misma identidad y presupuesto; si una llamada interrumpida deja gasto desconocido, se bloquea el replay. El stop es operativo: no limita una solicitud ya iniciada ni garantiza el máximo de factura.",
        "",
        "## Límites",
        "",
        "Se presupone precio de contexto corto. La tarifa long-context aplica por solicitud individual que exceda 272,000 tokens de entrada; no hay medición por solicitud para saber si ocurre. En ese caso el costo sería mayor. El saldo vivo no está conciliado y la referencia histórica de ~US$7 no se considera saldo disponible.",
        "",
        "El JSON conserva versiones y hashes de fixtures y catálogo. Para regenerar: `uv run python scripts/chat/render_phase2_estimate.py [--model-catalog PATH]`.",
        "",
    ])
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--stdout", action="store_true", help="emit JSON and Markdown without writing files")
    args = parser.parse_args(argv)
    payload, markdown = render(args.model_catalog)
    if args.stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(markdown)
    else:
        OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
