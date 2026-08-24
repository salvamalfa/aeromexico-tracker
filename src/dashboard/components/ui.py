"""Shared page chrome, empty states, and source notes."""

from __future__ import annotations

import html

import streamlit as st

from src.config import PATHS
from src.dashboard.data import data_as_of


def load_css() -> None:
    css = (PATHS.root / "src" / "dashboard" / "assets" / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def page_header(title: str, question: str, *, eyebrow: str) -> None:
    st.markdown(
        f"<div class='page-hero'><div class='eyebrow'>{html.escape(eyebrow)}</div>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(question)}</p></div>",
        unsafe_allow_html=True,
    )


def source_note(text: str) -> None:
    st.caption(f"Fuente y alcance: {text}")


def unavailable(title: str, reason: str) -> None:
    st.info(f"**{title}.** {reason}")


def render_footer() -> None:
    st.markdown(
        f"<div class='dashboard-footer'><strong>Datos al {data_as_of()}</strong> · "
        "Proyecto independiente y no oficial. No es consejo de inversión. "
        "Solo usa información pública y gratuita.</div>",
        unsafe_allow_html=True,
    )
