"""Render the Stage 11 executive prototype as a self-contained HTML file."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
from typing import Any

from plotly.offline import get_plotlyjs

from src.config import PATHS
from src.dashboard.executive_summary import KPI_DEFINITIONS


CSS_PATH = PATHS.root / "src" / "dashboard" / "assets" / "executive_summary.css"
JS_PATH = PATHS.root / "src" / "dashboard" / "assets" / "executive_summary.js"
DEFAULT_OUTPUT = PATHS.root / "prototypes" / "etapa-11" / "resumen_ejecutivo.html"


def _safe_json(payload: dict[str, Any]) -> str:
    value = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return (
        value.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _kpi_cards() -> str:
    cards: list[str] = []
    for definition in KPI_DEFINITIONS:
        key = escape(definition["key"], quote=True)
        label = escape(definition["label"])
        description = escape(definition["description"], quote=True)
        accent = escape(definition["accent"], quote=True)
        cards.append(
            f"""
            <article class="kpi-card" data-kpi="{key}" data-accent="{accent}">
              <span class="kpi-info" title="{description}" aria-label="{description}">i</span>
              <p class="kpi-label">{label}</p>
              <p class="kpi-value" id="kpi-{key}-value">—</p>
              <div class="kpi-comparisons">
                <div class="comparison-chip"><span>Vs. trimestre anterior</span><strong id="kpi-{key}-qoq">—</strong></div>
                <div class="comparison-chip"><span>Vs. año anterior</span><strong id="kpi-{key}-yoy">—</strong></div>
              </div>
            </article>
            """
        )
    return "".join(cards)


def _history_cards(payload: dict[str, Any]) -> str:
    cards: list[str] = []
    for record in reversed(payload["records"]):
        view = payload["views"][record["period_id"]]
        cards.append(
            """
            <article class="history-item">
              <h3>{period}: {headline}</h3>
              <p>{summary}</p>
            </article>
            """.format(
                period=escape(record["period_label"]),
                headline=escape(view["narrative"]["headline"]),
                summary=escape(view["narrative"]["paragraphs"][0]),
            )
        )
    return "".join(cards)


def _data_rows(payload: dict[str, Any]) -> str:
    rows: list[str] = []
    for record in reversed(payload["records"]):
        rows.append(
            """
            <tr>
              <td>{period}</td>
              <td>{rask:.2f}</td>
              <td>{cask:.2f}</td>
              <td>{margin:+.2f}</td>
              <td>{ask:.2f}</td>
              <td>{load:.1%}</td>
              <td>{passengers:.3f}</td>
            </tr>
            """.format(
                period=escape(record["period_label"]),
                rask=record["rask_cents_per_km"],
                cask=record["cask_cents_per_km"],
                margin=record["unit_margin_cents_per_km"],
                ask=record["ask_km"] / 1_000_000_000,
                load=record["load_factor_reported"],
                passengers=record["passengers"] / 1_000_000,
            )
        )
    return "".join(rows)


def _period_options(payload: dict[str, Any]) -> str:
    default = payload["metadata"]["default_period"]
    options: list[str] = []
    for record in reversed(payload["records"]):
        selected = " selected" if record["period_id"] == default else ""
        options.append(
            f'<option value="{escape(record["period_id"], quote=True)}"{selected}>'
            f'{escape(record["period_label"])}</option>'
        )
    return "".join(options)


def render_executive_html(payload: dict[str, Any]) -> str:
    """Return a complete offline HTML document from a validated payload."""

    css = CSS_PATH.read_text(encoding="utf-8")
    app_js = JS_PATH.read_text(encoding="utf-8")
    plotly_js = get_plotlyjs()
    if re.search(r"</script", plotly_js, re.IGNORECASE):
        raise ValueError("Bundled Plotly JavaScript contains an unsafe script terminator")
    metadata = payload["metadata"]
    document = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{escape(metadata['title'])}</title>
  <style>{css}</style>
</head>
<body>
  <main class="page-shell" data-testid="executive-summary-root">
    <header class="hero">
      <div class="hero-grid">
        <div>
          <h1>Aeroméxico — Vista ejecutiva trimestral</h1>
        </div>
        <div class="period-control">
          <label for="period-selector">Trimestre analizado</label>
          <select id="period-selector" aria-describedby="period-help">{_period_options(payload)}</select>
          <span id="period-help" class="sr-only">Actualiza tarjetas, conclusiones, narrativa y trimestre destacado.</span>
        </div>
      </div>
    </header>

    <section class="kpi-grid" aria-label="Indicadores ejecutivos">
      {_kpi_cards()}
    </section>

    <section aria-labelledby="unit-heading">
      <div class="section-heading">
        <div>
          <p class="section-kicker">Economía unitaria</p>
          <h2 id="unit-heading">Ingreso, costo y margen por ASK</h2>
        </div>
        <p class="source-inline">Fuente: {escape(metadata['source_view'])}</p>
      </div>
      <article class="chart-card">
        <p class="chart-title">RASK vs CASK y margen unitario</p>
        <p class="chart-subtitle">Cuando RASK supera CASK, la operación genera utilidad por cada asiento-kilómetro.</p>
        <div class="chart" id="unit-chart" role="img" aria-label="Serie trimestral de RASK, CASK y margen unitario"></div>
      </article>
    </section>

    <section class="chart-grid" aria-label="Diagnósticos de volumen y utilización">
      <article class="chart-card">
        <p class="chart-title">Precio versus volumen de pasajeros</p>
        <p class="chart-subtitle">Las barras indican el número de pasajeros; la línea, el RASK.</p>
        <div class="chart chart-sm" id="volume-chart" role="img" aria-label="Pasajeros y RASK por trimestre"></div>
      </article>
      <article class="chart-card">
        <p class="chart-title">Factor de ocupación vs RASK</p>
        <p class="chart-subtitle">Cada punto es un trimestre; los colores identifican el año. {escape(metadata['load_rask_interpretation'])}</p>
        <div class="chart chart-sm" id="load-chart" role="img" aria-label="Relación entre factor de ocupación y RASK"></div>
      </article>
    </section>

    <section class="narrative-card" aria-labelledby="narrative-headline">
      <div>
        <p class="section-kicker">Lectura ejecutiva · <span id="narrative-period">—</span></p>
        <h2 id="narrative-headline">—</h2>
      </div>
      <div class="narrative-copy" id="narrative-copy"></div>
    </section>

    <section class="executive-insight" aria-labelledby="insight-title">
      <div>
        <p class="section-kicker">Conclusiones clave</p>
        <h2 id="insight-title"><span id="insight-period">—</span> en tres lecturas</h2>
      </div>
      <ul class="insight-list" id="insight-list"></ul>
    </section>

    <details class="disclosure">
      <summary>Ver análisis de trimestres anteriores</summary>
      <div class="disclosure-body history-grid">{_history_cards(payload)}</div>
    </details>

    <details class="disclosure">
      <summary>Ver datos por trimestre</summary>
      <div class="disclosure-body table-wrap">
        <p class="method-note">{escape(metadata['method_note'])}</p>
        <table>
          <thead>
            <tr>
              <th>Trimestre</th><th>RASK (¢)</th><th>CASK (¢)</th><th>Margen (¢)</th>
              <th>ASK (mil M)</th><th>Ocupación</th><th>Pasajeros (M)</th>
            </tr>
          </thead>
          <tbody>{_data_rows(payload)}</tbody>
        </table>
      </div>
    </details>

    <footer class="footer">
      <span>Fuente: comunicados de resultados consolidados en <strong>{escape(metadata['source_view'])}</strong>.</span>
      <span>Corte actualizado al {escape(metadata['data_as_of'])} · Proyecto independiente y no oficial · No es consejo de inversión.</span>
    </footer>
    <p class="sr-only" id="live-status" aria-live="polite"></p>
  </main>

  <script type="application/json" id="dashboard-data">{_safe_json(payload)}</script>
  <script data-runtime="plotly-local">{plotly_js}</script>
  <script data-runtime="executive-prototype">{app_js}</script>
</body>
</html>
"""
    return "\n".join(line.rstrip() for line in document.splitlines()) + "\n"


def write_executive_html(payload: dict[str, Any], output: Path = DEFAULT_OUTPUT) -> Path:
    """Write the generated prototype and return its resolved path."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_executive_html(payload), encoding="utf-8")
    return output.resolve()
