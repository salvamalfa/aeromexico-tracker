# Changelog

Cambios notables del proyecto, para humanos. Formato inspirado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); no se usa
versión semántica, las entradas van por fecha.

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
