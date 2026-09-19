# Guía para agentes de desarrollo

Este repositorio construye un dashboard reproducible de Aeroméxico a partir de
fuentes públicas. La prioridad es preservar el significado de cada cifra, su
procedencia y el estado de aprobación humana. Una ejecución técnicamente válida
no autoriza por sí sola a publicar datos nuevos.

## Antes de editar

1. Ejecuta `git status --short --branch` y revisa el diff de los archivos que
   tocarás. Conserva los cambios existentes; no uses `reset`, `checkout`,
   `clean` ni sobrescribas trabajo ajeno.
2. Lee `README.md`, este archivo y el reporte de etapa relacionado en
   `docs/etapas/`. Para trabajo de Vuelos, empieza por
   `docs/etapas/vuelos-pasajeros-traspaso-20260913.md` y sigue sus enlaces.
3. Comprueba la rama y su relación con `origin/master`. No publiques desde una
   rama divergente sin integrar primero la historia remota mediante un PR
   revisable.
4. Busca instrucciones más específicas en el directorio de trabajo. Las
   instrucciones del usuario y los contratos de datos prevalecen sobre
   sugerencias de implementación.

## Entorno y comandos

- Windows y PowerShell son el entorno de referencia.
- Python soportado: 3.13. Usa `.venv\Scripts\python.exe` si el entorno ya está
  creado; `uv run` y `just` son las interfaces documentadas.
- Preparación: `just setup`.
- Suite: `just test` o `.venv\Scripts\python.exe -m pytest`.
- Validación de estructura: `just dashboard-validate`.
- Reconstrucción: `just transform`; para todo el pipeline offline, `just rebuild`.
- Dashboard local: `just dashboard`.

Los comandos con red, cuotas, suscripciones o APIs pagadas requieren una
ejecución deliberada. Implementa primero un `--dry-run` que muestre llamadas,
ventanas, unidades estimadas y destinos de escritura.

## Arquitectura y artefactos autoritativos

- `data/bronze/`: respuestas crudas inmutables y locales. Git solo conserva los
  manifiestos y restatements.
- `data/silver/`: normalización fiel a la fuente, local y regenerable.
- `data/gold/`: extractos públicos y validados que consume el dashboard.
- `data/warehouse.duckdb`: warehouse local regenerable; no se versiona.
- `src/ingest/`, `src/parse/`, `src/transform/`: pipeline de procedencia.
- `src/dashboard/`: payloads, vistas y generadores del dashboard.
- `src/analysis_agent/`: evidencia, cálculo, revisión y publicación controlada.
- `prototypes/`: artefactos HTML generados para revisión.
- `docs/etapas/`: decisiones, resultados, limitaciones y evidencia de cada etapa.

Los insumos privados y regenerables tienen un respaldo separado en
[`salvamalfa/aeromexico-tracker-data`](https://github.com/salvamalfa/aeromexico-tracker-data).
Ese repositorio debe permanecer privado y requiere Git LFS. Un agente con acceso
explícito puede clonarlo, ejecutar `verify_snapshot.py` y restaurarlo sobre un
checkout público con `restore_snapshot.py`. Nunca copies su contenido a un PR
del repositorio público ni asumas que acceso al código implica acceso a los
datos o autorización para publicarlos.

Edita el generador, no solo el HTML generado. El dashboard integrado principal
se produce con `src/analysis_agent/stage18.py::consumer_html` y
`src/analysis_agent/reader_ui.py`; `build_stage11.py` por sí solo no reproduce
la versión integrada. Si cambian fuentes o Vuelos, regenera primero
`python -m src.dashboard.build_flights` y después el artefacto integrado antes
de interpretar una prueba de igualdad como regresión.

## Reglas de significado de datos

- No conviertas un faltante en cero.
- Distingue cifras reportadas, calculadas, inferidas, estimadas y programadas.
- Distingue operador de comercializador/codeshare. En particular, Aerovías de
  México y Aeroméxico Connect no se fusionan si la fuente permite separarlas.
- Distingue vuelos realizados de programación; pasajeros por tramo de
  pasajeros de itinerario; y cifras de Aeroméxico de totales de todas las
  aerolíneas.
- No repartas un agregado entre rutas o aerolíneas sin evidencia. Si se usa un
  modelo, la salida debe declararse estimación y conservar versión, insumos,
  diagnósticos, incertidumbre y reconciliaciones.
- T-100 documenta operaciones observadas del operador/reportante entre México y
  Estados Unidos. No representa la red mundial, codeshares, ingresos ni
  rentabilidad.
- La elegibilidad histórica al corte de 2026-07-13 y el uso retrospectivo en el
  dashboard son decisiones distintas. No cambies una por actualizar la otra.
- `flight_evidence_v1` sigue siendo candidato no aprobado. No lo actives, no
  hagas backfill y no recalcules o publiques modelos automáticamente.

## Vuelos y estimaciones por ruta y aerolínea

Una semilla de frecuencias puede revelar la estructura ruta por aerolínea, pero
no observa pasajeros. Un ajuste a marginales AFAC debe publicarse como
`passengers_estimated`, incluso cuando reconcilie exactamente totales de ruta y
aerolínea. Las celdas de operador único solo pueden llamarse exactas si la
cobertura de la semilla demuestra que no falta otro operador y ambas marginales
usan el mismo universo.

Toda integración de un proveedor pagado debe incluir:

- inventario de endpoints, campos, límites, costo y ventana histórica;
- filtros explícitos de carga, charter, cancelaciones y codeshare;
- crosswalk versionado de aeropuerto, aerolínea y operador;
- conteo y monto AFAC de filas no mapeadas;
- puerta de aceptación de cobertura antes de estimar;
- reconciliación por ruta y por aerolínea al pasajero;
- separación entre contenido crudo sujeto a licencia y obra derivada publicable.

Nunca subas una API key, respuesta cruda o copia ligeramente reformateada de un
proveedor a GitHub. Revisa los términos vigentes del proveedor el día de la
captura. En el caso de AeroDataBox, `docs/cloud-development.md` documenta la
frontera actual.

## Analysis Agent y aprobación

`analysis_runs/` contiene el estado autoritativo de borradores, aprobaciones y
publicaciones, y está ignorado en el repositorio público. Existe una copia en el
respaldo privado para continuidad y recuperación. No fabriques una aprobación a
partir del HTML ni cambies el estado del Analysis Agent para hacer pasar una
prueba. Restaurar el expediente permite reproducir su estado; no concede por sí
solo autorización para aprobar o republicar un análisis.

No publiques el dashboard, no hagas push a `master`, no actives evidencia y no
consumas una API pagada salvo que el usuario lo haya pedido explícitamente.

## Criterio de cierre

Antes de entregar:

1. Regenera todos los artefactos afectados desde sus fuentes.
2. Ejecuta pruebas focalizadas y luego la suite completa cuando el cambio toca
   pipeline, warehouse, generadores o contratos.
3. Ejecuta `git diff --check` y revisa `git status` para no incluir secretos,
   temporales ni cambios ajenos.
4. Documenta en `docs/etapas/` qué cambió, por qué, cómo se validó y qué límites
   permanecen.
5. Reporta por separado código preparado, datos activados, aprobación y
   publicación. Ninguno implica automáticamente los otros.
