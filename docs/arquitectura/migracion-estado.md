# Estado de la migración a Vite + TypeScript y GitHub Pages

Fuente única de verdad del avance. Plan técnico:
[`auditoria-arquitectura-20260926.md`](auditoria-arquitectura-20260926.md) §4–§5.

## Cómo retomar

1. `git fetch origin` y revisar la tabla: el primer paquete que no esté en
   **fusionado** es el que sigue.
2. Si tiene PR abierto, leer el PR y su último commit; si está **en curso**,
   continuar desde el último commit de la rama.
3. La sesión principal coordina; cada paquete lo ejecuta el subagente
   `migrador` (`.claude/agents/migrador.md`, Sonnet, esfuerzo medio).
4. Al cambiar de estado, actualizar esta tabla y subirla en el mismo commit.

Rama de trabajo: `claude/aerodata-box-international-7en30g`. Tras cada fusión
se reinicia desde `master`.

## Decisiones del dueño (26 de septiembre de 2026)

- Vite + TypeScript aprobado; Node forma parte del proyecto.
- GitHub Pages reemplaza a Streamlit; la app de Streamlit se retira completa.
- Se reescribe la historia de git para quitar peso (último paquete).
- Subagentes Sonnet en esfuerzo medio; nunca Opus para la ejecución.
- Pasos manuales del dueño: activar Pages (Settings → Pages → Source: GitHub
  Actions) en P6 y borrar la app en share.streamlit.io en P7.

## Paquetes

| Paquete | Alcance | Estado | PR | Siguiente paso |
|---|---|---|---|---|
| P0 | Fusionar #46, republicar el integrado con el total en el panel, tracker y agente | fusionado | #46 | — |
| P1 | Pruebas y CI (auditoría fase 0) | fusionado | #47 | — |
| P2 | Higiene y mapa del repo (fase 1) | fusionado | #48 | — |
| P3 | Contratos de datos y privacidad (fase 2) | fusionado | #49 | — |
| P4a | Front-end en archivos reales: vista Vuelos en `web/` con ES modules y paridad (fase 3) | fusionado | #50 | — |
| P4b | Front-end en archivos reales: lectura ejecutiva y demás pestañas (fase 3) | PR abierto | #51 | revisar CI y fusionar |
| P5 | Vite + TypeScript (fase 4) | pendiente | | |
| P6 | Gate de publicación sobre `site/` y GitHub Pages (fase 5) | pendiente | | |
| P7 | Retiro de Streamlit | pendiente | | |
| P8 | Peso de git y reescritura de historia (fase 6) | pendiente | | |

## Bitácora

- 2026-09-26 · P0 iniciado.
- 2026-09-26 · P0 fusionado (#46). P1 iniciado.
- 2026-09-26 · P1 listo: CI pública 494 pruebas en 34 s sin datos locales; suite local 449 s → 152 s; `build_flight_payload()` 10.5 s → 2.4 s (diferencias de 1 ULP en ocupación por orden de suma). Falla previa: `test_stage12_diagnosis`.
- 2026-09-26 · P1 fusionado (#47, CI verde en 61 s). P2 iniciado.
- 2026-09-26 · P2 listo: REPO_MAP.md, README por paquete, ruff en 4 módulos, presupuesto de 600 líneas (13 excepciones), docs de etapa movidos. CI pública 501 pruebas.
- 2026-09-26 · P2 fusionado (#48, CI verde). P3 iniciado.
- 2026-09-26 · P3 listo: esquemas v1 (flights, executive), privacy.yaml con prueba negativa, exportador `src/web_export` (29 archivos, máx. 634 KB), insumos requeridos en `config/web_inputs.yaml`. CI pública 517 pruebas.
- 2026-09-26 · P3 fusionado (#49, CI verde). P4 dividido en P4a (Vuelos) y P4b (ejecutivo y demás pestañas) para sesiones más cortas. P4a iniciado.
- 2026-09-26 · P4a listo: `web/` con Vuelos en 12 módulos ES (≤ 228 líneas), datos por `fetch`, paridad 100 % contra el publicado (22 trimestres, 4 regiones, MEX/CUN, meses). Implementación duplicada con `flights.js` hasta P5. Plotly 3.7.0 vendorizado temporalmente (4.7 MB).
- 2026-09-26 · P4a fusionado (#50, CI verde). P4b iniciado.
- 2026-09-26 · P4b listo: página completa en `web/` (pestañas, lectura ejecutiva, economía, Vuelos), exportador de análisis de solo lectura vía `consumer_payload`. Paridad 100 % en texto, KPIs y gráficas, salvo las citas en superíndice.
  **Pendiente obligatorio para P6:** las citas (`<sup><a class="source-note">`) salen de `verified_inputs()` y aún no se exportan; P6 debe exportarlas (solo metadatos de fuentes públicas autorizadas) antes del corte a Pages para no perderlas.
