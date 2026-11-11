"""Genera figuras de documentación desde los artefactos públicos, sin entrenar modelos.

Uso: python scripts/render_documentation_visuals.py
Necesita Matplotlib y Pillow. No usa red, navegador ni almacén local.
"""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_PATH = ROOT / "models/stage7_0c0cf3cf5cbe8226"
MONTHS = ("", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def period_label(period: str) -> str:
    """Convierte el periodo mensual del artefacto en una etiqueta española."""
    year, month = period.split("M")
    return f"{MONTHS[int(month)]} {year}"


def load_evaluation() -> tuple[dict, list[dict]]:
    """Comprueba que ambas barras describen la misma evaluación retenida."""
    metadata = json.loads((RUN_PATH / "metadata.json").read_text(encoding="utf-8"))
    performance = json.loads((RUN_PATH / "performance.json").read_text(encoding="utf-8"))
    if metadata["config"]["target"] != "AEROMEXICO/passengers_afac/total/month":
        raise ValueError("La figura sólo admite el objetivo mensual AFAC de Aeroméxico")
    if metadata["performance_split"] != "test" or metadata["selected_model"] != "sarima":
        raise ValueError("Cambió el modelo o la partición: revisar el guion de la figura")
    rows = []
    for model, metadata_key in (
        ("seasonal_naive", "baseline_test_smape"),
        (metadata["selected_model"], "selected_test_smape"),
    ):
        matches = [row for row in performance if row["model_name"] == model]
        if len(matches) != 1:
            raise ValueError(f"Se esperaba un resultado único para {model}")
        row = matches[0]
        if (
            row["model_run_id"] != metadata["model_run_id"]
            or row["carrier_key"] != "AEROMEXICO"
            or row["metric_key"] != "passengers_afac"
            or row["evaluation_split"] != "test"
            or row["observations"] != metadata["config"]["test_periods"]
            or not math.isfinite(row["smape"])
            or not 0 <= row["smape"] <= 2
            or not math.isclose(row["smape"], metadata[metadata_key], rel_tol=1e-12)
        ):
            raise ValueError(f"La evaluación de {model} no coincide con sus metadatos")
        rows.append(row)
    if rows[0]["observations"] != 12 or metadata["config"]["horizon"] != 12:
        raise ValueError("Cambió el soporte temporal: revisar el texto explicativo")
    return metadata, rows


def render_evaluation(output_dir: Path) -> None:
    """Dibuja métricas ya calculadas; nunca invoca el modelo ni el almacén local."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    metadata, rows = load_evaluation()
    values = [row["smape"] * 100 for row in rows]
    start, end = (period_label(period) for period in metadata["test_window"])
    matplotlib.rcParams.update(
        {"font.family": "DejaVu Sans", "svg.fonttype": "none", "svg.hashsalt": "airlines-tracker-docs"}
    )
    figure = plt.figure(figsize=(12, 6.5), dpi=100, facecolor="white")
    axis = figure.add_axes((0.27, 0.38, 0.64, 0.37))
    axis.barh([1, 0], values, height=0.48, color=["#94A3B8", "#1D4ED8"], zorder=3)
    axis.set_yticks([1, 0], ["Referencia estacional", "SARIMA seleccionado"], fontsize=14.5)
    axis.set_xlim(0, max(values) * 1.25)
    axis.set_xticks([0, 1, 2, 3, 4])
    axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g} %"))
    axis.tick_params(axis="both", length=0, pad=13, labelcolor="#334155", labelsize=14)
    axis.set_xlabel("sMAPE (%) · menor es mejor", fontsize=14, color="#334155", labelpad=18)
    axis.grid(axis="x", color="#E2E8F0", zorder=0)
    for spine in axis.spines.values():
        spine.set_visible(False)
    for position, value in zip([1, 0], values, strict=True):
        axis.text(
            value + 0.09, position, f"{value:.2f} %".replace(".", ","),
            va="center", fontsize=18, weight="bold", color="#0F172A",
        )
    figure.text(
        0.05, 0.91, "Pronóstico mensual: evaluación fuera de muestra",
        fontsize=21, weight="bold", color="#0F172A",
    )
    figure.text(
        0.05, 0.85, f"Aeroméxico · pasajeros AFAC · prueba: {start} a {end}",
        fontsize=14.5, color="#475569",
    )
    figure.text(
        0.05, 0.22, "Se predice un mes y se amplía la historia en cada paso: 12 observaciones.",
        fontsize=13.5, color="#334155",
    )
    figure.text(
        0.05, 0.16, "El horizonte futuro es de 12 meses; este error no mide la precisión a 12 meses.",
        fontsize=13.5, color="#334155",
    )
    figure.text(
        0.05, 0.08, f"Fuente: {metadata['model_run_id']}/performance.json · corte observado: {end}",
        fontsize=10.5, color="#64748B",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_dir / "evaluacion-pronostico.png", metadata={"Software": "Airlines Tracker"})
    figure.savefig(output_dir / "evaluacion-pronostico.svg", metadata={"Date": None})
    plt.close(figure)
    svg_path = output_dir / "evaluacion-pronostico.svg"
    svg = svg_path.read_text(encoding="utf-8")
    svg = svg.replace('<svg ', '<svg role="img" aria-labelledby="title desc" ', 1)
    root_end = svg.index(">", svg.index("<svg ")) + 1
    description = (
        f"SARIMA: {values[1]:.2f} % de sMAPE; referencia estacional: {values[0]:.2f} %. "
        f"Prueba de {start} a {end}, con 12 predicciones mensuales de un paso. "
        "Este resultado no mide el error del horizonte futuro de doce meses."
    )
    accessible_text = (
        '<title id="title">Evaluación del pronóstico mensual de pasajeros de Aeroméxico</title>'
        f'<desc id="desc">{html.escape(description)}</desc>'
    )
    svg = svg[:root_end] + accessible_text + svg[root_end:]
    svg = "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"
    svg_path.write_text(svg, encoding="utf-8", newline="\n")


def render_data_flow(output_dir: Path) -> None:
    """Escribe el diagrama editable del recorrido implementado en el repositorio."""
    output_dir.mkdir(parents=True, exist_ok=True)
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1010"
    viewBox="0 0 1200 1010" role="img" aria-labelledby="title desc">
  <title id="title">Airlines Tracker: de las fuentes públicas al análisis y al panel</title>
  <desc id="desc">La ingesta conserva originales Bronze y sus hashes.
  La normalización produce Silver; la integración valida Gold.
  Gold alimenta la analítica y la exportación.
  Los datos publicados abastecen al panel y a las herramientas del chat.
  Algunas fuentes requieren descarga asistida. Bronze, Silver y DuckDB son locales;
  el chat consulta la versión publicada, no el almacén local.</desc>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8.4" refY="5"
      markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748B"/>
    </marker>
    <style>
      text { font-family:Arial,Helvetica,sans-serif; fill:#0F172A; }
      .title { font-size:32px; font-weight:700; }
      .sub { font-size:21px; fill:#475569; }
      .label { font-size:26px; font-weight:700; }
      .body { font-size:21px; fill:#334155; }
      .small { font-size:19px; fill:#475569; }
      .flow { fill:none; stroke:#64748B; stroke-width:2.8; marker-end:url(#arrow); }
      .node { stroke:#CBD5E1; stroke-width:1.5; rx:16; }
    </style>
  </defs>
  <rect width="1200" height="1010" fill="white"/>
  <text x="48" y="55" class="title">Airlines Tracker</text>
  <text x="48" y="91" class="sub">Fuentes públicas, controles y salidas</text>

  <rect x="48" y="127" width="1104" height="113" class="node" fill="#F8FAFC"/>
  <text x="74" y="165" class="label">Fuentes públicas</text>
  <text x="74" y="199" class="body">Reportes de aerolíneas · SEC / BMV · AFAC / BTS · datos económicos</text>
  <text x="74" y="224" class="small">Descargas automáticas y capturas asistidas, según la fuente</text>

  <path d="M 218 240 V 276" class="flow"/>
  <rect x="48" y="283" width="340" height="131" class="node" fill="#FFF7ED"/>
  <text x="73" y="323" class="label">1. Ingesta</text>
  <text x="73" y="359" class="body">Bronze: originales + SHA-256</text>
  <text x="73" y="389" class="small">src/ingest/</text>

  <path d="M 389 348 H 423" class="flow"/>
  <rect x="430" y="283" width="340" height="131" class="node" fill="#F8FAFC"/>
  <text x="455" y="323" class="label">2. Normalización</text>
  <text x="455" y="359" class="body">Silver: tipos y unidades</text>
  <text x="455" y="389" class="small">src/parse/</text>

  <path d="M 771 348 H 805" class="flow"/>
  <rect x="812" y="283" width="340" height="131" class="node" fill="#EFF6FF"/>
  <text x="837" y="323" class="label">3. Integración</text>
  <text x="837" y="359" class="body">Gold: tablas validadas</text>
  <text x="837" y="389" class="small">src/transform/</text>

  <rect x="48" y="447" width="1104" height="59" rx="12" fill="#F0FDF4" stroke="#BBF7D0"/>
  <text x="600" y="484" text-anchor="middle" class="body">
    Contratos, conciliaciones y linaje · si falla un control obligatorio, el flujo se detiene</text>

  <path d="M 982 414 V 430 H 1174 V 528 H 218 V 552" class="flow"/>
  <path d="M 600 528 V 552" class="flow"/>
  <rect x="48" y="560" width="340" height="145" class="node" fill="#F5F3FF"/>
  <text x="73" y="600" class="label">Analítica</text>
  <text x="73" y="636" class="body">Pronósticos y agrupación</text>
  <text x="73" y="665" class="body">de rutas; evaluación temporal</text>
  <text x="73" y="690" class="small">src/analytics/</text>

  <rect x="430" y="560" width="340" height="145" class="node" fill="#EFF6FF"/>
  <text x="455" y="600" class="label">Exportación</text>
  <text x="455" y="636" class="body">Datos para la interfaz</text>
  <text x="455" y="665" class="body">y publicación verificada</text>
  <text x="455" y="690" class="small">src/web_export/ + src/publish/</text>

  <text x="837" y="588" class="body">Las salidas analíticas</text>
  <text x="837" y="619" class="body">también se guardan en Gold.</text>
  <text x="837" y="654" class="small">Su exposición en la interfaz</text>
  <text x="837" y="681" class="small">es selectiva.</text>

  <path d="M 600 705 V 735 H 982 V 762" class="flow"/>
  <path d="M 600 735 V 762" class="flow"/>
  <rect x="430" y="770" width="340" height="137" class="node" fill="#F8FAFC"/>
  <text x="455" y="810" class="label">Panel web</text>
  <text x="455" y="846" class="body">Indicadores, rutas y lecturas</text>
  <text x="455" y="879" class="small">web/ · Vite + TypeScript</text>

  <rect x="812" y="770" width="340" height="137" class="node" fill="#F8FAFC"/>
  <text x="837" y="810" class="label">Chat con herramientas</text>
  <text x="837" y="846" class="body">Consulta los datos publicados</text>
  <text x="837" y="879" class="small">El modelo redacta con fuentes.</text>

  <text x="48" y="949" class="small">
    Bronze, Silver y DuckDB son locales. Los extractos Gold públicos se versionan.</text>
  <text x="48" y="978" class="small">
    El chat consulta una versión verificada del sitio; no abre el almacén local.</text>
</svg>
'''
    (output_dir / "flujo-datos.svg").write_text(svg, encoding="utf-8", newline="\n")


def render_static_summaries(output_dir: Path) -> None:
    """Reúne los pasos del diagrama sin superponer los pies y controles variables."""
    from PIL import Image, ImageChops

    for name, diagram_height in (("anatomia-chat", 490), ("anatomia-herramientas", 461)):
        with Image.open(output_dir / f"{name}-recorrido.gif") as animation:
            complete = animation.convert("RGB")
            for frame in range(1, animation.n_frames):
                animation.seek(frame)
                complete = ImageChops.darker(complete, animation.convert("RGB"))
            # Los diagramas ocupan una región fija en estas dos animaciones retenidas.
            # Se descartan sólo los controles y textos que cambian en cada paso.
            complete.crop((0, 0, animation.width, diagram_height)).save(
                output_dir / f"{name}-resumen.png", optimize=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--flow-only", action="store_true", help="Generar sólo el diagrama SVG, sin dependencias gráficas",
    )
    args = parser.parse_args()
    render_data_flow(ROOT / "docs/assets/architecture")
    if not args.flow_only:
        render_evaluation(ROOT / "docs/assets/analytics")
        render_static_summaries(ROOT / "docs/assets/chat")
    print("Figuras de documentación generadas desde el código y los artefactos versionados.")


if __name__ == "__main__":
    main()
