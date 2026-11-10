# Mapa del repositorio de Airlines Tracker

Esta guía conecta las capacidades del proyecto con su código, sus datos y sus
instrucciones de ejecución. La [portada](README.md) presenta el producto; aquí
puedes elegir un recorrido técnico sin leer el repositorio de principio a fin.

## Por dónde empezar

| Quieres revisar… | Empieza aquí | Qué encontrarás |
|---|---|---|
| Ingeniería de datos | [Flujo de datos](src/pipeline/README.md) | Registro de pasos, dependencias, controles y recibos de ejecución. |
| Pronósticos y aprendizaje automático | [Analítica](src/analytics/README.md) | Problemas, métodos, referencias de comparación y evaluación temporal. |
| Interfaz conversacional | [Guía del chat](docs/chat/README.md) | Preguntas de ejemplo, contexto y procedencia de las respuestas. |
| Implementación de IA | [Arquitectura del chat](docs/arquitectura/airline-tracker-agents-api.md) | Modelo, herramientas, sesiones y datos publicados. |
| Interfaz del dashboard | [Guía de `web/`](web/README.md) | Vistas, datos que consume, desarrollo y compilación. |
| Ejecutar o colaborar | [Desarrollo local y en nube](docs/cloud-development.md) | Preparación del entorno y límites de un clon público. |

## Qué vive dónde

| Área | Código o ruta | Responsabilidad |
|---|---|---|
| Orquestación | [`src/pipeline/`](src/pipeline/README.md) | Define pasos, dependencias, entradas requeridas y resultados. |
| Ingesta | [`src/ingest/`](src/ingest/README.md) | Obtiene documentos y series de fuentes públicas; registra sus originales en Bronze. |
| Lectura y normalización | [`src/parse/`](src/parse/README.md) | Extrae tablas de cada fuente y conserva unidades y procedencia en Silver. |
| Transformación | [`src/transform/`](src/transform/README.md) | Consolida Gold, diccionarios y vistas analíticas en DuckDB. |
| Analítica | [`src/analytics/`](src/analytics/README.md) | Calcula pronósticos, agrupaciones, anomalías y estudios sobre los datos preparados. |
| Análisis narrativo | [`src/analysis_agent/`](src/analysis_agent/README.md) | Vincula evidencia, cálculos, redacción y aprobación de la lectura trimestral. |
| Preparación del dashboard | [`src/dashboard/`](src/dashboard/README.md) | Construye datos de indicadores y rutas; no contiene la interfaz del sitio. |
| Exportación | [`src/web_export/`](src/web_export/README.md) | Escribe los JSON por vista y periodo que consume `web/`; valida sus contratos. |
| Contratos | [`contracts/web/`](contracts/web/README.md) | Define estructuras JSON y la frontera pública/privada de cada exportación. |
| Interfaz | [`web/`](web/README.md) | Implementa la página con Vite, TypeScript y Plotly. |
| Chat | [`src/conversational_analytics/`](src/conversational_analytics/README.md) | Consulta una copia verificada de los datos publicados mediante herramientas de solo lectura. |
| Publicación | [`src/publish/`](src/publish/README.md) | Verifica el análisis aprobado, compila la interfaz y firma el sitio. |
| Sitio compilado | [`site/`](site/) | Artefacto que GitHub Pages despliega. Se regenera desde sus fuentes. |
| Pruebas | [`tests/`](tests/) | Comprueba cálculos, contratos, publicación, backend e interfaz. |

### Datos, fuentes y referencias

- `data/bronze/`: documentos originales, URL, fecha y hash SHA-256. Su manifiesto
  permite seguir el origen de una cifra. Los originales no se versionan aquí.
- `data/silver/`: tablas fieles a cada fuente, con tipos y unidades. Son locales.
- `data/gold/`: extractos públicos consolidados en Parquet, versionados para el
  sitio. Existen además estimaciones históricas privadas, locales y regenerables.
- `data/warehouse.duckdb`: almacén analítico local; sus vistas se construyen a
  partir de los datos disponibles.
