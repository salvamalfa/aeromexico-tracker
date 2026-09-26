# `src/analysis_agent`

Evidencia, cálculo, revisión humana y publicación controlada del análisis
narrativo trimestral (etapas 12–18). Es el único camino autorizado para que un
análisis entre al HTML publicado.

## Responsabilidad

- Evidencia y expediente por trimestre (`evidence.py`, `flight_evidence.py`).
- Cálculo cuantitativo trazable (`quantitative.py`) y su prototipo
  (`stage15_html.py`).
- Redacción/revisión asistida (`analyst.py`, `stage13*.py`, `stage16_html.py`,
  `stage17_html.py`).
- **Ledger de aprobación** (`lifecycle.py`): registro local de solo apéndice
  en `analysis_runs/` (local, no versionado) que autoriza qué versión de un
  análisis puede publicarse.
- **Publicación** (`stage18.py::consumer_html`/`publish`): ensambla el HTML
  integrado final (lectura ejecutiva + análisis aprobado + Vuelos vía
  `src/dashboard/flights.py` y `flights_html.py`) y lo reemplaza de forma
  atómica y verificada por hash. `reader_ui.py` maqueta el resultado
  (pestañas, KPIs, panel de Vuelos).

No ejecutes `stage18 publish` ni cambies un registro de `lifecycle.py` sin una
instrucción explícita del dueño (ver `CLAUDE.md`, `AGENTS.md`).

## Entradas / salidas

- **Entradas:** `data/gold/`, `analysis_runs/` (expediente local), payloads de
  `src/dashboard/`.
- **Salidas:** el HTML integrado publicado (fuera de este repo salvo la copia
  en `static/`, ver `REPO_MAP.md`) y los recibos de publicación en
  `analysis_runs/publications/` (local).

## Puntos de entrada

- `python -m src.analysis_agent.stage18 --record … --output …` (publicación;
  requiere expediente autorizado y aprobación humana).
- Etapas individuales vía `just stage12-*` … `just stage16-*` en el
  `justfile`.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_stage17_lifecycle.py tests/test_stage18_integration.py tests/test_stage18_literal_contract.py
```
