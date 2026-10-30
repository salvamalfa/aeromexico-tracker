# Mapa del repositorio

Cobertura de Vuelos por trimestre, fuentes y límites:
[`docs/etapas/cobertura-vuelos-20261015.md`](docs/etapas/cobertura-vuelos-20261015.md).

Qué vive dónde, comandos clave y recetas paso a paso para los cambios más
comunes. Ver también `CLAUDE.md`, `AGENTS.md`, `CHANGELOG.md` y `ROADMAP.md`.

Para diseñar los siguientes lotes de datos, ver el
[catálogo de fuentes/métricas y calendario](docs/catalogo-fuentes-calendario.md)
y el [cierre de las capturas AeroDataBox con histórico conservado](docs/etapas/cierre-aerodatabox-20261014.md).
El catálogo incluye la guía de skills y del coordinador
(`src/source_updates/`, `python -m src.source_updates --help`). Hay planificación,
captura aislada, pasos offline y controles explícitos. Los ejemplos siguen
siendo vistas previas; el estado privado conserva la activación real del único calendario.
El [contrato de ejecución y recuperación](docs/calendario-ejecucion.md) añade
estado privado, despacho nativo y handoffs por producto y versión mediante
`scripts/source_update_handoffs.py`. Los datos financieros validados pueden
actualizar sus gráficas mientras una tesis recorre su auditoría independiente.
La [skill de análisis](.agents/skills/aeromexico-tracker-analysis/SKILL.md) y
la [skill de dashboard](.agents/skills/airline-update-dashboard/SKILL.md)
describen los comandos, los recibos y la recuperación. Una fuente sin cambio
real o sin consumidor visible conserva su comprobación sin generar otra publicación.

## Qué vive dónde

| Área | Módulos | Rol |
|---|---|---|
| Ingesta | `src/ingest/` | Descarga fuentes públicas (SEC, BMV, AFAC, T-100, AeroDataBox…) a `data/bronze/` (local, con hash). |
| Parseo | `src/parse/` | Normaliza bronze a `data/silver/` (local), fiel a cada fuente. |
| Transformación | `src/transform/` | Construye `data/gold/` (43 Parquet versionados, extractos públicos) desde silver. |
| Analítica | `src/analytics/` | Estudios y modelos precomputados sobre gold (forecast, estimación ruta×aerolínea, etc.). |
| Dashboard | `src/dashboard/` | Payloads que `src/web_export`/`src/publish` consumen: lectura ejecutiva (`executive_summary.py`), Vuelos (`flights.py`, `flights_html.py::integration_flight_payload` — la lista blanca de columnas, `domestic_routes.py`, `international_routes.py`), más `data.py`/`check_manual_freshness.py`/`validate_stage8.py` (consultas al warehouse y controles de calidad de datos, sin UI). `web/` es la única vista publicada. |
| Analysis Agent | `src/analysis_agent/` | Evidencia, cálculo, revisión y **publicación controlada** del análisis narrativo por trimestre (etapas 12–17). |
| Contratos web | `contracts/web/` | Esquemas JSON (draft 2020-12) del payload **v1** tal cual lo consume `web/` (Vuelos, ejecutivo y análisis) + `privacy.yaml` (frontera pública/privada). Fuente de verdad; no aspiracional. |
| Exportadores web | `src/web_export/` | Divide esos mismos payloads en JSON por periodo bajo `web/public/data/v1/` (local, no versionado), validados contra `contracts/web/` y `config/web_inputs.yaml` antes de escribir. `flights/quarters.json` incluye además `available_periods`: el manifiesto de qué archivos por periodo existen, para que `web/` sepa qué pedir con `fetch()` sin listar el directorio. `analysis.py` exporta, para cada periodo que el ledger local (`analysis_runs/`) tiene actualmente aprobado o publicado (`discover_approved_manifest`), exactamente lo que `analysis_agent.lifecycle.consumer_payload(record)` autoriza — lectura del flujo de aprobación existente, nunca escritura; falla si falta el expediente local salvo `--allow-missing-analysis` (dev). |
| Gate de publicación (`site/`) | `src/publish/` | Publicación firmada con aprobación, fuentes, compilación y verificación. `issuer_update` separa datos y texto por emisor: conserva el baseline y reproduce la fuente exacta; datos requieren su autorización y revisión, tesis requieren el lifecycle. Pages elige el verificador del alcance publicado. Recibos en `analysis_runs/publications/` (local). Ver `src/publish/README.md`. |
| Front-end en archivos reales | `web/` | La página completa (Vite + TypeScript), **única** implementación publicada de las tres vistas (Lectura ejecutiva, Economía unitaria, Vuelos): HTML/CSS/TS reales (ES modules, `web/src/views/{flights,executive,economy,shell}/*.ts`, ≤ 400 líneas cada uno; tipos generados en `web/src/types/generated/` desde `contracts/web/*.schema.json` vía `npm run gen:types`) que consume `web/public/data/v1/` con `fetch()`. Plotly se importa parcial (`plotly.js/lib/core` + `bar`/`scatter`/`scattergeo`/`choropleth`, ver `web/src/lib/plotly.ts`). Ver `web/README.md`. |
| Chat | `src/conversational_analytics/`, `scripts/start_chat_runtime.py`, `scripts/chat/`, `Dockerfile.chat`, `railway.toml` | Backend FastAPI del chat, desplegado en Railway: capa semántica sobre el snapshot publicado (`site/data/v1/`), 13 herramientas de solo lectura con R2 (7 base y 2 por cada capacidad de rutas, métricas financieras y evidencia), proveedor OpenAI Agents API y estado en SQLite en el volumen `/data`. El panel vive en `web/src/views/chat/`. Railway solo redespliega cuando cambia un archivo de la imagen; la lista está en la configuración del servicio y versionada en `railway.toml` (ver `docs/chat/railway.md`). Ver `docs/chat/README.md`. |
| Pruebas | `tests/` | `uv run pytest`; marcadores `local_data` (necesita `data/bronze|silver`/warehouse local) y `browser` (Playwright) se excluyen en CI. |

