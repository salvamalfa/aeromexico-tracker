# Changelog

Cambios notables del proyecto, para humanos. Formato inspirado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); no se usa
versión semántica, las entradas van por fecha.

## 2026-09-27

### Changed

- Los agentes del proyecto tienen autorización permanente para completar
  cambios rutinarios solicitados: implementación, PR, merge, publicación en
  Pages y verificación final. `AGENTS.md` define las puertas y las acciones de
  mayor riesgo que siguen requiriendo autorización específica. Detalle en
  [`docs/etapas/flujo-agentes-punta-a-punta-20260927.md`](docs/etapas/flujo-agentes-punta-a-punta-20260927.md).

### Fixed

- Los gráficos de Economía unitaria ahora se ajustan al abrir la pestaña. El
  cambio usa la instancia local de Plotly, corrige gráficos estrechos o
  desbordados y valida que cada SVG ocupe el ancho de su contenedor. Detalle en
  [`docs/etapas/ajuste-graficos-economia-20260927.md`](docs/etapas/ajuste-graficos-economia-20260927.md).

- El diagnóstico de etapa 12 registra un hash del contenido lógico del
  warehouse en vez de los bytes del archivo, así que un warehouse restaurado
  del respaldo privado ya no falla la prueba de reproducibilidad.

- `just rebuild` ya no borra los cuatro derivados privados de AeroDataBox: los
  lleva al checkout limpio como insumos, así que el warehouse reconstruido
  conserva la red nacional estimada. `validate_stage9` acepta el registro de
  41 pasos. Las pruebas de la guarda de rutas ya no dependen del Bronze local.
  Detalle en
  [`docs/etapas/rebuild-datos-privados-20260927.md`](docs/etapas/rebuild-datos-privados-20260927.md).

- Vuelos: el total de vuelos de la red cuenta solo vuelos observados; los
  programados (slots del AICM, anuncio fechado de OMA) y los inferidos de
  mercado AFAC van en líneas aparte. Las rutas con presencia documentada sin
  volumen atribuible se declaran como N/D en vez de desaparecer en silencio.
  Además, la región seleccionada se limpia al pasar a un trimestre sin rutas
  de esa región, y el mapa recalcula su recorte al redimensionar la ventana.
  Detalle en
  [`docs/etapas/vuelos-total-red-codex-20260927.md`](docs/etapas/vuelos-total-red-codex-20260927.md).

- Rutas internacionales: las bandas de ocupación fuera de [0, 100%] se omiten igual que en las nacionales.

- Cinco hallazgos abiertos de Codex (PRs #10, #19, #20): capacidad "Boeing
  737" genérica corregida a su punto medio real (175.1, no 175.7); rango de
  sensibilidad de ocupación acotado a [0, 100%] en vez de publicar valores
  como 103.41%; suma de mínimos/máximos de pasajeros a través de celdas con
  distintos escenarios de sensibilidad del IPF ya no infla el rango por
  ruta/red — se retiene solo cuando ningún componente requirió reparación
  temporal; la mezcla trimestral de pasajeros/ASM/RPM exige los tres meses
  no nulos y finitos en vez de sumar con `NaN` silencioso; y
  `build_warehouse` falla en vez de omitir en silencio el Gold de extensión
  de rutas cuando su bronce fuente está presente pero el generador no corrió.

- Tres hallazgos de Codex sobre el PR anterior: el cliente web ya no
  fabricaba una banda de sensibilidad cuando `passengers_low/high` o
  `load_factor_low/high` llegaban como `null` (sustituía el punto o cero);
  la guarda de bronce de `fact_aifa_shared_route_presence` incluía un
  documento que ese generador no lee. Detalle y validación en
  [`docs/etapas/correcciones-codex-estimaciones-20260927.md`](docs/etapas/correcciones-codex-estimaciones-20260927.md).

## 2026-09-26

### Changed

- Remediación de la auditoría de arquitectura (R1–R5): endurecimiento del
  gate de publicación (`src/publish`) contra registros duplicados del mismo
  periodo; exportación de análisis reescrita para aislar cada periodo con
  intercambio atómico ([PR #59](https://github.com/salvamalfa/aeromexico-tracker/pull/59));
  trazabilidad y documentación corregidas ([PR #60](https://github.com/salvamalfa/aeromexico-tracker/pull/60));
  dependencias de `web/` actualizadas para reducir avisos de `npm audit`
  ([PR #61](https://github.com/salvamalfa/aeromexico-tracker/pull/61)); limpieza
  de archivos y código muerto de la migración
  ([PR #62](https://github.com/salvamalfa/aeromexico-tracker/pull/62)).
- Republicación de `site/` para 2T26 con un `code_commit` resoluble en el
  manifiesto de publicación (expediente y aprobación sin cambios, versión de
  análisis `186ba823`) ([PR #64](https://github.com/salvamalfa/aeromexico-tracker/pull/64)).
- Reglas de PR para agentes documentadas en `AGENTS.md`: autorización
  permanente para suscribirse a la actividad de sus PRs y fusionarlos con
  checks verdes e hilos atendidos, incluida la política de auto-merge
  ([PR #66](https://github.com/salvamalfa/aeromexico-tracker/pull/66),
  [PR #67](https://github.com/salvamalfa/aeromexico-tracker/pull/67)).

### Removed

- Migración a Vite + TypeScript completada (P0–P8): `web/` es ahora la única
  implementación del dashboard, publicada en GitHub Pages
  (<https://salvamalfa.github.io/aeromexico-tracker/>); la app Streamlit y el
  consumidor HTML de una sola página se retiraron por completo (detalle
  histórico en `docs/archivo/migracion-2026-09/`).

## 2026-09-19 a 2026-09-25

### Added

- Estimador de pasajeros por ruta y aerolínea nacional (IPF) con evidencia de
  cobertura de semilla y publicación como `passengers_estimated`
  (`docs/estimacion-pasajeros-ruta-aerolinea.md`).
- Integración de AeroDataBox para vuelos internacionales: semilla de
  frecuencias, crosswalks de aeropuerto/aerolínea/puerta, captura mensual y
  estimación de capacidad/ocupación del Grupo Aeroméxico.
- Corrección de portabilidad del Analysis Agent entre Windows y Linux
  (decodificación de referencias de control C1 en HTML de la SEC,
  `src/parse/sec/common.py::html_text`).

## Antes de 2026-09-19

Ver `docs/etapas/` (trabajo vigente) y `docs/archivo/etapas/` (reportes de
etapa 0–18 y de la app retirada) para el detalle completo de cada entrega
desde el inicio del proyecto (agosto de 2026).
