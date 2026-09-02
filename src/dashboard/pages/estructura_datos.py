"""Interactive, metadata-driven explanation of the tracker data structure."""

from __future__ import annotations

import hashlib
import logging

import streamlit as st

from src.config import PATHS
from src.dashboard.components.ui import page_header, source_note
from src.dashboard.structure_html import render_structure_html
from src.dashboard.structure_metadata import (
    PUBLIC_VALIDATION_RECEIPT,
    build_structure_metadata,
)


LOGGER = logging.getLogger(__name__)


def _metadata_fingerprint() -> str:
    paths = [
        PATHS.root / "config" / "source_catalog.yaml",
        PATHS.root / "config" / "silver_schema_contracts.yaml",
        PATHS.root / "config" / "gold_schema_contracts.yaml",
        PATHS.root / "src" / "pipeline" / "registry.py",
        PATHS.root / "src" / "dashboard" / "navigation.py",
        PATHS.root / "src" / "dashboard" / "structure_metadata.py",
        PATHS.root / "src" / "dashboard" / "structure_html.py",
        PATHS.root / "src" / "dashboard" / "structure_presentation.py",
        PATHS.root / "src" / "dashboard" / "assets" / "data_structure.css",
        PATHS.root / "src" / "dashboard" / "assets" / "data_structure.js",
        PATHS.root / "src" / "parse" / "profiles" / "aeromexico.yaml",
        PATHS.root / "tests" / "fixtures" / "sec" / "earnings_2026Q1.htm",
        PATHS.root / "tests" / "fixtures" / "sec" / "earnings_2026Q2.htm",
        PUBLIC_VALIDATION_RECEIPT,
        *sorted((PATHS.root / "sql" / "gold").glob("*.sql")),
        *sorted(PATHS.gold.glob("*.parquet")),
    ]
    state = "\n".join(
        f"{path.relative_to(PATHS.root).as_posix()}:{path.stat().st_size}:{path.stat().st_mtime_ns}"
        for path in paths
    )
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


@st.cache_data(show_spinner=False)
def _structure_document(fingerprint: str) -> tuple[dict[str, object], str]:
    del fingerprint
    metadata = build_structure_metadata()
    return metadata, render_structure_html(metadata)


def render() -> None:
    page_header(
        "Estructura de datos",
        "¿Cómo se convierte una fuente pública en evidencia comparable, análisis y una decisión de negocio?",
        eyebrow="10 · Del origen a la decisión",
    )
    try:
        metadata, document = _structure_document(_metadata_fingerprint())
    except Exception:
        LOGGER.exception("Stage 10 structure metadata validation failed")
        st.error(
            "La metadata de arquitectura no superó su validación. La página no "
            "mostrará un diagrama parcial o inventado."
        )
        st.stop()

    summary = metadata["summary"]
    st.caption(
        f"Corte validado: {summary['active_public_sources']} fuentes públicas activas "
        f"({summary['sources']} definiciones catalogadas) · "
        f"{summary['artifacts']:,} artefactos · "
        f"{summary['silver_tables']} datasets Silver · "
        f"{summary['gold_tables']} tablas Gold · "
        f"{summary['lineage_coverage']:.0%} de linaje declarado."
    )
    st.html(document, unsafe_allow_javascript=True)
    source_note(
        "Catálogo de fuentes, registro central, contratos Silver/Gold, SQL semántico "
        "y catálogo de navegación. La página no descarga datos ni entrena modelos al abrirse."
    )
