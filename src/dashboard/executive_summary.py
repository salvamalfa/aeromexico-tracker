"""Source-backed presentation model for the Stage 11 executive prototype."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Any

import duckdb
import pandas as pd

from src.config import PATHS


EXECUTIVE_QUERY = """
SELECT
    period_id,
    passengers,
    ask_km,
    load_factor_reported,
    rask_cents_per_km,
    cask_cents_per_km,
    unit_margin_cents_per_km
FROM v_aeromexico_quarterly
WHERE passengers IS NOT NULL
  AND ask_km IS NOT NULL
  AND load_factor_reported IS NOT NULL
  AND rask_cents_per_km IS NOT NULL
  AND cask_cents_per_km IS NOT NULL
  AND unit_margin_cents_per_km IS NOT NULL
ORDER BY period_id
"""

REQUIRED_COLUMNS = (
    "period_id",
    "passengers",
    "ask_km",
    "load_factor_reported",
    "rask_cents_per_km",
    "cask_cents_per_km",
    "unit_margin_cents_per_km",
)

KPI_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "key": "rask_cents_per_km",
        "label": "RASK",
        "description": "Ingreso total generado por cada asiento-kilómetro disponible.",
        "accent": "blue",
        "format": "cents",
    },
    {
        "key": "cask_cents_per_km",
        "label": "CASK",
        "description": "Costo operativo por cada asiento-kilómetro disponible.",
        "accent": "red",
        "format": "cents",
    },
    {
        "key": "ask_km",
        "label": "ASK",
        "description": "Capacidad ofrecida: asientos disponibles multiplicados por kilómetros.",
        "accent": "gold",
        "format": "billions",
    },
    {
        "key": "load_factor_reported",
        "label": "Factor de ocupación",
        "description": "Porcentaje de la capacidad que fue utilizada por pasajeros.",
        "accent": "amber",
        "format": "percent",
    },
    {
        "key": "passengers",
        "label": "Pasajeros",
        "description": "Pasajeros transportados por Grupo Aeroméxico en el trimestre.",
        "accent": "violet",
        "format": "millions",
    },
)


@dataclass(frozen=True, slots=True)
class Comparison:
    """One typed period comparison for a KPI card."""

    available: bool
    raw: float | None
    display: str
    direction: str


def _finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Executive metric is not finite: {value!r}")
    return number


def _period_label(period_id: str) -> str:
    year, quarter = int(period_id[:4]), int(period_id[-1])
    return f"{quarter}T{year % 100:02d}"


def _previous_quarter(period_id: str) -> str:
    year, quarter = int(period_id[:4]), int(period_id[-1])
    if quarter == 1:
        return f"{year - 1}Q4"
    return f"{year}Q{quarter - 1}"


def _previous_year(period_id: str) -> str:
    return f"{int(period_id[:4]) - 1}{period_id[4:]}"


def _direction(value: float | None, *, tolerance: float = 1e-12) -> str:
    if value is None:
        return "na"
    if value > tolerance:
        return "up"
    if value < -tolerance:
        return "down"
    return "flat"


def _percent_comparison(current: float, previous: float | None) -> Comparison:
    if previous is None or previous == 0:
        return Comparison(False, None, "No disponible", "na")
    value = current / previous - 1
    return Comparison(True, value, f"{value:+.1%}", _direction(value))


def _point_comparison(current: float, previous: float | None) -> Comparison:
    if previous is None:
        return Comparison(False, None, "No disponible", "na")
    value = (current - previous) * 100
    return Comparison(True, value, f"{value:+.1f} pp", _direction(value, tolerance=0.005))


def _cent_comparison(current: float, previous: float | None) -> Comparison:
    if previous is None:
        return Comparison(False, None, "No disponible", "na")
    value = current - previous
    return Comparison(True, value, f"{value:+.2f} ¢", _direction(value, tolerance=0.005))


def _display_value(value: float, kind: str) -> str:
    if kind == "cents":
        return f"{value:.2f} ¢"
    if kind == "billions":
        return f"{value / 1_000_000_000:.2f} mil M"
    if kind == "millions":
        return f"{value / 1_000_000:.2f} M"
    if kind == "percent":
        return f"{value:.1%}"
    raise ValueError(f"Unsupported KPI format: {kind}")


def _comparison_for(
    metric_key: str,
    current: float,
    previous: float | None,
) -> Comparison:
    if metric_key == "load_factor_reported":
        return _point_comparison(current, previous)
    return _percent_comparison(current, previous)


def _change_phrase(
    label: str,
    comparison: Comparison,
    *,
    unavailable: str,
    plural: bool = False,
) -> str:
    if not comparison.available:
        return unavailable
    verbs = (
        {"up": "aumentaron", "down": "disminuyeron", "flat": "se mantuvieron estables"}
        if plural
        else {"up": "aumentó", "down": "disminuyó", "flat": "se mantuvo estable"}
    )
    display = comparison.display.lstrip("+-")
    return f"{label} {verbs[comparison.direction]} {display}"


def _validate_history(frame: pd.DataFrame) -> None:
    missing = set(REQUIRED_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Executive source is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Executive source has no complete comparable quarters")
    if frame["period_id"].isna().any() or frame["period_id"].duplicated().any():
        raise ValueError("Executive source must have one unique row per quarter")
    if frame[list(REQUIRED_COLUMNS[1:])].isna().any().any():
        raise ValueError("Executive source contains a partial comparable quarter")
    if not frame["period_id"].astype(str).str.fullmatch(r"\d{4}Q[1-4]").all():
        raise ValueError("Executive source contains an invalid quarter identifier")
    for column in REQUIRED_COLUMNS[1:]:
        frame[column].map(_finite)
    if (frame[["passengers", "ask_km", "rask_cents_per_km", "cask_cents_per_km"]] <= 0).any().any():
        raise ValueError("Executive source contains a non-positive business metric")
    if not frame["load_factor_reported"].between(0, 1).all():
        raise ValueError("Executive load factor must be stored as a fraction")
    calculated = frame["rask_cents_per_km"] - frame["cask_cents_per_km"]
    if not (calculated - frame["unit_margin_cents_per_km"]).abs().le(1e-9).all():
        raise ValueError("Executive unit margin does not reconcile to RASK - CASK")


def load_executive_history(database_path: str | None = None) -> pd.DataFrame:
    """Read complete comparable quarters from the canonical DuckDB view."""

    path = str(PATHS.warehouse if database_path is None else database_path)
    with duckdb.connect(path, read_only=True) as connection:
        frame = connection.execute(EXECUTIVE_QUERY).df()
    _validate_history(frame)
    return frame.sort_values("period_id").reset_index(drop=True)


def _data_as_of(database_path: str | None = None) -> str:
    path = str(PATHS.warehouse if database_path is None else database_path)
    with duckdb.connect(path, read_only=True) as connection:
        value = connection.execute(
            "SELECT MAX(CAST(downloaded_at AS DATE)) FROM dim_source_artifact"
        ).fetchone()[0]
    if value is None:
        return "sin fecha"
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        value = pd.Timestamp(value).date()
    months = ("", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
    return f"{value.day:02d} {months[value.month]} {value.year}"


def _record_dict(row: pd.Series) -> dict[str, float | str]:
    return {
        "period_id": str(row["period_id"]),
        "period_label": _period_label(str(row["period_id"])),
        **{column: _finite(row[column]) for column in REQUIRED_COLUMNS[1:]},
    }


def _period_view(
    record: dict[str, float | str],
    records_by_period: dict[str, dict[str, float | str]],
) -> dict[str, Any]:
    period_id = str(record["period_id"])
    prior = records_by_period.get(_previous_quarter(period_id))
    prior_year = records_by_period.get(_previous_year(period_id))

    kpis: list[dict[str, Any]] = []
    for definition in KPI_DEFINITIONS:
        key = definition["key"]
        current_value = float(record[key])
        qoq = _comparison_for(
            key,
            current_value,
            None if prior is None else float(prior[key]),
        )
        yoy = _comparison_for(
            key,
            current_value,
            None if prior_year is None else float(prior_year[key]),
        )
        kpis.append(
            {
                **definition,
                "value": current_value,
                "display_value": _display_value(current_value, definition["format"]),
                "qoq": qoq.__dict__ if hasattr(qoq, "__dict__") else {
                    "available": qoq.available,
                    "raw": qoq.raw,
                    "display": qoq.display,
                    "direction": qoq.direction,
                },
                "yoy": yoy.__dict__ if hasattr(yoy, "__dict__") else {
                    "available": yoy.available,
                    "raw": yoy.raw,
                    "display": yoy.display,
                    "direction": yoy.direction,
                },
            }
        )

    margin = float(record["unit_margin_cents_per_km"])
    previous_margin = None if prior is None else float(prior["unit_margin_cents_per_km"])
    yoy_margin = None if prior_year is None else float(prior_year["unit_margin_cents_per_km"])
    margin_qoq = _cent_comparison(margin, previous_margin)
    margin_yoy = _cent_comparison(margin, yoy_margin)

    by_key = {item["key"]: item for item in kpis}
    capacity_qoq = Comparison(**by_key["ask_km"]["qoq"])
    passengers_qoq = Comparison(**by_key["passengers"]["qoq"])
    load_qoq = Comparison(**by_key["load_factor_reported"]["qoq"])
    rask_qoq = Comparison(**by_key["rask_cents_per_km"]["qoq"])
    cask_qoq = Comparison(**by_key["cask_cents_per_km"]["qoq"])

    conclusions = [
        (
            f"El margen unitario fue {margin:.2f} ¢ por ASK-km; "
            + (
                f"cambió {margin_qoq.display} frente al trimestre anterior."
                if margin_qoq.available
                else "no existe un trimestre previo comparable en la serie validada."
            )
        ),
        (
            _change_phrase("La capacidad", capacity_qoq, unavailable="La capacidad abre la serie comparable")
            + "; "
            + _change_phrase(
                "los pasajeros",
                passengers_qoq,
                unavailable="no hay comparación previa de pasajeros",
                plural=True,
            )
            + "."
        ),
        (
            _change_phrase("El RASK", rask_qoq, unavailable="El RASK no tiene comparable previo")
            + "; "
            + _change_phrase("el CASK", cask_qoq, unavailable="el CASK no tiene comparable previo")
            + "."
        ),
    ]

    if load_qoq.available:
        conclusions[1] += f" La ocupación cambió {load_qoq.display}."

    if margin_qoq.available:
        if margin_qoq.direction == "down":
            headline = "El costo unitario presionó el margen del trimestre."
        elif margin_qoq.direction == "up":
            headline = "El margen unitario mejoró frente al trimestre anterior."
        else:
            headline = "El margen unitario se mantuvo estable."
    else:
        headline = "Primer trimestre completo de la serie comparable."

    if prior_year is None:
        year_context = "La comparación interanual todavía no está disponible para este punto de la serie validada."
    else:
        year_context = (
            f"Frente a {_period_label(_previous_year(period_id))}, el margen cambió "
            f"{margin_yoy.display}, con RASK {by_key['rask_cents_per_km']['yoy']['display']} "
            f"y CASK {by_key['cask_cents_per_km']['yoy']['display']}."
        )

    narrative = {
        "headline": headline,
        "paragraphs": [
            (
                f"{record['period_label']} registró RASK de {float(record['rask_cents_per_km']):.2f} ¢, "
                f"CASK de {float(record['cask_cents_per_km']):.2f} ¢ y un margen unitario de {margin:.2f} ¢ por ASK-km."
            ),
            (
                f"La compañía ofreció {float(record['ask_km']) / 1_000_000_000:.2f} mil millones de ASK, "
                f"transportó {float(record['passengers']) / 1_000_000:.2f} millones de pasajeros y reportó "
                f"{float(record['load_factor_reported']):.1%} de ocupación."
            ),
            year_context,
        ],
    }

    return {
        "period_id": period_id,
        "period_label": record["period_label"],
        "kpis": kpis,
        "conclusions": conclusions,
        "narrative": narrative,
        "margin_qoq": {
            "available": margin_qoq.available,
            "raw": margin_qoq.raw,
            "display": margin_qoq.display,
            "direction": margin_qoq.direction,
        },
        "margin_yoy": {
            "available": margin_yoy.available,
            "raw": margin_yoy.raw,
            "display": margin_yoy.display,
            "direction": margin_yoy.direction,
        },
    }


def build_executive_payload(database_path: str | None = None) -> dict[str, Any]:
    """Build the complete deterministic payload used by HTML and future Streamlit."""

    history = load_executive_history(database_path)
    records = [_record_dict(row) for _, row in history.iterrows()]
    records_by_period = {str(record["period_id"]): record for record in records}
    views = {
        period_id: _period_view(record, records_by_period)
        for period_id, record in records_by_period.items()
    }
    correlation = float(
        history["load_factor_reported"].corr(history["rask_cents_per_km"])
    )
    if correlation >= 0.7:
        correlation_label = "Correlación positiva clara: mayor ocupación tiende a coincidir con mayor RASK."
    elif correlation >= 0.3:
        correlation_label = "Correlación positiva moderada: mayor ocupación suele coincidir con mayor RASK."
    elif correlation > -0.3:
        correlation_label = "La relación entre ocupación y RASK es débil en la historia disponible."
    else:
        correlation_label = "La historia disponible muestra una relación inversa entre ocupación y RASK."
    return {
        "metadata": {
            "title": "Aeroméxico — Vista ejecutiva trimestral",
            "default_period": str(records[-1]["period_id"]),
            "first_period": str(records[0]["period_id"]),
            "last_period": str(records[-1]["period_id"]),
            "quarter_count": len(records),
            "coverage_label": (
                f"{len(records)} trimestres comparables · "
                f"{records[0]['period_label']}–{records[-1]['period_label']}"
            ),
            "data_as_of": _data_as_of(database_path),
            "source_view": "v_aeromexico_quarterly",
            "grain": "Grupo Aeroméxico · trimestre calendario · segmento total",
            "load_rask_correlation": correlation,
            "load_rask_interpretation": correlation_label,
            "method_note": (
                "En 1T21–3T22, Aeroméxico publicó el ingreso por ASK en pesos; "
                "se convirtió a centavos de USD con el tipo de cambio promedio "
                "publicado en el mismo reporte trimestral."
            ),
        },
        "records": records,
        "views": views,
    }