**Gold tables:** 43 Parquet en `data/gold/` versionados en git (ver
`docs/diccionario-datos.md`). Cuatro estimaciones adicionales
(`fact_route_carrier_*_estimate.parquet`, `fact_aeromexico_*_capacity_estimate.parquet`)
son locales y regenerables, no versionadas en el público. El
[mapa de aprovechamiento](docs/gold-exposure.md) verifica su cuenta y distingue
interfaz, derivados, controles, tesis y skills; incluye el cierre documental.

**Dashboard/Vuelos:** `web/` es la única vista publicada (ver arriba). Sus
datos vienen de `src/dashboard/executive_summary.py::build_executive_payload()`
y `src/dashboard/flights.py::build_flight_payload()` +
`src/dashboard/flights_html.py::integration_flight_payload()` (lista blanca de
columnas: una columna nueva que no esté ahí se descarta en silencio), exportados
por `src/web_export/` y ensamblados por `src/publish/gate.py`. Editar el
generador (los módulos de `src/dashboard/` o `web/src/views/`), nunca un HTML
generado.

**Gate de publicación (`src/publish`):** dado uno o más registros ya
aprobados, `gate.py` re-verifica cada uno contra el ledger de aprobación
(`src/analysis_agent/lifecycle.py`, `analysis_runs/` local) antes de exportar,
compilar `web/` y ensamblar+firmar `site/` (manifiesto SHA-256, recibo
`.published.json`). La autorización permanente de `AGENTS.md` permite ejecutar
el gate para publicar cambios rutinarios solicitados sobre datos ya aprobados.
Nunca cambies un registro de aprobación sin autorización específica del dueño.

**Publicación en GitHub Pages (`site/`):** `site/` es el sitio ya
ensamblado y firmado que `.github/workflows/pages.yml` despliega tal cual —
en `master`, sin secretos ni reconstrucción de datos — a
<https://salvamalfa.github.io/aeromexico-tracker/>. Si el cambio solicitado
afecta al dashboard público, regenera `site/`, inclúyelo en el PR y sigue el
deploy de Pages conforme a `AGENTS.md`, sin pedir permiso adicional para una
publicación rutinaria:

```
uv run python -m src.publish --record analysis_runs/drafts/<periodo>/<version>.json --out site/
uv run python -m src.publish.verify site/
```

