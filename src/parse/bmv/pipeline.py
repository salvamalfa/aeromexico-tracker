"""Orchestrate the complete BMV bronze-to-silver Stage 2 parse."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from src.common.quality import log_issue_once
from src.config import PATHS, SOURCE_URLS
from src.parse.bmv.derive import derive_quarters_from_ytd
from src.parse.bmv.reconciliation import build_reconciliation
from src.parse.bmv.validate import build_accounting_checks
from src.parse.bmv.xbrl import parse_all_packages, rebuild_package_index_from_bronze
from src.parse.sec.common import write_parquet_atomic


def _markdown(value: object) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def write_concept_dictionary(concepts: pl.DataFrame) -> Path:
    """Write the complete observed BMV concept catalog as reviewable Markdown."""

    target = PATHS.root / "docs" / "diccionario-conceptos-xbrl.md"
    extension_count = concepts.filter(pl.col("concept_is_extension")).height
    lines = [
        "# Diccionario de conceptos XBRL BMV / CNBV",
        "",
        "Catálogo generado a partir de todos los paquetes visibles de AERO y VOLAR en la",
        f"[tabla pública de la BMV]({SOURCE_URLS['bmv_xbrl']}). Incluye únicamente conceptos",
        "que tienen al menos un hecho en los paquetes preservados; las etiquetas se toman",
        "del modelo XBRL distribuido por la propia BMV.",
        "",
        f"- Conceptos observados: **{concepts.height:,}**.",
        f"- Conceptos fuera de los namespaces `ifrs-full`/`ifrs-mc`: **{extension_count:,}**.",
        "- `fact_count` suma apariciones entre paquetes y periodos comparativos; no es una métrica de negocio.",
        "- `statement_types` conserva todos los roles de presentación en los que aparece el concepto.",
        "",
        "| Concepto | Taxonomía | Etiqueta ES | Etiqueta EN | Extensión | Estados | Emisoras | Hechos |",
        "|---|---|---|---|---:|---|---|---:|",
    ]
    for row in concepts.iter_rows(named=True):
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown(row["concept"]),
                    _markdown(row["taxonomy"]),
                    _markdown(row["concept_label_es"]),
                    _markdown(row["concept_label_en"]),
                    "Sí" if row["concept_is_extension"] else "No",
                    _markdown(row["statement_types"]),
                    _markdown(row["tickers"]),
                    f"{int(row['fact_count']):,}",
                ]
            )
            + " |"
        )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def run_bmv_parse() -> dict[str, object]:
    packages = rebuild_package_index_from_bronze()
    write_parquet_atomic(packages, PATHS.silver / "bmv_packages_index.parquet")
    source_facts, concepts = parse_all_packages(packages)
    facts = derive_quarters_from_ytd(source_facts)
    write_parquet_atomic(facts, PATHS.silver / "bmv_financials.parquet")
    write_parquet_atomic(concepts, PATHS.silver / "bmv_concepts.parquet")
    reconciliation = build_reconciliation(facts)
    write_parquet_atomic(
        reconciliation, PATHS.silver / "bmv_sec_reconciliation.parquet"
    )
    accounting_checks = build_accounting_checks(facts)
    write_parquet_atomic(
        accounting_checks, PATHS.silver / "bmv_validation_checks.parquet"
    )
    logged_issues = 0
    for row in reconciliation.filter(pl.col("is_material")).iter_rows(named=True):
        log_issue_once(
            "silver",
            "bmv_sec_reconciliation",
            str(row["bmv_source_file"]),
            "warning" if row["is_explained"] else "error",
            "source_conflict",
            (
                f"{row['period_id']} {row['concept']}: BMV={row['bmv_value_usd']:.0f} "
                f"USD, SEC={row['sec_value_usd']:.0f} USD, relative difference="
                f"{row['relative_difference']:.6%}. {row['explanation']}"
            ),
            1,
        )
        logged_issues += 1
    dictionary_path = write_concept_dictionary(concepts)
    return {
        "network_used": False,
        "package_rows": packages.height,
        "aero_packages": packages.filter(pl.col("ticker") == "AERO").height,
        "volar_packages": packages.filter(pl.col("ticker") == "VOLAR").height,
        "source_fact_rows": source_facts.height,
        "derived_fact_rows": facts.filter(pl.col("is_derived")).height,
        "financial_rows": facts.height,
        "concept_rows": concepts.height,
        "extension_concept_rows": concepts.filter(pl.col("concept_is_extension")).height,
        "reconciliation_rows": reconciliation.height,
        "material_reconciliation_rows": reconciliation.filter(pl.col("is_material")).height,
        "unresolved_reconciliation_rows": reconciliation.filter(pl.col("requires_review")).height,
        "quality_issues_logged": logged_issues,
        "accounting_check_rows": accounting_checks.height,
        "accounting_check_failures": accounting_checks.filter(~pl.col("passed")).height,
        "concept_dictionary": dictionary_path.relative_to(PATHS.root).as_posix(),
    }


def main() -> int:
    print(json.dumps(run_bmv_parse(), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
