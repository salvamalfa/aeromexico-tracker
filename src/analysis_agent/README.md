# `src/analysis_agent`

Evidencia, cálculo, revisión humana y **publicación controlada** del análisis
narrativo trimestral (etapas 12–17). Es el único camino autorizado para que
un análisis entre a `site/` (via `src/publish/gate.py`).

The ledger and its approval semantics (`lifecycle.py`) are the single
authority for what may reach `site/`; `src/publish/gate.py` re-verifies
against those same functions before exporting or publishing anything.

## Responsabilidad

- Evidencia y expediente por trimestre (`evidence.py`, `flight_evidence.py`).
- Cálculo cuantitativo trazable (`quantitative.py`) y su prototipo
  (`stage15_html.py`).
- Redacción/revisión asistida (`analyst.py`, `stage13*.py`, `stage16_html.py`,
  `stage17_html.py`).
- Importación por entidad (`entity_adapter.py`): cápsulas privadas congeladas,
  originales y metadatos de captura verificados, replay offline de extractores
  revisados y texto exacto. La primera versión admite Viva, Volaris e Industria
  para 2T26; ampliar entidades o periodos exige adaptar y revisar el contrato.
- **Ledger de aprobación** (`lifecycle.py`): registro local de solo apéndice
  en `analysis_runs/` (local, no versionado) que autoriza qué versión de un
  análisis puede publicarse — `consumer_payload(record)` es el paso fail-closed
  que usa `src/publish/gate.py`.

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

## Identidad y promoción por entidad

Los registros nuevos usan `(entity_key, period_id, version)` y viven en
`analysis_runs/drafts/{entity}/{period}/{version}.json`. El formato legado de
Aeroméxico y su ruta publicada se conservan. La auditoría independiente, la
autorización humana y el exportador deben referir la misma identidad exacta.
Cambios de texto, fuentes o implementación invalidan la versión consumible.

La importación toma un lote revisado del respaldo privado:

```bash
uv run python -m src.analysis_agent.entity_adapter --bundle <lote-privado>
```

Importar no aprueba ni publica. Conserva la petición humana real en el ledger,
registra una auditoría independiente de esa versión y aprueba únicamente tras
el resultado favorable. Una petición previa a la auditoría queda pendiente y
se cancela si falla la revisión o cambia la versión. Nunca reconstruyas
autorizaciones desde HTML o desde el estado deseado.

El corte retrospectivo de las nuevas tesis es 2026-10-13; las expectativas
conservan la fecha de sus informes. El panel Industria comprende los tres
grupos, con límites de pasajeros, geografía y contabilidad declarados. El
expediente y las advertencias de revisión permanecen privados; el consumidor
público recibe el texto aprobado y enlaces de fuente, sin cápsulas internas.
