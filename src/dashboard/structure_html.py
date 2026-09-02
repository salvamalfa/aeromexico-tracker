"""Escaped, local-only HTML renderer for the data-structure page."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from src.config import PATHS


ROOT_ID = "amx-data-structure-v1"
ROLE_LABELS = {
    "who": "Quién",
    "when": "Cuándo",
    "what": "Qué",
    "where": "Dónde",
    "context": "Contexto",
    "trust": "Confianza",
    "facts": "Hecho",
    "analysis": "Análisis",
}


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _technical_list(values: dict[str, object]) -> str:
    rows = "".join(
        f"<div><dt>{_e(label)}</dt><dd><code>{_e(value)}</code></dd></div>"
        for label, value in values.items()
    )
    return f"<dl class='technical-list'>{rows}</dl>"


def _example_cards(examples: list[dict[str, str]]) -> str:
    if not examples:
        return ""
    cards = "".join(
        "<article class='example-card'>"
        f"<span class='example-kind'>{_e(item['kind'])}</span>"
        f"<div class='example-flow'><code>{_e(item['before'])}</code>"
        "<span aria-hidden='true'>→</span>"
        f"<code>{_e(item['after'])}</code></div>"
        f"<p>{_e(item['explanation'])}</p>"
        f"<small>Evidencia: {_e(item['evidence'])}</small>"
        "</article>"
        for item in examples
    )
    return f"<div class='example-grid'>{cards}</div>"


def _source_details(sources: list[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for source in sources:
        artifact = source["featured_artifact"]
        artifact_link = ""
        artifact_technical = ""
        official_is_artifact = bool(
            artifact is not None and artifact["url"] == source["official_url"]
        )
        if artifact is not None:
            if not official_is_artifact:
                artifact_link = (
                    f"<a class='action-link secondary' data-link-kind='artifact' href='{_e(artifact['url'])}' "
                    "target='_blank' rel='noopener noreferrer'>Abrir archivo fuente</a>"
                )
            artifact_technical = _technical_list(
                {
                    "Archivo Bronze": artifact["source_file"],
                    "Formato": artifact["artifact_format"],
                    "SHA-256": artifact["artifact_sha256"],
                    "Descargado": artifact["downloaded_at"],
                }
            )
        status = "Disponible" if source["artifact_count"] else "Sin artefacto en este corte"
        rendered.append(
            "<section class='source-detail'>"
            "<div class='source-detail-heading'>"
            f"<div><span class='status-pill'>{_e(status)}</span>"
            f"<h5>{_e(source['display_name'])}</h5></div>"
            f"<span class='artifact-count'>{source['artifact_count']:,} artefactos</span>"
            "</div>"
            f"<p>{_e(source['description'])}</p>"
            "<dl class='business-facts'>"
            f"<div><dt>Responsable</dt><dd>{_e(source['institution'])}</dd></div>"
            f"<div><dt>Cobertura</dt><dd>{_e(source['coverage'])}</dd></div>"
            f"<div><dt>Actualización</dt><dd>{_e(source['update_frequency'])}</dd></div>"
            f"<div><dt>Acceso</dt><dd>{_e(source['access_method'])}</dd></div>"
            "</dl>"
            f"<p class='limitation'><strong>Límite:</strong> {_e(source['limitations'])}</p>"
            f"<p class='artifact-note'>{_e(source['artifact_note'])}</p>"
            "<div class='link-row'>"
            f"<a class='action-link' data-link-kind='official' "
            + ("data-featured-artifact='true' " if official_is_artifact else "")
            + f"href='{_e(source['official_url'])}' target='_blank' rel='noopener noreferrer'>"
            + ("Abrir fuente oficial (archivo)" if official_is_artifact else "Ir a la fuente oficial")
            + "</a>"
            f"{artifact_link}</div>"
            f"{artifact_technical}"
            "</section>"
        )
    return "<div class='source-detail-list'>" + "".join(rendered) + "</div>"


def _render_card(card: dict[str, Any]) -> str:
    card_id = _e(card["card_id"])
    details_id = f"{card_id}-panel"
    test_id = "source-card" if card["card_type"] == "source" else "process-card"
    body = (
        _source_details(card["sources"])
        if card["card_type"] == "source"
        else (
            f"<p class='detail-explanation'>{_e(card['explanation'])}</p>"
            + _example_cards(card.get("examples", []))
        )
    )
    body += (
        "<div class='technical-block'><h5>Detalle técnico</h5>"
        + _technical_list(card["technical"])
        + "</div>"
    )
    return (
        f"<article class='info-card' data-testid='{test_id}' data-card-id='{card_id}'>"
        "<div class='card-front'>"
        f"<h4>{_e(card['title'])}</h4>"
        f"<p class='card-summary'>{_e(card['summary'])}</p>"
        "<div class='quick-detail' aria-label='Resumen adicional'>"
        "<dl>"
        f"<div><dt>Responsable</dt><dd>{_e(card['owner'])}</dd></div>"
        f"<div><dt>Cobertura</dt><dd>{_e(card['coverage'])}</dd></div>"
        f"<div><dt>Actualización</dt><dd>{_e(card['update'])}</dd></div>"
        "</dl>"
        "</div>"
        "</div>"
        "<details class='card-details'>"
        f"<summary data-testid='detail-toggle' aria-controls='{details_id}' aria-expanded='false'>"
        "<span>Ver detalle</span><span class='summary-icon' aria-hidden='true'>＋</span>"
        "</summary>"
        f"<div class='detail-panel' id='{details_id}' data-testid='detail-panel'>"
        f"{body}"
        "<button class='close-detail' type='button' data-action='close-details'>Cerrar detalle</button>"
        "</div>"
        "</details>"
        "</article>"
    )


def _render_level(level: dict[str, Any]) -> str:
    cards = "".join(_render_card(card) for card in level["cards"])
    return (
        f"<li class='funnel-level level-{_e(level['level_key'])}' "
        f"data-testid='funnel-level' data-level='{_e(level['level_key'])}'>"
        "<header class='level-header'>"
        f"<span class='level-number'>{int(level['number']):02d}</span>"
        f"<div><h3>{_e(level['title'])}</h3><p>{_e(level['subtitle'])}</p></div>"
        "</header>"
        f"<div class='card-grid'>{cards}</div>"
        "</li>"
    )


def _connector() -> str:
    return (
        "<li class='level-connector' data-testid='level-connector' aria-hidden='true'>"
        "<svg viewBox='0 0 100 76' role='presentation' focusable='false'>"
        "<path d='M50 4 V57'/><path d='M35 45 L50 62 L65 45'/></svg>"
        "</li>"
    )


def _table_detail(table: dict[str, Any]) -> str:
    def listed(values: list[str], empty: str) -> str:
        if not values:
            return f"<span class='empty-value'>{_e(empty)}</span>"
        return "<ul>" + "".join(f"<li><code>{_e(value)}</code></li>" for value in values) + "</ul>"

    pages = table["consumer_pages"]
    page_html = (
        "<ul>" + "".join(f"<li>{_e(value)}</li>" for value in pages) + "</ul>"
        if pages
        else "<span class='empty-value'>No tiene una página directa en el corte actual.</span>"
    )
    return (
        f"<article class='selected-table' data-selected-table='{_e(table['table_name'])}'>"
        "<div class='selected-table-heading'>"
        f"<div><span class='role-pill'>{_e(ROLE_LABELS.get(table['role'], table['role']))}</span>"
        f"<h3>{_e(table['label'])}</h3></div>"
        f"<code>{_e(table['table_name'])}</code>"
        "</div>"
        f"<p>{_e(table['purpose'])}</p>"
        "<div class='table-detail-grid'>"
        f"<section><h4>Entradas relacionadas</h4>{listed(table['inputs'], 'Sin clave foránea de entrada declarada.')}</section>"
        f"<section><h4>Salidas y vistas</h4>{listed(table['outputs'], 'Sin consumidor técnico directo declarado.')}</section>"
        f"<section><h4>Campos principales</h4>{listed(table['main_fields'], 'Sin campos declarados.')}</section>"
        f"<section><h4>Grano</h4>{listed(table['grain'], 'Sin grano declarado.')}</section>"
        f"<section><h4>Páginas consumidoras</h4>{page_html}</section>"
        f"<section><h4>Contrato</h4><code>{_e(table['contract_source'])}</code><p>Etapa {int(table['stage'])}</p></section>"
        "</div>"
        "</article>"
    )


def _render_gold(metadata: dict[str, Any]) -> str:
    gold = metadata["gold"]
    tables = {table["table_name"]: table for table in gold["tables"]}
    dimensions = "".join(
        "<button class='gold-node dimension-node' type='button' "
        f"data-testid='gold-node' data-table='{_e(table['table_name'])}' aria-pressed='false'>"
        f"<span class='business-label'>{_e(table['label'])}</span>"
        f"<span class='technical-label'>{_e(table['table_name'])}</span>"
        "</button>"
        for table in gold["dimension_tables"]
    )
    fact_options = "".join(
        f"<option value='{_e(table['table_name'])}' data-label='{_e(table['label'])}'"
        + (" selected" if table["table_name"] == gold["default_fact"] else "")
        + f">{_e(table['label'])}</option>"
        for table in gold["fact_options"]
    )
    all_options = "".join(
        f"<option value='{_e(table['table_name'])}' data-business-label='{_e(table['label'])}' "
        f"data-technical-name='{_e(table['table_name'])}'>{_e(table['label'])}</option>"
        for table in gold["tables"]
    )
    edge_records = "".join(
        "<span class='gold-edge-record' hidden "
        f"data-parent='{_e(edge['parent'])}' data-child='{_e(edge['child'])}' "
        f"data-label='{_e(', '.join(edge['child_columns']))}'></span>"
        for edge in gold["fk_edges"]
    )
    view_names = {view["name"] for view in gold["views"]}
    table_roles = {table["table_name"]: table["role"] for table in gold["tables"]}
    consumer_records = "".join(
        "<span class='gold-consumer-record' hidden "
        f"data-table='{_e(table['table_name'])}' "
        f"data-views='{_e(' | '.join(value for value in table['outputs'] if value in view_names))}' "
        f"data-analytics='{_e(' | '.join(value for value in table['outputs'] if table_roles.get(value) == 'analysis'))}' "
        f"data-pages='{_e(' | '.join(table['consumer_pages']))}'></span>"
        for table in gold["tables"]
    )
    templates = "".join(
        f"<template data-table-template='{_e(table['table_name'])}'>{_table_detail(table)}</template>"
        for table in gold["tables"]
    )
    default_table = tables[gold["default_fact"]]
    return (
        "<section class='gold-section' id='gold-model' aria-labelledby='gold-title'>"
        "<div class='section-heading'>"
        "<div><span class='section-kicker'>Relaciones dentro de Gold</span>"
        f"<h2 id='gold-title'>Una estrella enfocada, no {_e(metadata['summary']['gold_tables'])} tablas amontonadas</h2>"
        "<p>Elige un hecho: solo se iluminan las dimensiones que su contrato conecta. Las flechas se recalculan con el tamaño real de la pantalla.</p></div>"
        "<button id='tech-toggle' data-testid='tech-toggle' type='button' aria-pressed='false'>Ver nombres técnicos</button>"
        "</div>"
        "<div class='gold-controls'>"
        "<label>Hecho central"
        f"<select id='fact-selector'>{fact_options}</select></label>"
        "<label>Explorar cualquier tabla"
        f"<select id='table-selector'><option value='' data-business-label='Selecciona una tabla…' "
        f"data-technical-name=''>Selecciona una tabla…</option>{all_options}</select></label>"
        "</div>"
        "<div class='gold-map' data-testid='gold-map'>"
        "<div class='gold-column dimension-column'>"
        "<span class='column-label'>Quién · Cuándo · Qué · Dónde</span>"
        f"<div class='dimension-grid'>{dimensions}</div></div>"
        "<div class='gold-column fact-column'>"
        "<span class='column-label'>Qué ocurrió</span>"
        f"<button id='gold-fact-node' class='gold-node fact-node' type='button' data-testid='gold-node' "
        f"data-table='{_e(default_table['table_name'])}' aria-pressed='true'>"
        f"<span class='business-label'>{_e(default_table['label'])}</span>"
        f"<span class='technical-label'>{_e(default_table['table_name'])}</span></button></div>"
        "<div class='gold-column consumer-column'>"
        "<span class='column-label'>Qué consume el negocio</span>"
        "<div id='semantic-node' class='consumer-node'><strong>Vistas semánticas</strong><span></span></div>"
        "<div id='analytics-node' class='consumer-node'><strong>Resultados analíticos</strong><span></span></div>"
        "<div id='pages-node' class='consumer-node'><strong>Páginas de negocio</strong><span></span></div>"
        "</div>"
        f"<div class='edge-records' aria-hidden='true'>{edge_records}{consumer_records}</div>"
        "</div>"
        "<div id='gold-detail' class='gold-detail' data-testid='gold-detail' aria-live='polite' aria-atomic='true'>"
        f"{_table_detail(default_table)}</div>"
        f"<div class='table-templates' hidden>{templates}</div>"
        "</section>"
    )


def render_structure_html(metadata: dict[str, Any]) -> str:
    """Render one escaped document fragment with only local CSS and JavaScript."""

    if len(metadata.get("levels", [])) != 5:
        raise ValueError("Data-structure funnel requires exactly five levels")
    css_path = PATHS.root / "src" / "dashboard" / "assets" / "data_structure.css"
    js_path = PATHS.root / "src" / "dashboard" / "assets" / "data_structure.js"
    css = css_path.read_text(encoding="utf-8")
    script = js_path.read_text(encoding="utf-8")
    level_parts: list[str] = []
    for index, level in enumerate(metadata["levels"]):
        level_parts.append(_render_level(level))
        if index < len(metadata["levels"]) - 1:
            level_parts.append(_connector())
    stats = "".join(
        f"<div><strong>{_e(value)}</strong><span>{_e(label)}</span></div>"
        for label, value in (
            ("fuentes públicas activas", metadata["summary"]["active_public_sources"]),
            ("artefactos preservados", f"{metadata['summary']['artifacts']:,}"),
            ("datasets Silver", metadata["summary"]["silver_tables"]),
            ("tablas Gold", metadata["summary"]["gold_tables"]),
            ("linaje declarado", f"{metadata['summary']['lineage_coverage']:.0%}"),
        )
    )
    provenance = " · ".join(metadata["provenance"])
    return (
        f"<style>{css}</style>"
        f"<div id='{ROOT_ID}' class='aero-structure' data-testid='structure-root' data-theme='light' lang='es'>"
        "<a class='skip-link' href='#structure-funnel'>Saltar al embudo</a>"
        "<section class='structure-intro' aria-labelledby='structure-intro-title'>"
        "<div><span class='section-kicker'>Del documento público a una decisión</span>"
        "<h2 id='structure-intro-title'>La evidencia desciende; la trazabilidad siempre puede subir</h2>"
        "<p>Empieza con lenguaje de negocio. Abre una tarjeta cuando necesites ver archivos, contratos, campos o controles.</p></div>"
        f"<div class='summary-stats'>{stats}</div>"
        "</section>"
        "<nav class='structure-nav' aria-label='Secciones de la estructura'>"
        "<a href='#structure-funnel'>Embudo completo</a><a href='#gold-model'>Relaciones Gold</a>"
        "</nav>"
        "<ol id='structure-funnel' class='structure-funnel' aria-label='Cinco niveles del flujo de datos'>"
        + "".join(level_parts)
        + "</ol>"
        + _render_gold(metadata)
        + "<p class='metadata-note'>Diagrama generado desde metadata validada: "
        + _e(provenance)
        + ". Las etiquetas de presentación no declaran relaciones.</p>"
        + "</div>"
        + f"<script>{script}</script>"
    )
