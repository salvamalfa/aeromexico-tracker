"""Offline validation for public editorial candidates, separate from approvals."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "contracts/editorial/airline-monthly.schema.json"
ISSUES = ROOT / "config/monthly/issues"
SOURCE_HOSTS = {
    "ir.aeromexico.com", "investorcloud.s3.amazonaws.com",
    "filemanager-cdn.mziq.com",
}


def validate_issue(path: Path) -> dict:
    issue = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(issue)
    cutoff = date.fromisoformat(issue["cutoff"])
    month = date.fromisoformat(issue["id"] + "-01")
    if month.replace(day=1) >= cutoff.replace(day=1):
        raise ValueError("La edición debe corresponder a un mes completo anterior al corte")
    sources = {source["id"]: source for source in issue["sources"]}
    if len(sources) != len(issue["sources"]):
        raise ValueError("ID de fuente duplicado")
    for source in sources.values():
        url = urlparse(source["url"])
        if url.scheme != "https" or url.hostname not in SOURCE_HOSTS or url.username or url.password or url.port:
            raise ValueError("Fuente fuera de los dominios públicos revisados")
        if not date.fromisoformat(source["published"]) <= date.fromisoformat(source["accessed"]) <= cutoff:
            raise ValueError("Fecha de fuente posterior a la consulta o al corte")
    sections = [section["id"] for section in issue["sections"]]
    if sections != ["senales", "analisis", "rutas", "resultados", "agenda"]:
        raise ValueError("Faltan secciones de la edición o cambió su orden")
    for section in issue["sections"]:
        for story in section["stories"]:
            for claim in story["claims"]:
                if claim["kind"] != "limite" and not claim["sources"]:
                    raise ValueError("Afirmación sin fuente")
                if set(claim["sources"]) - sources.keys():
                    raise ValueError("Afirmación con fuente inexistente")
    airlines = [row["airline"] for row in issue["traffic"]]
    if sorted(airlines) != ["Aeroméxico", "Viva", "Volaris"]:
        raise ValueError("Debe haber una fila única para cada compañía")
    for row in issue["traffic"]:
        if row["source"] not in sources:
            raise ValueError("Cifra sin fuente existente")
    return issue


def validate_all() -> list[dict]:
    paths = sorted(ISSUES.glob("*.json"), reverse=True)
    if not paths:
        raise ValueError("No hay ediciones para revisar")
    issues = [validate_issue(path) for path in paths]
    if len({issue["id"] for issue in issues}) != len(issues):
        raise ValueError("Edición duplicada")
    if any(path.stem != issue["id"] for path, issue in zip(paths, issues, strict=True)):
        raise ValueError("El archivo no coincide con el periodo de la edición")
    return issues


if __name__ == "__main__":
    print(f"{len(validate_all())} edición(es) editorial(es) válidas; sin aprobación ni publicación")
