"""Build and execute the reader-facing EDA notebook."""

from __future__ import annotations

import nbformat
from nbclient import NotebookClient

from src.config import PATHS


def build() -> None:
    notebook = nbformat.v4.new_notebook()
    notebook["metadata"]["kernelspec"] = {
        "display_name": "Python 3", "language": "python", "name": "python3",
    }
    notebook["metadata"]["language_info"] = {"name": "python", "version": "3.13"}
    notebook["cells"] = [
        nbformat.v4.new_markdown_cell(
            "# EDA reproducible de Aeroméxico\n\n"
            "## tl;dr\n\n"
            "La historia mensual de pasajeros es apta para modelado sencillo; la historia trimestral de Aeroméxico todavía debe tratarse como descriptiva. COVID permanece en la serie y no se reemplazan faltantes por cero."
        ),
        nbformat.v4.new_markdown_cell(
            "## Context & Methods\n\n"
            "Este notebook es un compañero auditable. La lógica productiva vive en `src.analytics.eda`; aquí se ejecuta y se muestran resultados acotados.\n\n"
            "### Key Assumptions\n\n"
            "- Vista consolidada de Aeroméxico.\n- Periodicidad mensual para pasajeros.\n- STL de periodo 12.\n- COVID se conserva como régimen extraordinario."
        ),
        nbformat.v4.new_code_cell(
            "from src.analytics.eda import run_eda\n"
            "eda = run_eda()\n"
            "{k: (len(v) if hasattr(v, '__len__') and not isinstance(v, dict) else v) for k, v in eda.items()}"
        ),
        nbformat.v4.new_markdown_cell("## Data\n\n### 1. Cobertura de la serie objetivo"),
        nbformat.v4.new_code_cell(
            "coverage = eda['coverage']\n"
            "coverage.query(\"carrier_key == 'AEROMEXICO' and metric_key == 'passengers_afac'\")"
            "[['segment','observations','first_period','last_period','null_values']]"
        ),
        nbformat.v4.new_markdown_cell("## Results\n\n### 2. Tendencia y estacionalidad mensual"),
        nbformat.v4.new_code_cell(
            "import plotly.graph_objects as go\n"
            "seasonality = eda['seasonality']\n"
            "fig = go.Figure()\n"
            "fig.add_scatter(x=seasonality['period_id'], y=seasonality['observed'], name='Observado', line=dict(color='#0B3A66'))\n"
            "fig.add_scatter(x=seasonality['period_id'], y=seasonality['trend'], name='Tendencia', line=dict(color='#C89211', dash='dash'))\n"
            "fig.update_layout(title='Pasajeros AFAC observados y tendencia STL', xaxis_title='Mes', yaxis_title='Pasajeros', template='plotly_white')\n"
            "fig.show()"
        ),
        nbformat.v4.new_markdown_cell("### 3. Relaciones con variables macro, con rezagos"),
        nbformat.v4.new_code_cell(
            "corr = eda['correlations'].dropna().assign(abs_corr=lambda d: d.correlation.abs())\n"
            "corr.sort_values('abs_corr', ascending=False).head(12)[['indicator_key','lag_months','correlation','observations']]"
        ),
        nbformat.v4.new_markdown_cell("### 4. Quiebres estructurales candidatos"),
        nbformat.v4.new_code_cell("eda['structural_breaks'].head(10)"),
        nbformat.v4.new_markdown_cell(
            "## Takeaways\n\n"
            "- Los pasajeros mensuales son la única prioridad de forecast con historia larga y completa.\n"
            "- La estacionalidad debe estar dentro del baseline; una comparación contra el mes anterior sería insuficiente.\n"
            "- Los quiebres alrededor de 2020-2023 se conservan como parte de la historia.\n"
            "- Correlación no implica causalidad y los rezagos macro son descriptivos.\n"
            "- Las conclusiones de negocio completas están en `docs/analytics/eda-hallazgos.md`."
        ),
    ]
    output = PATHS.root / "notebooks" / "01_eda.ipynb"
    output.parent.mkdir(parents=True, exist_ok=True)
    client = NotebookClient(notebook, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(PATHS.root)}})
    executed = client.execute()
    nbformat.write(executed, output)


if __name__ == "__main__":
    build()
