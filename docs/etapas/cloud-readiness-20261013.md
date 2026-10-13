# Preparación cloud para desarrollo y operación · 13 oct 2026

Alcance: auditoría y preparación, sin cambio funcional ni publicación. Bases:
público `d456eb8`, privado `922a963`. Se conservaron los checkouts originales y
se prepararon ramas/worktrees aislados. Las instrucciones permanentes viven
en `AGENTS.md`, `docs/cloud-development.md` y el README/AGENTS privados.

## Accesos y despliegue

GitHub API y fetch acceden a ambos repositorios; reportan `pull`, `push` y
`admin`. El push de la rama privada se verificó usando el ayudante de la sesión
`gh` existente, solo en el comando: el primer intento carecía de credenciales
para el hook LFS. No se crearon tokens ni se deshabilitaron hooks.
Se confirmó que el respaldo sigue privado. Los 1.900 archivos LFS
están materializados, verificados por SHA-256 y `git lfs fsck`; los once
manifiestos derivados pasan. Se usó la caché LFS existente; no se probó una
descarga remota desde una caché vacía ni se crearon credenciales.

Railway: servicio `aeromexico-tracker`, solo entorno `production`, fuente
`master`, Dockerfile y watch paths acordes al repositorio, volumen `/data`
de 500 MB y ningún cambio staged. Deployment
`93447a36-7477-4382-bea6-d711ead0ad09`: `SUCCESS`; health HTTP 200, worker activo,
`gpt-6.1-sol` / `low`. Se leyeron nombres de variables, ningún valor.
`checkSuites=false` impide confiar en CI como barrera de despliegue de Railway.
La API local de GitHub para listar variables devuelve 403; los pins de prueba
se tomaron de la decisión ya documentada, no de secretos ni de un hash nuevo.

Triggers revisados en las ramas vigentes antes de push: el PR público solo
ejecuta CI; Pages requiere cambios de sitio/configuración preview en `master`
o despacho; las capturas privadas solo tienen despacho manual. No se cambian
triggers, seguridad, flags, infraestructura ni producción.

## Ejecución y datos

Python 3.13.5, `uv` 0.12.19, Node 24.19.0 / npm 11.9.0 (CI usa Node 22),
`just` 1.58.0. Dependencias Python bloqueadas y `npm ci` instalados con cachés
escribibles bajo `/workspace`; Chromium 153.0.8010.12 de Playwright 1.63.0.
La activación existente del cloud no se cargaba automáticamente en la shell.

