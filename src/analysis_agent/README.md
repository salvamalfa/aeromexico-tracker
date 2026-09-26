# `src/analysis_agent`

Evidencia, cálculo, revisión humana y **publicación controlada** del análisis
narrativo trimestral (etapas 12–17). Es el único camino autorizado para que
un análisis entre a `site/` (via `src/publish/gate.py`).

P7 retired `stage18.py`/`reader_ui.py`, the module pair that used to assemble
the legacy single-file integrated HTML (`consumer_html`) and its consumer
publish path — see `docs/arquitectura/migracion-estado.md`. The ledger and
its approval semantics (`lifecycle.py`) are unchanged and unaffected;
`src/publish/gate.py` re-verifies against the exact same functions.

## Responsabilidad

- Evidencia y expediente por trimestre (`evidence.py`, `flight_evidence.py`).
- Cálculo cuantitativo trazable (`quantitative.py`) y su prototipo
  (`stage15_html.py`).
- Redacción/revisión asistida (`analyst.py`, `stage13*.py`, `stage16_html.py`,
  `stage17_html.py`).
- **Ledger de aprobación** (`lifecycle.py`): registro local de solo apéndice
  en `analysis_runs/` (local, no versionado) que autoriza qué versión de un
  análisis puede publicarse — `consumer_payload(record)` is the fail-closed
  handoff both the retired `stage18` and today's `src/publish/gate.py` use.

No cambies un registro de `lifecycle.py` sin una instrucción explícita del
dueño (ver `CLAUDE.md`, `AGENTS.md`). Publicar de verdad es
`python -m src.publish` (ver `src/publish/README.md`), no algo que vive en
este módulo.

## Entradas / salidas

- **Entradas:** `data/gold/`, `analysis_runs/` (expediente local), payloads de
  `src/dashboard/`.
- **Salidas:** el estado del ledger de aprobación (`analysis_runs/`, local).
  El artefacto publicado (`site/`) y sus recibos son responsabilidad de
  `src/publish/`, no de este módulo.

## Puntos de entrada

- Etapas individuales vía `just stage12-*` … `just stage16-*` en el
  `justfile`.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_stage17_lifecycle.py tests/test_stage18_literal_contract.py
```
