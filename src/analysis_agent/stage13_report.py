"""Canonical portable report input for the Stage 13 review (no agent narrative)."""
from __future__ import annotations

import json
import duckdb

from src.analysis_agent.stage13 import OUTPUT, LABELS, build
from src.parse.aeromexico_ir_financial import TARGETS


def artifact() -> dict:
    result = build()
    if result["unexplained"]:
        raise ValueError("Resolve extraction differences before rendering")
    title = "Aeroméxico Tracker · Etapa 13 · Cobertura financiera histórica"
    datasets, sources, blocks, tables = {}, [], [], []
    source = {"id": "review", "label": "Diagnóstico financiero de Etapa 13",
              "path": "docs/referencias/etapa-13/financial_review.json",
              "query": {"engine": "Python", "language": "python",
                        "description": "Extraer cifras trimestrales de PDF verificados, conciliar unidades y comparar con la cobertura congelada antes de Etapa 13.",
                        "sql": "from src.analysis_agent.stage13 import build\nreview = build()",
                        "tables_used": ["data/silver/aeromexico_ir_financial_history.parquet", "docs/referencias/etapa-13/baseline.json"],
                        "filters": {"carrier_key": "AEROMEXICO", "period_type": "quarter", "period_range": "2021Q1–2025Q2"}}}
    sources.append(source)
    def md(id, body, source_id=None):
        b = {"id": id, "type": "markdown", "body": body}
        if source_id:
            b["sourceId"] = source_id
        blocks.append(b)
    def table(id, title, rows, cols, source_id="review", sort="period_id"):
        datasets[id] = rows
        tables.append({"id": id, "title": title, "dataset": id, "sourceId": source_id,
                       "defaultSort": {"field": sort, "direction": "asc"},
                       "columns": [{"field": key, "label": label, "type": "text"} for key, label in cols]})
        blocks.append({"id": id + "_block", "type": "table", "tableId": id})
    md("title", "# " + title)
    md("summary", "## Recuperamos el histórico sin mezclar sus definiciones\n\n"
       "Se extrajeron **290 cifras financieras, de costos y consumo, más 9 tipos de cambio**, de **18 reportes oficiales**: 1T21–2T25. "
       "Esto incorpora evidencia financiera de los primeros **14 trimestres** y recupera los documentos propios de otros **cuatro** que ya tenían cifras en la serie vigente.\n\n"
       "Los **252 campos objetivo** (14 métricas × 18 trimestres) tienen una disposición explícita: **214 extraídos** y **38 con una definición distinta o sin desglose separado**. "
       "La revisión incluye **94 conciliaciones** y **64 comparaciones** contra la serie vigente. Tres comparaciones conservan discrepancias documentales verificadas.\n\n"
       "**Entrega de desarrollo para revisión.** Esta página no es un análisis trimestral aprobado y no se incorpora al dashboard. La certificación de publicación y versión corresponde a Etapa 14.", "review")
    md("definition", "## Qué significa la cobertura\n\n"
       "El grano es una métrica de Grupo Aeroméxico consolidado por trimestre, documento y definición. Se seleccionan columnas de **tres meses**, separadas de acumulados y años comparativos. "
       "Los 14 objetivos son ingresos, UAFIDAR ajustada y su margen, resultado y margen operativo, resultado neto, gasto operativo total, combustible, litros, CASK sin combustible, fuerza de trabajo, mantenimiento, depreciación/amortización y renta de equipo.\n\n"
       "**Antes** cuenta los objetivos disponibles en la vista vigente al iniciar esta etapa; **extraídos** cuenta los encontrados en el propio reporte con la definición objetivo. "
       "Las variantes reportadas se conservan y se muestran aparte. Un campo sin definición equivalente no se rellena con una variante ni con cero. Los cuatro trimestres finales ya cubiertos permanecen fuera de esta extracción.")
    md("coverage_heading", "## La extracción amplía los 14 trimestres que carecían de finanzas modeladas\n\n"
       "La gráfica muestra cobertura, no desempeño financiero. Las diferencias entre trimestres reflejan cambios en las definiciones y en el desglose publicado; no indican que un trimestre haya tenido peores resultados.", "review")
    target_sql = ",".join("'" + k + "'" for k in TARGETS)
    coverage_sql = ("SELECT period_id AS period, count(DISTINCT metric_key) AS count "
                    "FROM read_parquet('data/silver/aeromexico_ir_financial_history.parquet') "
                    f"WHERE metric_key IN ({target_sql}) GROUP BY period_id ORDER BY period_id")
    with duckdb.connect() as c:
        datasets["coverage_chart"] = c.execute(coverage_sql).fetchdf().to_dict("records")
    sources.append({"id": "coverage_query", "label": "Conteo de campos objetivo por trimestre",
                    "query": {"engine": "DuckDB", "sql": coverage_sql,
                              "description": "Cuenta métricas objetivo distintas, conservando trimestre y definición.",
                              "tables_used": ["data/silver/aeromexico_ir_financial_history.parquet"]}})
    charts = [{"id": "coverage_chart", "title": "Campos objetivo extraídos por trimestre",
               "subtitle": "Máximo de 14; las variantes se conservan por separado.", "type": "bar",
               "dataset": "coverage_chart", "sourceId": "coverage_query", "valueFormat": "number",
               "encodings": {"x": {"field": "period", "type": "nominal", "label": "Trimestre"},
                             "y": {"field": "count", "type": "quantitative", "label": "Campos"}}}]
    blocks.append({"id": "coverage_plot", "type": "chart", "chartId": "coverage_chart"})
    table("coverage", "Cobertura de los 22 trimestres", result["coverage"], [
        ("period_id", "Trimestre"), ("before", "Antes /14"), ("extracted_targets", "Extraídos /14"),
        ("other_definitions", "Otras cifras"), ("documented_gaps", "Faltantes")])
    md("currency", "## Las monedas y los ajustes permanecen visibles\n\n"
       "**1T21–3T22:** importes en millones de MXN; el equivalente USD mostrado se calcula con el promedio cambiario que publica ese mismo reporte. Es una conversión analítica, no una cifra USD publicada. "
       "**4T22 y 1T23:** el apéndice muestra MXN y USD convertidos por conveniencia a un tipo de cambio de cierre; se conservan ambas columnas. "
       "**Desde 2T23:** el documento declara USD como moneda funcional y de presentación. Esas bases no son intercambiables para comparaciones históricas.\n\n"
       "**4T21 y 1T22:** se separan las columnas sin efectos de reestructura de los resultados contables. El CASK sin combustible de esos dos periodos también excluye efectos de reestructura. "
       "**4T22 y 4T23:** resultados excluyendo PLM se conservan con su propia etiqueta. Hasta 3T22, rentas, depreciación y amortización se publican agrupadas; no se asigna arbitrariamente una parte a cada componente.")
    table("gaps", "Campos sin equivalencia o desglose independiente", [dict(g, metric=LABELS[g["metric_key"]]) for g in result["gaps"]],
          [("period_id", "Trimestre"), ("metric", "Campo objetivo"), ("reason", "Motivo"), ("source_page", "Página")])
    md("differences_heading", "## El reporte propio de 3T24 difiere del comparativo posterior\n\n"
       "El original presenta **195 millones USD** de resultado neto; el comparativo SEC posterior presenta **211 millones**. Con las cifras redondeadas del estado financiero, el resultado antes de impuestos pasa de **254 a 255 millones** y el impuesto de **59 a 44 millones**: esa identidad localiza los **16 millones** de diferencia. "
       "El comunicado posterior no explica el motivo de la revisión.\n\n"
       "El consumo pasa de **461.976 a 461.394 millones de litros** entre documentos: una diferencia de **582 mil litros**, sin causa explícita encontrada en el comunicado posterior. "
       "Las versiones quedan separadas; no se considera un error del parser ni se sustituye la evidencia histórica.\n\n"
       "Las restantes comparaciones admiten los intervalos de redondeo de ambas fuentes. Para CASK, se compara además con el CASM redondeado y convertido de millas a kilómetros. No se fuerza igualdad exacta.", "review")
    comparisons = []
    for c in result["comparison"]:
        row = next(r for r in result["rows"] if r["record_id"] == c["record_id"])
        # Presentation only: monetary values in millions, ratios in percent.
        mult = .000001 if row["value_usd"] is not None else (100 if row["unit_raw"] == "percent" else (.001 if row["unit_raw"] == "thousand liters" else 1))
        unit = "millones USD" if row["value_usd"] is not None else row["unit_raw"]
        comparisons.append(dict(c, metric=LABELS[c["metric_key"]], original=f"{c['ir_value'] * mult:,.4f}",
                                vigente=f"{c['current_value'] * mult:,.4f}", unit=unit))
    table("comparison", "Reporte propio frente a serie vigente · 3T24–2T25", comparisons,
          [("period_id", "Trimestre"), ("metric", "Métrica"), ("original", "Reporte propio"), ("vigente", "Serie vigente"),
           ("unit", "Unidad")])
    md("methods", "## Cada cifra conserva su origen y cada conversión sus insumos\n\n"
       "Los PDF se leen desde Bronze después de comprobar su SHA-256. La extracción combina texto de tablas y apéndices rotados; conserva signo, token original, escala, precisión, página, encabezado y definición. "
       "La tabla Silver guarda unidades publicadas. Las conversiones para esta revisión se calculan aparte y enlazan el registro original con el tipo de cambio extraído del mismo documento.\n\n"
       "Las conciliaciones usan media unidad de la última posición publicada por cada insumo, incluida la precisión del margen y del tipo de cambio cuando corresponde. Se verifican ingresos menos gastos, resultado antes de impuestos menos impuesto, márgenes con definiciones compatibles y columnas USD de conveniencia. "
       "Los apéndices suelen redondear a millones enteros; esa es la precisión de esta extracción, aunque algunos párrafos del comunicado ofrezcan más decimales.")
    md("dossiers", "## Fichas por trimestre\n\n"
       "Cada tabla muestra la cifra tal como fue publicada y su página. «Equivalente USD» solo aplica a importes monetarios y se expresa en millones; los USD de conveniencia no demuestran comparabilidad con USD funcionales. "
       "Los enlaces abren el reporte oficial. La copia local verificada y el texto completo de la página quedan registrados en el expediente reproducible del proyecto.")
    for q in sorted({r["period_id"] for r in result["rows"]}):
        rows = [r for r in result["rows"] if r["period_id"] == q]
        source_id = "ir_" + q
        first = rows[0]
        sources.append({"id": source_id, "label": f"Aeroméxico · comunicado {q}", "href": first["source_url"],
                        "path": "data/bronze/" + first["source_file"],
                        "query": {"description": f"Cifras trimestrales del PDF SHA-256 {first['source_hash']}; localizadores por página y fila. Disponibilidad al corte no certificada.",
                                  "tables_used": ["data/silver/aeromexico_ir_financial_history.parquet"],
                                  "filters": {"period_id": q, "source_hash": first["source_hash"]}}})
        basis = {"mxn_reported": "MXN originales; equivalente USD al promedio publicado.",
                 "usd_convenience_translation": "MXN originales y USD de conveniencia al cierre.",
                 "usd_functional_presentation": "USD como moneda funcional y de presentación."}[first["reporting_basis"]]
        md("heading_" + q, f"### {q} · {basis}\n\n[Ver reporte oficial]({first['source_url']}) · Referencia del archivo: `{first['source_hash'][:16]}`.", source_id)
        display = []
        for r in rows:
            display.append({"metric": LABELS[r["metric_key"]], "original": r["published_token"], "unit": r["unit_raw"],
                            "published": r["published_token"] + " " + r["unit_raw"],
                            "usd": f"{r['value_usd'] / 1e6:,.3f}" if r["value_usd"] is not None else "No aplica",
                            "reported_usd": f"{r['reported_usd_millions']:,.0f}" if r["reported_usd_millions"] is not None else "No hay columna adicional",
                            "definition": r["definition_type"], "page": r["source_page"],
                            "formula": r["normalization_formula"], "fx": str(r["fx_rate_used"] or "No aplica"),
                            "excerpt": r["source_excerpt"], "record_id": r["record_id"], "artifact_id": r["artifact_id"]})
        table("dossier_" + q, f"Cifras y localizadores · {q}", display,
              [("metric", "Métrica"), ("published", "Publicado (unidad original)"), ("usd", "USD (M)"),
               ("page", "Página")], source_id, "metric")
    md("limits", "## Lo que esta etapa permite y lo que sigue pendiente\n\n"
       "La extracción es reproducible desde Bronze y tiene referencias resueltas. Los gastos no desglosados siguen ausentes; los importes ajustados no sustituyen al resultado contable. "
       "La explicación empresarial de las diferencias entre documentos de 3T24 permanece abierta. Recuperar el reporte propio es necesario, pero no acredita aún que la copia descargada hoy sea idéntica a la disponible en su fecha original.\n\n"
       "Las tablas vigentes de Gold y el dashboard conservan sus datos. La nueva evidencia queda en Silver para la futura selección temporal; no se publica automáticamente en el resumen ejecutivo. "
       "La maqueta de Etapa 12 y su alcance visual se mantienen como referencia aprobada.")
    md("next", "## Tu revisión cierra esta etapa\n\n"
       "Revisa las fichas, las conversiones y el tratamiento de variantes y discrepancias. Podemos corregirlos dentro de Etapa 13. "
       "La **Etapa 14** preparará evidencia por fecha de corte y requiere tu autorización explícita. "
       "Quedan como preguntas documentales la prueba de versión original y el motivo de los cambios de 3T24; no se completarán con inferencias del modelo.")
    # Materialize the reviewed display rows and query that exact snapshot for the
    # portable reader's table provenance contract. No hidden database dependency.
    (OUTPUT / "report_tables.json").write_text(json.dumps(datasets, ensure_ascii=False, indent=2), encoding="utf-8")
    for t in tables:
        source = next(s for s in sources if s["id"] == t["sourceId"])
        sql = f"SELECT unnest(\"{t['dataset']}\", recursive := true) FROM read_json_auto('docs/referencias/etapa-13/report_tables.json')"
        with duckdb.connect() as c:
            cursor = c.execute(sql)
            names = [column[0] for column in cursor.description]
            datasets[t["dataset"]] = [dict(zip(names, row)) for row in cursor.fetchall()]
        t["source"] = dict(source, query={"engine": "DuckDB", "sql": sql,
                            "description": "Lectura exacta de filas de revisión producidas por src.analysis_agent.stage13_report; cifras y conversiones proceden del expediente financiero con localizadores.",
                            "tables_used": ["docs/referencias/etapa-13/report_tables.json", "data/silver/aeromexico_ir_financial_history.parquet"]})
        del t["sourceId"]
    return {"surface": "report", "manifest": {"version": 1, "surface": "report", "title": title,
            "description": "Revisión local de desarrollo; no es el análisis trimestral del agente.",
            "sources": sources, "blocks": blocks, "charts": charts, "tables": tables},
            "snapshot": {"version": 1, "status": "ready", "generatedAt": "2026-09-05T13:19:12Z", "datasets": datasets}}


if __name__ == "__main__":
    path = OUTPUT / "artifact.json"
    path.write_text(json.dumps(artifact(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