- [`docs/diccionario-datos.md`](docs/diccionario-datos.md): tablas y columnas.
  El [mapa de uso de Gold](docs/gold-exposure.md) distingue datos visibles en
  pantalla, insumos analíticos y controles; una tabla exportada no implica una
  gráfica implementada.
- [Catálogo de fuentes y calendario](docs/catalogo-fuentes-calendario.md):
  organismos, publicaciones, frecuencias y procedimientos de actualización.
- [Periodos del dashboard](docs/periodos-dashboard.md): trimestre seleccionado,
  cortes de cada fuente y cobertura. No todas las fuentes comparten el mismo corte.
- [Mapa oficial](docs/mapa-oficial.md) y [estimación de pasajeros por ruta y
  aerolínea](docs/estimacion-pasajeros-ruta-aerolinea.md): métodos, universos y
  límites de las rutas. Conservan estados de aprobación independientes.

### Repo de datos privado

El respaldo [`aeromexico-tracker-data`](https://github.com/salvamalfa/aeromexico-tracker-data)
contiene originales, Silver, warehouse y expedientes de análisis; requiere acceso
explícito y Git LFS. Un clon público permite inspeccionar el código y el sitio
versionado, pero no reconstruye toda la publicación sin esos insumos. La opción
`--allow-missing-analysis` permite omitir el expediente narrativo en desarrollo;
no sustituye otros datos requeridos por el exportador.

Los requisitos por vista están en [`config/web_inputs.yaml`](config/web_inputs.yaml).
La [guía de desarrollo](docs/cloud-development.md) explica qué puede reproducirse
en cada entorno. Acceder al código no concede acceso ni permiso para publicar
insumos privados o sujetos a licencia.

### Actualización de fuentes

[`src/source_updates/`](src/source_updates/) coordina planificación, capturas
aisladas, reconstrucciones y controles. Consulta sus opciones con
`uv run python -m src.source_updates --help` y el
[contrato de ejecución y recuperación](docs/calendario-ejecucion.md). Los recibos
operativos y la activación del calendario se conservan en el estado privado.

El workflow [`refresh.yml`](.github/workflows/refresh.yml) monitorea frescura y
valida Gold: no descarga todas las fuentes ni reconstruye el pipeline. AFAC
incluye descarga asistida. La actualización de datos y la aprobación de una
lectura tienen recorridos distintos; las guías del [análisis](src/analysis_agent/README.md)
y de [publicación](src/publish/README.md) detallan sus controles.

La carpeta [`automation/amr/`](automation/amr/README.md) conserva las instrucciones
y validadores de búsquedas con puntos. Sus identificadores y resultados privados
no forman parte del dashboard público.

## Comandos clave

Ejecuta estos comandos desde la raíz. Los que descargan fuentes necesitan red y
las credenciales que indique cada fuente. Una reconstrucción requiere sus
originales locales. Los comandos de publicación requieren un expediente aprobado.

| Comando | Resultado |
|---|---|
| `just setup` | Instala dependencias de Python y Chromium para desarrollo. |
| `just ingest` | Ejecuta las ingestas registradas que usan red. |
| `just parse` | Reconstruye Silver desde Bronze. |
| `just transform` | Reconstruye Gold y las vistas analíticas. |
| `just rebuild` | Reconstruye el pipeline sin nuevas descargas, desde los originales locales. |
| `just dashboard-validate` | Comprueba los datos preparados para el dashboard. |
| `just test` | Ejecuta las pruebas; los datos locales disponibles determinan qué casos pueden ejecutarse. |
| `uv run pytest -m "not local_data and not browser" -q` | Ejecuta el perfil público de Python sin insumos privados ni navegador. |
| `uv run python -m src.dashboard.build_flights` | Reconstruye los datos de Vuelos; por sí solo no los publica ni aprueba. |
| `uv run python -m src.web_export --out web/public/data/v1` | Exporta y valida los JSON que consume la interfaz. |
| `uv run python -m http.server 8000 --directory site` | Permite revisar el sitio versionado en `http://localhost:8000/`, sin reconstruir sus datos. El chat requiere su servicio aparte. |

Para trabajar en la interfaz, entra en `web/`:

| Comando | Resultado |
|---|---|
| `npm ci` | Instala las dependencias fijadas en `package-lock.json`. |
| `npm run dev` | Inicia Vite con recarga al editar; requiere datos exportados. |
| `npm run check` | Comprueba los tipos de TypeScript. |
| `npm run test` | Ejecuta pruebas unitarias con Vitest. |
| `npm run gen:types` | Genera tipos desde los contratos JSON; úsalo después de cambiar un esquema. |
| `npm run build` | Compila la interfaz en `web/dist/`. |
| `npm run preview` | Sirve esa compilación para revisión local. |

Vite expone `web/public/data/v1/x.json` como `data/v1/x.json`. El
[README de la interfaz](web/README.md) reúne configuración, pruebas de navegador
y soluciones para el entorno local.

## Publicación en GitHub Pages

El recorrido es: exportar los datos, compilar `web/`, ensamblar y verificar
`site/`, integrar el PR y desplegar. El control de publicación vuelve a comprobar
el expediente aprobado y registra los hashes de la entrega. Una compilación
local o una CI correcta no sustituyen la comprobación del sitio servido.

```powershell
uv run python -m src.publish --record analysis_runs/drafts/<periodo>/<version>.json --out site/
uv run python -m src.publish.verify site/
```

El [procedimiento de publicación](src/publish/README.md) explica los modos
disponibles y la conservación de datos ya publicados. [`AGENTS.md`](AGENTS.md)
define el flujo de PR, revisión e integración y los límites de autorización.
Nunca se fabrica una aprobación para poder compilar.

[`pages.yml`](.github/workflows/pages.yml) despliega el sitio firmado en
<https://salvamalfa.github.io/aeromexico-tracker/>. Una vista previa puede fijarse
con `.github/pages-preview.json`: su artefacto se verifica con los contratos y
el verificador de su propio commit. El
[procedimiento original](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/mantenimiento-2026-09/pages-preview-v2-20260930.md)
conserva sus detalles. La vista previa no reemplaza la publicación de la raíz.

### Eficiencia de pruebas y CI

La [configuración de CI](.github/workflows/ci.yml) mantiene los checks `test` y
`web`. Ambos exigen que terminen correctamente todos los componentes seleccionados.
El [selector de cambios](scripts/ci_change_plan.py) aplica perfiles conservadores:

| Perfil | Alcance |
|---|---|
| Documentación raíz | Solo cambios regulares en `README.md`, `REPO_MAP.md`, `ROADMAP.md` y `CHANGELOG.md`; conserva controles estáticos y de publicación. |
| Interfaz | Añade comprobación de tipos, unitarias, compilación y navegador cuando solo cambia la interfaz admitida. |
| Completo | Código, datos, contratos, documentación que puede ser insumo ejecutable, cambios mixtos o historia incierta. También es el perfil de las llamadas que lo fuerzan. |

El perfil público de Python reparte los módulos en tres particiones disjuntas
(`core-a`, `core-b`, `publication`). Cada una usa dos procesos con
`--dist=loadfile` y no reinicia automáticamente un proceso fallido. Las pruebas
`browser` se ejecutan aparte; `local_data` requiere insumos locales. Los controles
de Pages, Docker y el chat conservan sus propios entornos y verificaciones.

Pages puede reutilizar la CI de un PR fusionado solo si comprueba la asociación
del PR, su base, su ejecución correcta y la igualdad del árbol completo del merge.
Si no puede acreditar esas condiciones, ejecuta la validación completa. En ambos
casos verifica y despliega el commit integrado.

Para investigar un fallo o repetir un intento sobre el mismo commit:

```powershell
gh run view RUN_ID --json headSha,event,status,conclusion
gh run rerun RUN_ID --failed
gh run rerun --job JOB_ID
```

Un commit nuevo necesita su propia validación. Editar el cuerpo del PR vuelve a
comprobar el inventario documental. Las versiones fijadas de las herramientas
de pruebas están en [`.github/ci-test-tools.txt`](.github/ci-test-tools.txt).

Las mediciones históricas conservan comandos, perfiles, resultados y límites en
los registros del [29 de octubre](docs/referencias/ci-efficiency-20261029.json),
[31 de octubre](docs/referencias/ci-preflight-20261031.json) y
[6 de noviembre](docs/referencias/ci-efficiency-20261106.json). El
[detalle de las comparaciones y ensayos descartados](https://github.com/salvamalfa/aeromexico-tracker/blob/72861902ee30feeb3d3c15b681ee897f5e1e6ab5/REPO_MAP.md#eficiencia-de-pruebas-y-ci)
permanece en su versión original. Son observaciones sobre entornos y commits
concretos; no predicen la duración de futuras ejecuciones.

## Recetas

<a id="a-mover-o-agregar-un-elemento-de-ui-en-vuelos"></a>

### a) Mover o agregar un elemento de interfaz en Vuelos

1. Revisa la [guía de entrada de Vuelos](docs/etapas/vuelos-pasajeros-traspaso-20260913.md)
   y el [mapa oficial](docs/mapa-oficial.md) cuando el cambio afecte esa red.
2. Modifica la preparación de datos en `src/dashboard/` o `src/web_export/`.
   Para el contrato histórico de Vuelos, revisa también la lista blanca de
   `flights_html.py::integration_flight_payload`: descarta campos no incluidos.
3. Actualiza el esquema correspondiente en `contracts/web/` y regenera sus tipos.
4. Modifica la interfaz en `web/src/views/`; ahí viven el diseño y la interacción.
5. Regenera los datos afectados y la exportación. Comprueba tipos, unitarias y
   los casos de navegador que cubran el recorrido modificado.
6. Si el cambio debe verse en Pages, sigue la publicación con datos aprobados.

### b) Agregar una columna a la tabla de rutas

La tabla histórica utiliza `domestic_routes.py`, `international_routes.py` y
`integration_flight_payload`; el mapa oficial tiene contrato y exportador propios.
Identifica primero cuál consume la vista que modificarás.

1. Añade el campo al constructor de datos y a su contrato público.
2. Si pasa por `integration_flight_payload`, inclúyelo en su lista blanca.
3. Actualiza el diccionario desde su generador y los tipos con `npm run gen:types`.
4. Añade su representación en el módulo de `web/src/views/flights/` correspondiente.
5. Regenera, valida esquemas y comprueba que el valor aparece con unidad,
   procedencia y tratamiento de faltantes correctos.

### c) Actualizar datos de Vuelos

Sigue el [catálogo y calendario](docs/catalogo-fuentes-calendario.md) y los
controles del método que uses. La exportación histórica completa conserva
estimaciones privadas como entradas; reconstruirlas no exige nuevas capturas
por sí mismo. El [histórico conservado](docs/plan-salida-aerodatabox.md) precisa
sus condiciones. Para un cambio que deba conservar datos publicados, consulta
`--preserve-published-data` en la [guía de publicación](src/publish/README.md).
Actualizar el código no activa una fuente ni aprueba una estimación nueva.

### d) Retomar trabajo pendiente

Consulta [`ROADMAP.md`](ROADMAP.md) para las prioridades y
[`CHANGELOG.md`](CHANGELOG.md) para los cambios recientes. Lee la guía vigente del
área antes de acudir a una bitácora. El [archivo](docs/archivo/README.md) resume
trabajos cerrados y enlaza sus originales; no define el comportamiento actual.

### e) Cerrar un esfuerzo y retirar su documentación

El [cierre documental obligatorio](AGENTS.md#cierre-documental-obligatorio-por-tarea)
exige inventariar cada archivo del cambio, incluidos los nuevos y los generados,
y registrar su disposición y motivo en el resumen existente del PR.

```powershell
python scripts/check_document_lifecycle.py --base <base> --worktree --list
python scripts/check_document_lifecycle.py --base <base> --worktree --summary-file <resumen>
```

Después del commit omite `--worktree`. El control verifica rutas y referencias;
la revisión humana comprueba anclas, enlaces externos, significado y autorización.
Consolida lo vigente antes de retirar un documento. Conserva fuentes, decisiones,
aprobaciones y evidencia, y comprueba su recuperación en un commit fijo. No se
crea otra bitácora para certificar el cierre.
