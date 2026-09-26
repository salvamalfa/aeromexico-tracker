# Archivo

Material histórico. No lo leas salvo que la tarea lo requiera explícitamente
(depurar una decisión pasada, reconstruir el porqué de un dato heredado,
auditar la migración). No es lectura de referencia para trabajo normal: el
estado actual vive en `README.md`, `CHANGELOG.md`, `ROADMAP.md` y
`REPO_MAP.md`, en la raíz del repositorio.

Está excluido de búsquedas de agentes (`ripgrep`/`.ignore`) para no ocupar
contexto; sigue siendo legible bajo pedido explícito.

## Contenido

- `migracion-2026-09/`: bitácora completa de la migración a Vite + TypeScript
  y GitHub Pages (paquetes P0–P8) y de la remediación posterior de la
  auditoría (R1–R5, hallazgos A1–A12): `migracion-estado.md` (estado y
  bitácora paquete por paquete) y `auditoria-arquitectura-20260926.md` (el
  plan técnico §4–§5 que originó ambas rondas).
- `auditorias/`: la auditoría de arquitectura anterior (2026-09-01), previa a
  la migración.
- `plan-original/`: el plan de etapas 0–17 tal como se escribió antes de
  ejecutarlo.
- `etapas/`: reportes de cierre de etapa (0–18) y de la migración
  (`migracion-p6b-*`, `migracion-p7-*`, `vuelos-reporte.md`,
  `vuelos-selector-trimestre-*`) cuya sustancia es la app Streamlit o la ruta
  HTML heredada, ya retiradas. Los reportes de etapa con valor metodológico
  vigente (AeroDataBox, AFAC, el estimador ruta×aerolínea, cobertura y
  pasajeros de Vuelos, España, fuentes) siguen en `docs/etapas/`.
