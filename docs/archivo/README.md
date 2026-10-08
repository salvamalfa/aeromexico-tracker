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
  ejecutarlo. Ojo: `src/transform/stage6_dimensions.py` todavía lee
  `plan-original/11-glosario-kpis.md`; no lo muevas sin cambiar ese código.
- `etapas/`: reportes de cierre de etapa (0–18) y de la migración
  (`migracion-p6b-*`, `migracion-p7-*`, `vuelos-reporte.md`,
  `vuelos-selector-trimestre-*`) cuya sustancia es la app Streamlit o la ruta
  HTML heredada, ya retiradas, más la validación AFAC contra SEC de la etapa 3
  (`afac-validacion-sec.md`).
- `app-retirada/`: el recorrido narrado de las once páginas de la app anterior.
- `analysis-agent/`: la especificación propuesta de contratos de la etapa 12,
  reemplazada por el código de `src/analysis_agent/` y por
  `docs/analysis-agent/analista-v1.md` y `auditor-v1.md`.
- `referencias/` y `assets/`: referencias y capturas de las etapas 11–18 y de
  la app retirada que ningún documento vigente usa.
- `chat-mvp/` (archivado el 8 oct 2026): construcción del MVP del chat entre el
  3 y el 7 de octubre: reportes `airline-tracker-*`, preparación y
  recuperación del MVP, límites de 8 llamadas, propuesta de la fase 2,
  traspaso Codex→Claude, verificación de data sharing y la comparación de
  hosting (Railway frente a VPS, decidida en
  `docs/decisiones/decision-009-hosting-chat-railway.md`). El estado vigente
  del chat está en `docs/chat/`.
- `vuelos-2026-09/` (archivado el 8 oct 2026): investigación e integración de
  fuentes de Vuelos de septiembre (AFAC, AeroDataBox internacional, Aena,
  AICM, ANAC/Aerocivil/CAA, pilotos de pasajeros) con su evidencia. Su
  contenido metodológico vive en `docs/estimacion-pasajeros-ruta-aerolinea.md`;
  el punto de entrada de Vuelos sigue siendo
  `docs/etapas/vuelos-pasajeros-traspaso-20260913.md`.
- `mantenimiento-2026-09/` (archivado el 8 oct 2026): correcciones y tareas
  puntuales ya cerradas (CI, reconstrucción con datos privados, vista previa
  `/v2/`, entrega del repo de datos privados, flujo de agentes, gráficos de
  economía). Sus reglas vigentes están en `AGENTS.md`, `REPO_MAP.md` y
  `docs/cloud-development.md`.

La regla para archivar está en `AGENTS.md`, sección «Ciclo de vida de la
documentación».