El warehouse del snapshot antecedía al panel Industria/Viva. La suite inicial
sin navegador, con solo el pin financiero, dio 1.315 pasadas, siete fallos,
14 errores y un skip: seis fallos por pin de evidencia ausente y el resto por
panel Industria incompleto. Se usaron los dos pins aprobados del
[brief en el commit auditado](https://github.com/salvamalfa/aeromexico-tracker/blob/d456eb8dc05e586d7119161c710db5ff47af0da3/docs/chat/fase-2-decision-dueno.md),
solo en procesos locales; se reconstruyó
el warehouse con `build_warehouse(max_stage=9)` desde Gold vigente, sin
regenerar cifras ni modificar aprobaciones. Panel resultante: Industria 14,
Aeroméxico 22, Volaris 15 y Viva 14 trimestres. Export real: 112 archivos.

Los cuatro combinados privados usados por el dashboard se copiaron desde
`derived/` a destinos Gold ignorados. La capacidad nacional combinada difiere
de la copia del snapshot; se conservó el respaldo original. El restaurador
también copiaba dos metadatos de modelos versionados con distinto fin de línea:
se devolvieron los bytes del commit público, tras comprobar igualdad de
contenido. No se incluyen datos privados en el diff.

## Verificación

- TypeScript, 170 tests Vitest y build: pasaron.
- Ruff pyflakes y formato de los dos módulos migrados: pasaron.
- Runtime chat aislado: pasó snapshot, auth, worker y compare_metrics con
  proveedor mock; cero llamadas al proveedor.
- `src.publish.verify site/`: pasó con el pin financiero aprobado.
- `src.dashboard.validate_stage8`: 8/8; la alerta de frescura sigue abierta.
- Línea base de la suite preparada: 1.348 pasadas, dos fallidas, un skip (preview Pages
  no configurada), 29 subtests pasados y cero errores de setup, en 487 s.
  La paridad con el sitio y el panel completo ya pasan. Fallos:
  `test_stage12_diagnosis.py::test_outputs_match_snapshot_and_are_reproducible`
  (fingerprint del warehouse en el HTML guardado desfasado) y
  `test_web_page_smoke.py::test_flights_tab_renders_the_synthetic_fixture`
  (el smoke copia archivos reales del export dentro de su fixture y pide
  `cdn.plot.ly/un/world_110m.json`, rechazado por TLS del cloud).
  Se confirmó que el HTML de Etapa 12 difiere únicamente por un fingerprint.
  La repetición aislada del smoke pasó, pero un control nuevo de requests
  reveló que la topología vacía aún podía pedir el CDN antes de que terminara
  la prueba.

### Correcciones verificadas de la preparación

Se regeneraron `diagnostico.json` y `prototypes/etapa-12/analysis_agent.html`
con `python -m src.analysis_agent.stage12`. Cambió exclusivamente
`input_sha256.warehouse_content`; JSON embebido y JSON canónico coinciden,
CSV y datos permanecen iguales. La prueba conserva comparación byte a byte,
reproducibilidad y comprobación de que warehouse/Gold no se modifican.

Los dos smokes copian el build sin sus exportaciones `data/`; después exportan
únicamente sus fixtures. La topología sintética ahora incluye las capas vacías
válidas que Plotly necesita, y los smokes esperan a que las rutas se dibujen.
El smoke de página falla si se pide cualquier recurso externo. No se simula
éxito de un CDN ni se desactiva TLS.

Pruebas focalizadas de Etapa 12 y los dos módulos smoke: 19 pasadas con el
export real presente en `web/public/data/v1`. El resultado de la suite completa
y de CI sobre el commit final se conserva en el
[PR #130](https://github.com/salvamalfa/aeromexico-tracker/pull/130).
El PR público contiene documentación, código de tests/fixture y dos artefactos
diagnósticos regenerados; no cambia código de producto, Gold, `site/`, contratos
ni workflows. El privado #23 sigue siendo solo documentación.

Playwright/Chromium **del cloud**, sin navegador ni sesión del usuario:
Lectura, Economía y Vuelos del `site/` sin modificar, escritorio 1440 px y
móvil 390 px; sin errores JavaScript ni requests fallidos y sin overflow tras
el resize. Los 131 archivos del manifiesto remoto coinciden por bytes, tamaño
y SHA-256 con la copia inspeccionada. Navegación directa a Pages desde Chromium
falló por `ERR_CERT_AUTHORITY_INVALID` del entorno; se usó HTTPS con la
confianza ya disponible en httpx y la copia local, sin desactivar TLS.

Contraste: KPI 2T26 de Aeroméxico (RASK 9.94, CASK 9.51 ¢ USD, ASK 14.90 mil M)
coinciden con payload y warehouse; ingreso US$1.479 millones y ocupación 84.9 %
coinciden con la captura SEC preservada y su hash. Vuelos conserva sus etiquetas
observado/estimado y la evidencia candidata no se activa. Esta comprobación
no afirma que se descargaron fuentes nuevas.

## Pendientes y límites

- AFAC del Gold/warehouse termina el 30 jun 2026: 105 días frente al umbral
  de 62. Vuelos estimado nacional contiene marzo–julio; no confundir ambas
  coberturas. El refresco mensual requiere un encargo y fuentes revisadas;
  no lo ejecuta automáticamente `refresh.yml`.
- El fingerprint desfasado y la dependencia de red del smoke se corrigen
  arriba, conservando checks estrictos. Antes de integrar, comprobar `test` y
  `web` del head vigente del PR; no sustituir CI final por la de un commit anterior.
- El privado registra que probe/sweep figuran `active` pese a documentar la
  práctica de deshabilitarlos fuera de un despacho; siguen siendo manuales.
  Se conserva su estado durante esta preparación.
- PR borrador [#128](https://github.com/salvamalfa/aeromexico-tracker/pull/128)
  declara Stage 3 entregado y pendiente de ratings del dueño. Se revisó su
  alcance documental, sin editarlo ni verificar esa calificación contra un
  expediente privado posterior al snapshot. No bloquea esta preparación.
- Smoke de chat pagado, nuevas capturas, reinicios/persistencia tras restart,
  aprobaciones y despliegues: no ejecutados en este encargo.

Prueba pública: [dashboard](https://salvamalfa.github.io/aeromexico-tracker/) y
[health](https://aeromexico-tracker-production.up.railway.app/api/chat/health).
Los cambios de esta preparación se entregan en PRs borrador; necesitan aprobación
explícita antes de integrar. No se habilita auto-merge ni publicación.

Una sola aprobación explícita puede autorizar ambos PRs identificando sus
heads finales y el alcance anterior. Sus archivos quedan fuera de los triggers
de Pages y los watch paths de Railway auditados: la integración pública corre
CI y la privada no despacha capturas. Revalidar esos triggers y el diff contra
`master` inmediatamente antes de integrar, por si cambió la base o configuración.
