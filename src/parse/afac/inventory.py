"""AFAC source inventory generated from the explicit observation cutoff."""

from pathlib import Path


def write_inventory(through_month=6, database=None) -> Path:
    from pypdf import PdfReader

    from src.parse.afac.monthly_stats import (
        PATHS,
        _format_family,
        _latest_annual_workbook,
        _metadata,
        _sheet_names,
    )

    """Write the reproducible AFAC source and format-family inventory."""

    lines = [
        "# Inventario de fuentes AFAC",
        "",
        "Inventario generado a partir de la capa bronze. La serie anual oficial de gob.mx",
        f"está completa para 1992–2025; DATATUR aporta boletines mensuales 2024M01–2026M{through_month:02d}",
        f"y una base larga 2016M01–2026M{through_month:02d}. Todos los archivos tienen SHA-256 y metadatos",
        "inmutables en `data/bronze/_manifest.jsonl`.",
        "",
        "## Familias de formato",
        "",
        "| Familia | Periodos | Rasgos | Uso en silver |",
        "|---|---|---|---|",
        "| `legacy_biff_wide` | 1992–2008 | `.xls`, hojas PAX/PAS por servicio, bloques apilados y meses en columnas | Fixture y archivo histórico; no entra al corte analítico 2015+ |",
        "| `biff_wide_plus_hours` | 2009 | Agrega hojas de horas | Inventariada |",
        "| `biff_wide_plus_operational` | 2010–2011 | Agrega OPREG/OPFLET en formato largo | Inventariada |",
        "| `ooxml_wide_plus_operational` | 2012–2016 | Migración a `.xlsx`; PAX ancho y operación larga | Pasajeros desde 2015 |",
        "| `ooxml_summary_plus_operational` | 2017–2019 | Incorpora hoja Resumen | Pasajeros |",
        "| `ooxml_with_revision_history` | 2020–2024 | Incorpora historial explícito de revisiones | Pasajeros |",
        "| `ooxml_modern` | 2025 | Misma topología moderna; sin hoja de revisiones en la descarga actual | Pasajeros preliminares |",
        f"| `datatur_monthly_bulletin_pdf` | 2024M01–2026M{through_month:02d} | Tablas mensuales, participación y notas de estimación | Canónico para vuelos regulares 2026 |",
        f"| `datatur_long_database` | 2016M01–2026M{through_month:02d} | Una fila por mes/mercado/servicio/región/aerolínea | Canónico para fletamento 2026; solape usado para QA |",
        "",
        "## Archivos",
        "",
        "| Periodo | Archivo bronze | Formato | Tamaño (bytes) | Hojas/páginas | Descargado | Método | Familia |",
        "|---|---|---|---:|---|---|---|---|",
    ]
    for year in range(1992, 2026):
        path = _latest_annual_workbook(year)
        metadata = _metadata(path)
        sheets = ", ".join(_sheet_names(path))
        lines.append(
            f"| {year} | `{path.relative_to(PATHS.bronze).as_posix()}` | {path.suffix[1:]} | "
            f"{path.stat().st_size:,} | {sheets} | Sí | {metadata['download_method']} | `{_format_family(year)}` |"
        )
    for year in range(2024, 2027):
        for month in range(1, 13):
            if (year, month) > (2026, through_month):
                break
            directory = PATHS.bronze / "afac" / str(year) / f"{month:02d}"
            pdf = next(directory.glob("*.pdf"), None)
            if pdf is None:
                lines.append(
                    f"| {year}M{month:02d} | — | pdf | — | — | No | — | `datatur_monthly_bulletin_pdf` |"
                )
                continue
            metadata = _metadata(pdf)
            page_count = len(PdfReader(pdf).pages)
            lines.append(
                f"| {year}M{month:02d} | `{pdf.relative_to(PATHS.bronze).as_posix()}` | pdf | "
                f"{pdf.stat().st_size:,} | {page_count} páginas | Sí | {metadata['download_method']} | `datatur_monthly_bulletin_pdf` |"
            )
    database = database or max(
        (PATHS.bronze / "afac" / "database" / "extracted").glob("*.xlsx"),
        key=lambda item: item.stat().st_mtime_ns,
    )
    database_metadata = _metadata(database)
    lines.append(
        f"| 2016M01–2026M{through_month:02d} | `{database.relative_to(PATHS.bronze).as_posix()}` | xlsx | "
        f"{database.stat().st_size:,} | AFAC | Sí | {database_metadata['download_method']} | `datatur_long_database` |"
    )
    lines.extend(
        [
            "",
            "## Precedencia de fuentes",
            "",
            "- 2015–2025: libros anuales oficiales AFAC, porque conservan bloques y filas TOTAL.",
            "- 2026 vuelos regulares: boletín mensual DATATUR/AFAC del mismo periodo.",
            "- 2026 fletamento: base larga DATATUR, ya que el boletín no publica ese desglose.",
            "- Los solapes no se concatenan: se usan para detectar revisiones y diferencias de versión.",
            "",
        ]
    )
    target = PATHS.root / "docs" / "afac-inventario.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
