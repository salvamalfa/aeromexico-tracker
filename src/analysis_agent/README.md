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

### Aeroméxico financiero · 3T26

`quarterly_release.py` incorpora exclusivamente el trimestre julio–septiembre
de 2026. Reproduce columnas trimestrales del comunicado del emisor, montos
narrativos de mayor precisión y páginas de la presentación. Verifica originales,
recibos de captura, fechas, unidades y huellas antes de cada consumo. La captura
del 21 de octubre es retrospectiva; no demuestra que esos mismos bytes fueran
accesibles el día del reporte. No actualiza Gold ni tráfico mensual.

El [comunicado no auditado del 19 de octubre](https://www.globenewswire.com/fr/news-release/2026/10/19/3383928/0/en/aerom%C3%A9xico-reports-unaudited-third-quarter-2026-results.html),
la [presentación del 20 de octubre](https://ir.aeromexico.com/static-files/1338d53e-2740-4b3a-8d44-cac3ac17d28f)
y el [índice primario](https://ir.aeromexico.com/financial-information/quarterly-results)
respaldan el expediente. Los originales y la auditoría se conservan en el respaldo
privado, separados de los borradores de fuentes de otros hilos.

La redacción pasa por `analyst_v1`; `source_profile: quarterly_release_v1`
vincula su versión a todo el runtime y contratos. Conserva las mismas puertas
de auditoría independiente y consentimiento de la versión exacta del ledger.
El flujo operativo acumulado conserva `period_id: 2026YTD9`; no es un trimestre.

La revisión editorial del 24 de octubre conserva el texto financiero revisado
por el dueño y necesita un expediente nuevo ligado al runtime actual. La extensión
`quarterly_editorial.py` incorpora los originales IR y el tráfico de septiembre
con sus recibos reales, sin actualizar tráfico ni Gold. El ingreso de nueve meses
se extrae de la columna acumulada del comunicado; permanece separado del trimestre.
Las páginas IR sin texto se identifican como `image_page`: su correspondencia
con las afirmaciones exige revisión independiente de sus píxeles. No se fabrica
una transcripción. Las cifras conservan también el linaje del HTML del emisor.

`presentation.py` aplica formatos finitos y compatibles con cada unidad para
preservar literalmente la redacción revisada. No acepta cifras literales nuevas,
formatos arbitrarios ni conversiones entre millas y kilómetros sin cálculo.
La sección administrativa «Pendientes» de la vista de revisión se conserva en el
expediente como sección privada; su aviso de borrador no se publica como estado
actual. Esta adaptación no hereda auditorías ni aprobaciones de otra versión.

Deuda neta y apalancamiento comparan contra diciembre de 2025. La recuperación
de combustible de 113% reportada incluye el ajuste de lealtad de US$48.7m.
Las exclusiones mecánicas de ese ajuste son cálculos ilustrativos propios,
sin presentarlos como métricas normalizadas publicadas ni como efectivo nuevo.
Premium es participación del ingreso de pasajeros de productos y servicios
por encima de Básica/Clásica. TRASM y CASM nativos usan asiento-milla.

```bash
python -m src.analysis_agent.quarterly_release <carpeta-de-capturas-verificada>
```

La carpeta debe contener originales y `captures.json` auténtico con URL, HTTP,
fecha UTC, tamaño y SHA-256. Preparar el paquete no aprueba ni publica nada.
La imagen privada de referencia editorial no se incorpora al sitio.

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
