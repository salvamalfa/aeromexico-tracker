"""Generate the Stage 6 data dictionary from contracts and dim_metric."""

from __future__ import annotations

import pandas as pd

from src.config import PATHS
from src.transform.stage6_contracts import load_contracts


OUTPUT = PATHS.root / "docs" / "diccionario-datos.md"


def generate() -> str:
    contracts = load_contracts()
    lines = [
        "# Diccionario de datos",
        "",
        "> Archivo generado automáticamente por `python -m src.transform.generate_data_dictionary`.",
        f"> Contrato: `{contracts['version']}`. No editar manualmente.",
        "",
        "## Tablas gold",
        "",
    ]
    for table_name, definition in contracts["tables"].items():
        lines.extend(
            [
                f"### `{table_name}`",
                "",
                f"Clave primaria declarada: `{', '.join(definition.get('primary_key', []))}`.",
                "",
                "| Columna | Tipo | Nulo | Descripción |",
                "|---|---|---:|---|",
            ]
        )
        for column, properties in definition["columns"].items():
            description = str(properties["description"]).replace("|", "\\|")
            lines.append(f"| `{column}` | `{properties['type']}` | {'sí' if properties['nullable'] else 'no'} | {description} |")
        lines.append("")

    metrics = pd.read_parquet(PATHS.gold / "dim_metric.parquet").sort_values("display_order")
    lines.extend(
        [
            "## Catálogo de métricas",
            "",
            "Las interpretaciones provienen de `docs/plan/11-glosario-kpis.md`; las métricas técnicas no mostradas en el dashboard conservan una descripción de trazabilidad.",
            "",
        ]
    )
    for row in metrics.itertuples(index=False):
        lines.extend(
            [
                f"### `{row.metric_key}` — {row.metric_name_es}",
                "",
                f"- Categoría: `{row.metric_category}`",
                f"- Unidad: `{row.unit_normalized}`",
                f"- Fórmula: {row.formula if pd.notna(row.formula) else 'No declarada; valor reportado por la fuente.'}",
                f"- Si sube: {row.business_interpretation_up}",
                f"- Si baja: {row.business_interpretation_down}",
                f"- Por qué importa: {row.why_it_matters}",
                f"- Advertencias: {row.caveats}",
                f"- Sección del glosario: {row.glossary_section if pd.notna(row.glossary_section) else 'métrica técnica fuera del dashboard'}",
                "",
            ]
        )
    content = "\n".join(lines).rstrip() + "\n"
    OUTPUT.write_text(content, encoding="utf-8")
    return content


def main() -> int:
    generate()
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