**Vista previa en `/v2/`.** `.github/pages-preview.json` puede fijar el commit
de una rama sin fusionar cuyo `site/` ya firmado se sirve en
`…/aeromexico-tracker/<path>/`, junto al sitio de `master`, que sigue en la raíz.
`pages.yml` verifica ese `site/` con el verificador y los contratos de su propio
commit, y si falla no despliega nada. Para actualizarla o retirarla, hace falta
un PR a `master` que cambie el commit fijado o borre el archivo. Ver
[`docs/archivo/mantenimiento-2026-09/pages-preview-v2-20260930.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/mantenimiento-2026-09/pages-preview-v2-20260930.md).

**Repo de datos privado:** insumos regenerables y privados
(`data/bronze`, `data/silver`, warehouse, `analysis_runs/`) tienen respaldo en
[`salvamalfa/aeromexico-tracker-data`](https://github.com/salvamalfa/aeromexico-tracker-data)
(privado, Git LFS). Acceso al código público no implica acceso a esos datos ni
autorización para publicarlos. Ver "Datos y documentación" en `README.md`.

## Comandos clave

| Comando | Qué hace |
|---|---|
| `uv run pytest -m "not local_data and not browser" -q` | Suite pública/CI (sin datos locales ni navegador). Conteo actual: ver salida del comando, no lo copies aquí. |
| `just test` / `uv run pytest` | Suite completa local (necesita `data/bronze`/`silver`/warehouse). |
| `just rebuild` | Reconstrucción completa offline desde bronze. |
| `python -m src.dashboard.build_flights` | Reconstruye el payload de Vuelos y su evidencia candidata tras cambiar fuentes o Vuelos. |
| `uv run python -m src.web_export --out web/public/data/v1` | Exporta los payloads v1 divididos por periodo bajo `web/public/data/v1/` (local, gitignored, no publica nada; falla con mensaje claro si falta un insumo Gold o el expediente de análisis, salvo `--allow-missing-analysis`). Vite (`npm run dev`/`build`) copia el contenido de `web/public/` a la raíz del sitio servido/`dist/` (convención de Vite: `web/public/data/v1/x.json` queda accesible en `data/v1/x.json`, no en `public/data/v1/x.json`; ver `web/src/views/{flights,executive}/state.ts`). |
| `cd web && npm ci` | Instala node_modules desde `web/package-lock.json` (versiones fijas; Node 22 + npm 10). |
| `cd web && npm run dev` | Sirve `web/` con el servidor de desarrollo de Vite (recarga en caliente) en `http://127.0.0.1:5173/`; necesita los datos exportados arriba primero. |
| `cd web && npm run build` | Compila el sitio a `web/dist/` (determinista: dos builds seguidos producen los mismos hashes de archivo). |
| `cd web && npm run preview` | Sirve `web/dist/` (el build) para revisión antes de publicar. |
| `cd web && npm run check` | `tsc --noEmit`: chequeo de tipos estricto sin emitir archivos. |
| `cd web && npm run test` | `vitest run`: pruebas unitarias de funciones puras (formato, agregación, clasificación de región…) y la prueba de tipos generados al día. |
| `cd web && npm run gen:types` | Regenera `web/src/types/generated/*.ts` desde `contracts/web/*.schema.json`; ejecútalo tras editar un esquema. |
| `uv run python -m src.publish --record … --out site/` | Publica `site/` (verifica el registro ya aprobado, exporta v1, compila `web/`, ensambla y firma). Autorizado para cambios rutinarios solicitados según `AGENTS.md`. |
| `uv run python -m src.publish.verify site/` | Revisa `site/` contra su manifiesto, los esquemas y `privacy.yaml` — sin datos privados; lo mismo que corre `.github/workflows/pages.yml` antes de desplegar. |

### Eficiencia de pruebas y CI

CI ejecuta lifecycle y Ruff antes del perfil público, con los mismos controles.
Los jobs `test` y `web` muestran las treinta fases más lentas y conservan JUnit
durante siete días en `public-test-results` y `browser-test-results`.

Las pruebas de conversación comparten una lectura real de `Snapshot` por
módulo: dos construcciones en vez de ocho. Cada consumidor comprueba que no
cambió su estado, incluidas las estructuras anidadas. Los nueve casos y sus
82 aserciones se conservan. App, SQLite, proveedor y worker siguen siendo
independientes por caso. Las pruebas que alteran archivos, contratos, pins o
validación construyen su propio lector y no usan esta fixture.

Medición del 29/oct/2026: base `62607e8`, implementación `ce9e152`, Python
3.13.5, dependencias de `uv.lock`, datos públicos y pins aprobados iguales.
Las ejecuciones medidas fueron en serie, en checkouts aislados; no se
restauraron insumos privados. El [registro técnico](docs/referencias/ci-efficiency-20261029.json)
conserva comandos, hashes, resultados y tiempos por fase y proceso. El
[detalle comprimido por caso](docs/referencias/ci-efficiency-20261029-cases.json.gz)
conserva todos los IDs y fases del perfil público; se abre como JSON con gzip.

| Perfil | Pytest antes / después | Proceso antes / después | Resultado |
|---|---|---|---|
| Dos módulos de chat | 122,52 / 71,00 s | 124,70 / 72,60 s | Nueve casos aprobados; IDs y resultados iguales. |
| Público completo | 2112,54 / 2118,20 s | 2116,66 / 2121,25 s | 5.363 casos y 29 subpruebas aprobados; nueve omisiones y 106 exclusiones. IDs y resultados iguales. |

En la toma completa, el proceso subió 4,59 s (0,22 %):
no se observó ahorro global. Los dos módulos afectados sumaron 93,101
→ 30,533 s de JUnit inclusivo dentro de ese perfil; ese dato describe
solo esos módulos.

El proceso focal bajó un 41,8 % observado. Su pico de memoria
subió de 539,1 a 725,8 MiB por la copia profunda
de la guarda.

Es un solo par local por perfil; no acredita un ahorro estadístico ni garantiza
esos tiempos en GitHub Actions. La comparación fija los commits indicados y
no se mezcla con CI de otros heads o perfiles. El perfil público excluye
`local_data` y `browser`; no demuestra validación privada ni autoriza publicar.
Los tiempos de fase de `--durations` están redondeados a centésimas. JUnit
conserva el total inclusivo por caso y por suite; el proceso incluye el arranque
de `uv` y pytest.

Para repetir, usa dos checkouts con los mismos datos, dependencias y pins
externos del [registro de aprobación auditado](https://github.com/salvamalfa/aeromexico-tracker/blob/d456eb8dc05e586d7119161c710db5ff47af0da3/docs/chat/fase-2-decision-dueno.md).
Ejecuta primero la base y después el cambio, sin competir por CPU:

```bash
export CI_PROFILE_BASE=62607e869d553b3ebb387404a63b726a8ce17f08
uv sync --all-extras --all-groups --locked
uv run --no-sync pytest -q tests/test_chat_mock_conversation.py tests/test_chat_integration.py --durations=0 --durations-min=0 --junitxml=tmp/ci-profile/focal.xml
uv run --no-sync pytest -m "not local_data and not browser" -q --financial-publication-base "$CI_PROFILE_BASE" --durations=0 --durations-min=0 --junitxml=tmp/ci-profile/public.xml
```

`CI_PROFILE_BASE` debe ser el SHA completo confiable del baseline de CI. Usa
esa opción solo cuando el sitio y su autoridad estén conservados: verifica la
publicación existente con su verificador liberado, sin aprobar el runtime nuevo.
Registra también el tiempo total del subproceso, CPU y pico de memoria; no
incluyas instalaciones en un lado y las excluyas del otro.

CI ejecuta el perfil público con dos procesos de pytest-xdist y
`--dist=loadfile`: cada archivo conserva juntos sus casos y fixtures. Un
worker que falle no se reinicia. Las dos herramientas están fijadas con
versiones y hashes en [`.github/ci-test-tools.txt`](.github/ci-test-tools.txt).
La instalación separada conserva el lock de runtime y exige `uv pip check`;
`--no-sync` mantiene esa instalación durante pytest.

La [pareja completa en CI40902930996](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/40902930996)
corrió primero secuencial y después con dos procesos en el mismo job y runner
`runnervm48cm3`, de cuatro CPU. Usó el mismo árbol del commit `ab940a0`, Python 3.13.18,
pytest 9.1.1, xdist 3.8.0, dependencias, datos, pins y filtros. Ambos modos
aprobaron **5.451 casos y 29 subpruebas**, con nueve omisiones y 106 exclusiones.
Coinciden los 5.460 IDs principales, 16.380 reportes de fase y las 29 identidades y
resultados de subpruebas. Las exclusiones se verifican en los inventarios de
cada proceso; xdist puede omitir su cuenta en el texto terminal.

| Perfil público completo | Secuencial | Dos procesos | Cambio observado |
|---|---:|---:|---:|
| Tiempo del subproceso pytest | 993,75 s | 536,64 s | −46,0 % |
| CPU acumulada, incluido el medidor | 996,80 s | 1.054,00 s | +5,7 % |
| RSS agregado muestreado | 1.489,7 MiB | 2.937,0 MiB | +97,2 % |

Se acepta el intercambio de CPU y memoria por 457,11 s menos de espera en la
capacidad ya asignada. Es una sola pareja; no garantiza esos tiempos futuros
ni describe el job entero, los datos privados o el navegador. El RSS es la
suma simultánea muestreada de los procesos cada 0,2 s: puede duplicar páginas
compartidas o perder picos breves. El máximo del mayor hijo es otra métrica y
se conserva por separado. La [distribución oficial](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)
explica la agrupación utilizada.

El [registro canónico](docs/referencias/ci-efficiency-20261029.json) conserva
comandos, hashes, entorno, CPU, memoria y límites; el
[detalle comprimido](docs/referencias/ci-global-efficiency-20261029-cases.json.gz)
conserva IDs, resultados y fases de todos los casos. La instrumentación fue
temporal y no queda en el CI recurrente. Sus fuentes se recuperan en el
[medidor del commit fijo](https://github.com/salvamalfa/aeromexico-tracker/blob/ab940a0ea2cc828c91e77107ff55c74dcfc3f4b5/.github/ci/profile_pytest.py)
y su [registro por proceso](https://github.com/salvamalfa/aeromexico-tracker/blob/ab940a0ea2cc828c91e77107ff55c74dcfc3f4b5/.github/ci/ci_pytest_inventory.py).
Para reproducir el protocolo, usa ese checkout, instala las dependencias
bloqueadas y las herramientas con hashes, conserva los pins externos ya
aprobados y ejecuta los modos 0 y 2 con el mismo entorno. No mezcles esta pareja
remota con tiempos de otro head o del cloud local.

Se descartó el ensayo adicional de lector compartido en tres módulos:
bajó el focal de 206,67 a 131,22 s, pero el completo pasó de 3.209,43 a 3.463,51 s y
terminó con un fallo del CLI a 90 s y un error del verificador histórico a 120 s.
El focal subió de 447,1 a 700,5 MiB de máximo del mayor hijo. El cambio fue
revertido; sus datos y los dos resultados distintos permanecen en la evidencia.
No se atribuye causalidad de los timeouts a la fixture ni se declara ahorro
global de ese ensayo.

El smoke de runtime rechaza antes el pin financiero ausente o vacío cuando
el recibo existe dentro del sitio elegido. Las entradas admisibles siguen
pasando por el `Snapshot` completo. El modo `--fixture-only` conserva su raíz
propia y no acredita el sitio publicado. Los límites de 90/120 s y las verificaciones
históricas se conservan.

## Recetas

### a) Mover o agregar un elemento de UI en Vuelos

Nada de esto genera HTML: `src/dashboard/` y `src/web_export/` son
constructores de payloads JSON; el único maquetado/interacción vive en
`web/src/views/`.

1. Lee `docs/etapas/vuelos-pasajeros-traspaso-20260913.md` (guía de entrada de Vuelos).
2. Edita el payload en `src/dashboard/flights.py` (datos) y/o la lista blanca en
   `src/dashboard/flights_html.py::integration_flight_payload` (qué campos
   llegan al JSON exportado vía `src/web_export/flights.py`).
3. Si el campo es nuevo, agrégalo al contrato en `contracts/web/flights.schema.json`.
4. Edita el maquetado/interacción en `web/src/views/flights/*.ts` (la única
   implementación de la vista).
5. Regenera: `python -m src.dashboard.build_flights`, luego
   `uv run python -m src.web_export --out web/public/data/v1`.
6. Corre `uv run pytest -q tests/test_flights_prototype.py tests/test_international_routes.py`
   y, en `web/`, `npm run check && npm run test`.
7. Si el cambio debe verse en Pages y usa datos ya aprobados, ejecuta
   `python -m src.publish`, verifica `site/`, incluye el artefacto en el PR y
   sigue el deploy y la comprobación pública (ver `AGENTS.md`).

### b) Agregar una columna a la tabla de rutas

Igual que en (a): `src/dashboard/*_routes.py` y `flights_html.py` construyen
un payload JSON, no HTML/CSS; el maquetado vive solo en `web/src/views/flights/table.ts`.

1. Añade la columna en `src/dashboard/domestic_routes.py` y/o
   `src/dashboard/international_routes.py` (donde se construyen las filas).
2. Agrégala a la lista blanca en
   `src/dashboard/flights_html.py::integration_flight_payload` — si se omite
   este paso, la columna se descarta en silencio sin error.
3. Añade la columna al contrato público en `contracts/web/flights.schema.json`
   (si no está ahí, `uv run python -m src.web_export` la rechaza en la
   validación de esquema) y a `docs/diccionario-datos.md`.
4. Agrega la columna a la tabla renderizada en `web/src/views/flights/table.ts`
   (o al módulo de `web/src/views/flights/` que corresponda a esa columna).
5. Regenera: `python -m src.dashboard.build_flights`, luego
   `uv run python -m src.web_export --out web/public/data/v1`.
6. Corre `uv run pytest -q tests/test_international_routes.py tests/test_aicm_international_slots.py`
   y, en `web/`, `npm run check && npm run test`.

### c) Actualizar datos de Vuelos

Seguir el [catálogo y calendario](docs/catalogo-fuentes-calendario.md) para las
ediciones oficiales y reconstruir offline los Gold correspondientes.
La exportación completa conserva los cuatro Gold privados de estimaciones
históricas como entradas ignoradas; no requiere nuevas capturas. Para cambiar
solo el mapa, `src.publish --preserve-published-data` conserva todos los bytes
de `site/data/v1/` y las cuatro tesis, sin reconstruir modelos ni actualizar
fuentes. Ver [histórico conservado y prueba AFAC/AICM](docs/plan-salida-aerodatabox.md).

### d) Retomar trabajo pendiente

El trabajo abierto vive en `ROADMAP.md` ("Ahora"/"Siguiente"). Un paquete de
varios pasos delegado por la sesión coordinadora lo ejecuta el subagente
`implementador` (`.claude/agents/implementador.md`), en su propia rama,
commiteando y subiendo tras cada tarea. La historia de proyectos cerrados se
resume en `docs/archivo/README.md` y no se retoma.

### e) Cerrar un esfuerzo y retirar su documentación

Sigue el [cierre documental obligatorio](AGENTS.md#cierre-documental-obligatorio-por-tarea),
también en una entrega local. Inventaría todos los archivos, incluidas las salidas generadas;
clasifica conservar, actualizar, consolidar, archivar, retirar, candidato a eliminar o pendiente,
con motivo y dependencias desde código, pruebas, skills e índices. Pasa lo
vigente a la guía canónica antes de retirar un plan reemplazado. Conserva
fuentes, decisiones, aprobaciones y evidencia.

Para archivar, comprueba primero que el original íntegro existe en un commit
fijo; enlázalo desde `docs/archivo/README.md` y actualiza referencias entrantes.
Retíralo del árbol solo si el encargo lo permite. Registra la disposición por
archivo en el resumen existente con `document-lifecycle:v1` y valida con
`scripts/check_document_lifecycle.py --base <base> --worktree --summary-file <resumen>`
antes del commit; después omite `--worktree`. Para el respaldo privado añade
`--root <checkout-privado>`. El mismo control verifica código y artefactos; los
lotes homogéneos admiten prefijo acotado y conteo exacto según la guía canónica.
No crees otro Markdown de estado para acreditar el cierre. Un pendiente exige
archivo y motivo; la edad o el número de documentos no justifican un retiro.
