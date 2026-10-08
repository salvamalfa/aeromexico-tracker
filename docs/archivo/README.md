# Historia del proyecto

Resumen de los esfuerzos cerrados. Los documentos originales se borraron del
árbol el 8 de octubre de 2026 y siguen disponibles, sin cambios, en el commit
[`7478082`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo):
cada sección enlaza a su carpeta en ese commit. No los restaures al árbol; si
algo de ellos sigue vigente, pásalo a la documentación permanente (ver
`AGENTS.md`, «Ciclo de vida de la documentación»).

Este archivo está excluido de las búsquedas de agentes (`.ignore`). Léelo solo
cuando la tarea lo pida (depurar una decisión pasada o el porqué de un dato).

## Plan original y app anterior (agosto–septiembre de 2026)

- **Plan de etapas 0–17**
  ([`plan-original/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/plan-original)):
  el plan escrito antes de ejecutar el proyecto. Cubría la conectividad y las
  ingestas (SEC EDGAR, BMV XBRL, AFAC, fuentes complementarias, peers), las
  tablas maestras, la analítica, el dashboard, el saneamiento del backend y el
  Analysis Agent (etapas 12–17). Su glosario de KPIs sigue vigente y se movió a
  `docs/glosario-kpis.md`, porque `src/transform/stage6_dimensions.py` lo lee.
- **Reportes de etapa 0–18**
  ([`etapas/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/etapas)):
  el cierre de cada etapa de la app Streamlit y de la ruta HTML heredada
  (`prototypes/etapa-11`), incluida la validación AFAC contra SEC de la etapa 3.
  Las decisiones que sobreviven están en `docs/decisiones/`; los datos, en
  `docs/diccionario-datos.md`.
- **Auditoría de arquitectura del 1 de septiembre**
  ([`auditorias/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/auditorias)):
  aprobó Bronze/Silver/Gold + Parquet + DuckDB y originó la decisión 008.
- **App retirada**
  ([`app-retirada/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/app-retirada)):
  recorrido narrado de las once páginas de la app Streamlit.
- **Referencias y capturas de las etapas 11–18**
  ([`referencias/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/referencias),
  [`assets/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/assets)):
  material de revisión que ningún documento vigente usa. Las referencias que
  genera o lee `src/analysis_agent/` (etapas 12–15 y 17) siguen en
  `docs/referencias/`.
- **Contratos v1 del Analysis Agent**
  ([`analysis-agent/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/analysis-agent)):
  especificación propuesta en la etapa 12, reemplazada por el código de
  `src/analysis_agent/` y por `docs/analysis-agent/analista-v1.md` y
  `auditor-v1.md`.

## Migración a Vite y GitHub Pages (26 de septiembre de 2026)

[`migracion-2026-09/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/migracion-2026-09):
la migración del dashboard de Streamlit a `web/` (Vite + TypeScript) publicado
como `site/` en GitHub Pages, en los paquetes P0–P8, y la remediación de la
auditoría posterior (R1–R5, hallazgos A1–A12). Resultado: `web/` es la única
vista, `src/publish` es la única ruta de publicación y Streamlit se retiró. El
estado vigente está en `REPO_MAP.md` y `web/README.md`.

## Vuelos: investigación e integración de fuentes (septiembre de 2026)

[`vuelos-2026-09/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/vuelos-2026-09):
investigación de cobertura de rutas AFAC, AeroDataBox internacional (sondeo,
crosswalks, capturas de abril a julio, integración y asientos), Aena (España),
slots del AICM, fuentes ANAC/Aerocivil/CAA, el primer estimador IPF y los
pilotos de pasajeros por ruta, con su evidencia y capturas. El método vigente
está en `docs/estimacion-pasajeros-ruta-aerolinea.md` y la entrada a Vuelos en
`docs/etapas/vuelos-pasajeros-traspaso-20260913.md`.

## Construcción del MVP del chat (3–7 de octubre de 2026)

[`chat-mvp/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp):
la implementación inicial del backend, el catálogo semántico, la comparación de
modelos con el holdout, las auditorías y remediaciones, el paso a contraseña, la
reserva de costo, los primeros despliegues en Railway, la preparación y la
recuperación del MVP, el traspaso de Codex a Claude, la verificación de data
sharing y la comparación de hosting (Railway frente a un VPS de Hostinger,
decidida en `docs/decisiones/decision-009-hosting-chat-railway.md`). El estado
vigente está en `docs/chat/` y en los reportes `docs/etapas/chat-*`.

## Mantenimiento cerrado (septiembre–octubre de 2026)

[`mantenimiento-2026-09/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/mantenimiento-2026-09):
correcciones y tareas puntuales: diagnóstico de fuentes, gráficos de
Economía, portabilidad de la publicación, entrega del repositorio de datos
privados, flujo de agentes de punta a punta, CI y dependencias, vista previa
`/v2/` en Pages y reconstrucción con datos privados. Sus reglas vigentes están
en `AGENTS.md`, `REPO_MAP.md` y `docs/cloud-development.md`.
