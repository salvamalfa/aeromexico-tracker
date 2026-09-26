"""Repo hygiene budget: no Python module grows past its size limit, and (as
of P4a) no web/ JS module either.

See docs/arquitectura/auditoria-arquitectura-20260926.md §4.3: modulo
Python <= 600 lineas, modulo JS (web/src/**/*.js) <= 400 lineas, con una
lista explicita de excepciones vigentes que solo puede reducirse, nunca
crecer.
"""

from __future__ import annotations

from pathlib import Path

BUDGET = 600
JS_BUDGET = 400

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories whose Python files are excluded from the walk entirely:
# environments, caches and third-party/generated trees, not project code.
EXCLUDED_DIR_NAMES = {
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}

# Current offenders, with the exact line count recorded the last time this
# test was updated. A listed file may shrink (or leave the list entirely)
# but must never grow past the count recorded here, and it may never exceed
# BUDGET by more than what is already on record.
ALLOWLIST: dict[str, int] = {
    "src/analytics/international_route_carrier.py": 1404,
    "src/dashboard/structure_metadata.py": 957,
    "src/transform/stage9_lineage.py": 950,
    "src/transform/validate_stage9.py": 867,
    "src/transform/stage9.py": 812,
    "src/parse/afac/monthly_stats.py": 809,
    "src/analytics/route_carrier.py": 783,
    "src/transform/stage6_facts.py": 772,
    "src/ingest/aerodatabox/international.py": 715,
    "src/dashboard/flights.py": 701,
    "src/dashboard/international_routes.py": 638,
    "src/parse/peers/stage5.py": 625,
    "tests/test_international_route_carrier.py": 622,
}


def _line_count(path: Path) -> int:
    with path.open("rb") as stream:
        return sum(1 for _ in stream)


def _tracked_python_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        if EXCLUDED_DIR_NAMES & set(relative.parts):
            continue
        files.append(relative)
    return sorted(files)


def test_no_untracked_file_exceeds_the_line_budget():
    violations = []
    for relative in _tracked_python_files():
        key = relative.as_posix()
        if key in ALLOWLIST:
            continue
        lines = _line_count(REPO_ROOT / relative)
        if lines > BUDGET:
            violations.append(f"{key}: {lines} lineas (limite {BUDGET})")
    assert not violations, (
        "Modulos nuevos o no listados que exceden el presupuesto de "
        f"{BUDGET} lineas; divide el modulo o agregalo a ALLOWLIST con "
        "justificacion en tests/test_repo_budgets.py:\n" + "\n".join(violations)
    )


def test_allowlisted_files_have_not_grown():
    grown = []
    missing = []
    for key, recorded in ALLOWLIST.items():
        path = REPO_ROOT / key
        if not path.exists():
            missing.append(key)
            continue
        lines = _line_count(path)
        if lines > recorded:
            grown.append(f"{key}: {lines} lineas (registradas {recorded})")
    assert not missing, (
        "Archivos en ALLOWLIST que ya no existen; quitalos de la lista:\n" + "\n".join(missing)
    )
    assert not grown, (
        "Archivos de la lista de excepciones que crecieron; redúcelos o, si "
        "el crecimiento es intencional y justificado, actualiza el conteo "
        "registrado en ALLOWLIST junto con la justificación:\n" + "\n".join(grown)
    )


def _tracked_js_files() -> list[Path]:
    files = []
    for path in (REPO_ROOT / "web" / "src").rglob("*.js"):
        relative = path.relative_to(REPO_ROOT)
        if EXCLUDED_DIR_NAMES & set(relative.parts):
            continue
        files.append(relative)
    return sorted(files)


def test_no_js_module_exceeds_the_line_budget():
    violations = [
        f"{relative.as_posix()}: {lines} lineas (limite {JS_BUDGET})"
        for relative in _tracked_js_files()
        if (lines := _line_count(REPO_ROOT / relative)) > JS_BUDGET
    ]
    assert not violations, (
        "Modulos web/src/**/*.js que exceden el presupuesto de "
        f"{JS_BUDGET} lineas; divide el modulo (ver web/README.md):\n" + "\n".join(violations)
    )
