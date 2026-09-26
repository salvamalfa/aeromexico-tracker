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
| P4b | Front-end en archivos reales: lectura ejecutiva y demás pestañas (fase 3) | fusionado | #51 | — |
| P5 | Vite + TypeScript (fase 4) | fusionado | #52 | — |
| P6a | Citas del análisis exportadas y Vuelos cargado al abrir su pestaña (estado de trimestre único) | fusionado | #53 | — |
| P6b | Gate de publicación sobre `site/`, `verify.py` y workflow de GitHub Pages (fase 5) | fusionado | #54 | — (Pages activo: https://salvamalfa.github.io/aeromexico-tracker/) |
| P7 | Retiro de Streamlit y de la ruta HTML heredada | fusionado | #55 | el dueño borra la app en share.streamlit.io |
| P8a | Aligerar el árbol: `bridge_record_lineage.parquet` con zstd y escritores alineados | fusionado | #56 | — |
| P8b | Reescritura del historial con `git filter-repo` y push forzado (coordinador) | completado | — | — |

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
- 2026-09-26 · P4b fusionado (#51, CI verde). P5 iniciado.
- 2026-09-26 · P5 listo: `web/` en Vite 7 + TypeScript estricto, tipos generados de los contratos, Plotly parcial (se borró el vendorizado de 4.7 MB), 43 pruebas Vitest, build determinista, job `web` en CI. Carga inicial: código 1.42 MB (0.47 MB gzip); con datos, 2.49 MB (0.73 MB gzip) contra 7.2 MB del publicado. **Pendiente menor para P6:** unificar el estado de trimestre de ejecutivo y Vuelos para cargar Vuelos solo al abrir su pestaña (bajaría la carga inicial a menos de 2 MB).
- 2026-09-26 · P5 fusionado (#52, CI `test` y `web` verdes). P6 dividido en P6a (citas y carga diferida de Vuelos) y P6b (gate y Pages). P6a iniciado.
- 2026-09-26 · P6a listo: citas exportadas por la misma vía verificada que stage18, paridad 100 % sin excepciones; estado de trimestre único; Vuelos carga al abrir su pestaña. Carga inicial 1.51 MB (0.49 MB gzip).
- 2026-09-26 · P6a fusionado (#53, CI `test` y `web` verdes). P6b iniciado.
- 2026-09-26 · P6b listo: `src/publish` (gate con la misma verificación que stage18, manifiesto SHA-256, recibo), `verify.py` con 6 pruebas negativas, workflow `pages.yml`, `site/` generado del expediente aprobado 2T26 (34 archivos, ~3.7 MB), paridad con el publicado.
- 2026-09-26 · P6b fusionado (#54, CI verde). P7 iniciado.
- 2026-09-26 · P7 listo: ~28,000 líneas retiradas (app Streamlit, `static/`, `stage18`/`reader_ui`, HTML heredado y sus pruebas, 17 dependencias). Una sola implementación de cada vista (`web/`) y una sola ruta de publicación (`src/publish`). Commit de archivo con Streamlit: `e645d3e` (no se pudo subir etiqueta desde este entorno). CI pública 487 pruebas; locales 62 + 8 de navegador.
- 2026-09-26 · P7 fusionado (#55, CI verde). P8 dividido: P8a (árbol más ligero, PR normal) y P8b (reescritura del historial). P8a iniciado.
- 2026-09-26 · Pages activado por el dueño; despliegue manual correcto; los 34 archivos servidos coinciden byte a byte con el manifiesto.
- 2026-09-26 · P8a listo: todos los Gold se escriben con zstd (`write_parquet_atomic`), 43 tablas reescritas con contenido idéntico comprobado; `data/gold` 92.9 → 51 MB (linaje 61.8 → 32.1 MB). Corregida regresión del mapa (topología fijada, sin peticiones a cdn.plot.ly) y `site/` republicado con el mismo expediente aprobado.
- 2026-09-26 · P8a fusionado (#56, CI verde; hallazgo de Codex sobre escritores Gold internacionales corregido).
- 2026-09-26 · P8b completado: `git filter-repo --strip-blobs-with-ids` quitó los 49 blobs > 1 MB que ya no están en el árbol de `master` (HTML generados, versiones viejas de Parquet, Plotly vendorizado). Árbol final de `master` idéntico (`9981a6d…`). Push forzado de `master` y de las 7 ramas `claude/*`. Clon nuevo: `.git` 173 MB → 76 MB. No se alcanzó la meta de < 40 MB: el árbol vigente ya pesa ~74 MB empaquetado (Gold 51 MB, prototipos del Analysis Agent ~25 MB); bajarlo más exige sacar `bridge_record_lineage.parquet` del árbol público (decisión del dueño). Los clones anteriores deben volver a clonarse. Pages redesplegado; los 34 archivos servidos coinciden con el manifiesto.
- 2026-09-26 · **Migración completa.** Sitio: https://salvamalfa.github.io/aeromexico-tracker/. Publicar: `python -m src.publish --record <expediente aprobado> --out site/` con instrucción explícita del dueño; CI verifica y despliega.
