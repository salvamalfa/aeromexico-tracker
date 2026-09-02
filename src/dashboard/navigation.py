"""Single navigation registry shared by Streamlit and dashboard metadata."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable


@dataclass(frozen=True, slots=True)
class PageSpec:
    """Business and routing metadata for one dashboard page."""

    module_name: str
    title: str
    icon: str
    url_path: str
    business_question: str
    default: bool = False


PAGE_SPECS: tuple[PageSpec, ...] = (
    PageSpec("resumen", "Resumen ejecutivo", "🏠", "resumen", "¿Cómo le fue este trimestre?", True),
    PageSpec("economia_unitaria", "Economía unitaria", "↔️", "economia-unitaria", "¿Gana o pierde por unidad de capacidad?"),
    PageSpec("capacidad_demanda", "Capacidad y demanda", "📈", "capacidad-demanda", "¿La oferta crece al ritmo de la demanda?"),
    PageSpec("competencia", "Competencia", "🧭", "competencia", "¿Cómo se posiciona frente a sus comparables?"),
    PageSpec("red_rutas", "Red y rutas", "🗺️", "red-rutas", "¿Dónde vuela y qué tan concentrada está la red?"),
    PageSpec("finanzas", "Finanzas", "💼", "finanzas", "¿Qué dicen resultados, balance y mercado?"),
    PageSpec("forecast", "Forecast", "🔭", "forecast", "¿Qué sugiere la historia y con qué incertidumbre?"),
    PageSpec("lenguaje_reportes", "Lenguaje de reportes", "💬", "lenguaje", "¿Cómo cambia el tono de los reportes?"),
    PageSpec("salud_datos", "Salud de datos", "🩺", "salud-datos", "¿Qué tan confiable y reciente es la evidencia?"),
    PageSpec("estructura_datos", "Estructura de datos", "🧬", "estructura-datos", "¿Cómo se convierte una fuente pública en una decisión?"),
    PageSpec("glosario", "Glosario", "📚", "glosario", "¿Qué significa cada KPI y cómo debe leerse?"),
)


def render_callable(spec: PageSpec) -> Callable[[], None]:
    """Load a page lazily so the registry remains the single navigation source."""

    module = import_module(f"src.dashboard.pages.{spec.module_name}")
    return module.render


def validate_navigation() -> None:
    """Reject duplicate routes, modules, defaults, or incomplete page metadata."""

    if len({spec.module_name for spec in PAGE_SPECS}) != len(PAGE_SPECS):
        raise ValueError("Dashboard page module names must be unique")
    if len({spec.url_path for spec in PAGE_SPECS}) != len(PAGE_SPECS):
        raise ValueError("Dashboard URL paths must be unique")
    if sum(spec.default for spec in PAGE_SPECS) != 1:
        raise ValueError("Dashboard navigation requires exactly one default page")
    if any(
        not value.strip()
        for spec in PAGE_SPECS
        for value in (spec.title, spec.url_path, spec.business_question)
    ):
        raise ValueError("Dashboard page metadata cannot be blank")


validate_navigation()
