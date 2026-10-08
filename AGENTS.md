# Guía para agentes de desarrollo

Este repositorio construye un dashboard reproducible de Aeroméxico a partir de
fuentes públicas. La prioridad es preservar el significado de cada cifra, su
procedencia y el estado de aprobación humana. Una ejecución técnicamente válida
no autoriza por sí sola a publicar datos nuevos.

## Antes de editar

1. Ejecuta `git status --short --branch` y revisa el diff de los archivos que
   tocarás. Conserva los cambios existentes; no uses `reset`, `checkout`,
   `clean` ni sobrescribas trabajo ajeno.
2. Lee `README.md`, este archivo y el reporte de etapa relacionado en
   `docs/etapas/`. Para trabajo de Vuelos, empieza por
   `docs/etapas/vuelos-pasajeros-traspaso-20260913.md` y sigue sus enlaces.
   [`REPO_MAP.md`](REPO_MAP.md) da el mapa del árbol, comandos y recetas.
3. Comprueba la rama y su relación con `origin/master`. No publiques desde una
   rama divergente sin integrar primero la historia remota mediante un PR
   revisable.
4. Busca instrucciones más específicas en el directorio de trabajo. Las
   instrucciones del usuario y los contratos de datos prevalecen sobre
   sugerencias de implementación.

### Dónde mirar

`README.md`: estado actual. `CHANGELOG.md`: cambios recientes. `ROADMAP.md`:
lo que sigue (propuesta, el dueño decide prioridades). `REPO_MAP.md`: mapa del
árbol y recetas paso a paso. `docs/archivo/README.md`: resumen de la historia
del proyecto con enlaces a los documentos originales en Git — no lo leas salvo
que la tarea lo requiera explícitamente; está fuera de las búsquedas de agentes
(`.ignore`).

## Entorno y comandos

Windows/PowerShell es el entorno de referencia; Python 3.13
(`.venv\Scripts\python.exe`); `uv run` y `just` son las interfaces
documentadas. `just setup` prepara el entorno; `just test` corre la suite;
`just dashboard-validate` valida los datos del dashboard; `just transform`
reconstruye gold, `just rebuild` todo el pipeline offline. Dashboard local:
`uv run python -m src.web_export --out web/public/data/v1
--allow-missing-analysis` y luego `cd web && npm ci && npm run dev` (ver
`web/README.md`).

Los comandos con red, cuotas, suscripciones o APIs pagadas requieren una
ejecución deliberada. Implementa primero un `--dry-run` que muestre llamadas,
ventanas, unidades estimadas y destinos de escritura.

## Arquitectura y artefactos autoritativos

Bronze/silver/warehouse son locales y regenerables (no versionados); gold son
extractos públicos versionados. `src/ingest/`, `src/parse/`, `src/transform/`
son el pipeline de procedencia; `src/dashboard/` construye los payloads del
dashboard; `src/analysis_agent/` es evidencia, cálculo, revisión y
publicación controlada; `prototypes/` son artefactos HTML para revisión;
`docs/etapas/` documenta decisiones, resultados y límites por etapa. Detalle
completo (qué vive dónde, comandos, recetas) en `REPO_MAP.md`.

Los insumos privados y regenerables tienen un respaldo separado en
[`salvamalfa/aeromexico-tracker-data`](https://github.com/salvamalfa/aeromexico-tracker-data).
Ese repositorio debe permanecer privado y requiere Git LFS. Un agente con acceso
explícito puede clonarlo, ejecutar `verify_snapshot.py` y restaurarlo sobre un
checkout público con `restore_snapshot.py`. Nunca copies su contenido a un PR
del repositorio público ni asumas que acceso al código implica acceso a los
datos o autorización para publicarlos.

Edita el generador, no solo el HTML generado. El dashboard publicado es la
página real en `web/` (Vite + TypeScript) — única implementación de cada
vista — alimentada por `src/web_export/` a partir de los payloads de
`src/dashboard/executive_summary.py` y `src/dashboard/flights.py` +
`flights_html.py::integration_flight_payload`, y publicada como `site/` por
`src/publish/gate.py`. Si cambian fuentes o Vuelos, regenera primero
`python -m src.dashboard.build_flights` y después
`uv run python -m src.web_export --out web/public/data/v1` antes de
interpretar una prueba de igualdad como regresión.

## Reglas de significado de datos

- No conviertas un faltante en cero.
- Distingue cifras reportadas, calculadas, inferidas, estimadas y programadas.
- Distingue operador de comercializador/codeshare. En particular, Aerovías de
  México y Aeroméxico Connect no se fusionan si la fuente permite separarlas.
- Distingue vuelos realizados de programación; pasajeros por tramo de
  pasajeros de itinerario; y cifras de Aeroméxico de totales de todas las
  aerolíneas.
- No repartas un agregado entre rutas o aerolíneas sin evidencia. Si se usa un
  modelo, la salida debe declararse estimación y conservar versión, insumos,
  diagnósticos, incertidumbre y reconciliaciones.
- T-100 documenta operaciones observadas del operador/reportante entre México y
  Estados Unidos. No representa la red mundial, codeshares, ingresos ni
  rentabilidad.
- La elegibilidad histórica al corte de 2026-07-13 y el uso retrospectivo en el
  dashboard son decisiones distintas. No cambies una por actualizar la otra.
- `flight_evidence_v1` sigue siendo candidato no aprobado. No lo actives, no
  hagas backfill y no recalcules o publiques modelos automáticamente.

## Vuelos y estimaciones por ruta y aerolínea

**Antes de tocar el estimador, lee
[`docs/estimacion-pasajeros-ruta-aerolinea.md`](docs/estimacion-pasajeros-ruta-aerolinea.md).**
Es el documento canónico del método: problema estadístico, ecuaciones del IPF,
grano y definiciones de ambas marginales, aceptación de la semilla, ceros, no
convergencia, soporte temporal, sensibilidad, separación Aerovías/Connect y
agregación visible como Grupo Aeroméxico, error medido por operador,
competencia, tamaño y distancia, y las condiciones exactas para extenderlo al
mercado internacional. No reconstruyas el método desde reportes de etapa sueltos
ni desde una conversación.

Una semilla de frecuencias puede revelar la estructura ruta por aerolínea, pero
no observa pasajeros. Un ajuste a marginales AFAC debe publicarse como
`passengers_estimated`, incluso cuando reconcilie exactamente totales de ruta y
aerolínea. Las celdas de operador único solo pueden llamarse exactas si la
cobertura de la semilla demuestra que no falta otro operador y ambas marginales
usan el mismo universo.

Toda integración de un proveedor pagado debe incluir:

- inventario de endpoints, campos, límites, costo y ventana histórica;
- filtros explícitos de carga, charter, cancelaciones y codeshare;
- crosswalk versionado de aeropuerto, aerolínea y operador;
- conteo y monto AFAC de filas no mapeadas;
- puerta de aceptación de cobertura antes de estimar;
- reconciliación por ruta y por aerolínea al pasajero;
- separación entre contenido crudo sujeto a licencia y obra derivada publicable.

Nunca subas una API key, respuesta cruda o copia ligeramente reformateada de un
proveedor a GitHub. Revisa los términos vigentes del proveedor el día de la
captura. En el caso de AeroDataBox, `docs/cloud-development.md` documenta la
frontera actual.

## Analysis Agent y aprobación

`analysis_runs/` contiene el estado autoritativo de borradores, aprobaciones y
publicaciones, y está ignorado en el repositorio público. Existe una copia en el
respaldo privado para continuidad y recuperación. No fabriques una aprobación a
partir del HTML ni cambies el estado del Analysis Agent para hacer pasar una
prueba. Restaurar el expediente permite reproducir su estado; no concede por sí
solo autorización para aprobar o republicar un análisis.

La autorización permanente de la sección siguiente permite publicar cambios
rutinarios del dashboard con el gate y el PR del proyecto. No hagas push directo
a `master`, no actives evidencia, no cambies aprobaciones humanas y no consumas
una API pagada sin autorización específica para esa acción.

## Cambios de principio a fin: autorización permanente del dueño

Autorización dada por el dueño (salvamalfa) el 26 de septiembre de 2026 para
PRs y ampliada el 27 de septiembre de 2026 al ciclo completo de cambios
rutinarios. Aplica a cualquier agente (Claude, ChatGPT/Codex u otro), en esta y
futuras sesiones. Una petición como «cambia esto» autoriza realizar lo
necesario para entregar ese cambio: investigar, editar, regenerar, verificar,
crear rama, hacer commits y push a esa rama, abrir y actualizar un PR, atender
CI y revisiones, integrarlo y, si afecta al dashboard público, desplegarlo en
GitHub Pages y verificar el resultado. No pidas permiso separado para cada paso
ni para ejecutar el gate de publicación de un cambio rutinario. Si el usuario
limita la tarea a diagnóstico, borrador o revisión, respeta ese límite.

### Flujo de entrega

1. Confirma alcance, estado Git, fuentes y datos afectados. Conserva cambios
   ajenos y trabaja en una rama desde el `master` vigente.
2. Implementa y valida. Confirma primero en Git los cambios de entrada de
   compilación bajo `src/`, `web/`, `contracts/` y `config/`: el gate rechaza
   esos archivos si tienen cambios sin commit, porque el manifiesto registra
   el commit del código. Después regenera los artefactos afectados desde las
   fuentes. Si el cambio debe verse en Pages, ejecuta `src.publish` con un
   registro que el gate verifique como ya aprobado, luego
   `src.publish.verify site/`; incluye `site/` en un segundo commit del mismo
   PR. Para cambios solo de interfaz, comprueba que el `analysis_manifest` y
   los hashes de `site/data/v1/` no cambien.
3. Abre el PR como borrador. Espera los checks obligatorios `test` y `web` del
   último commit; atiende comentarios e hilos y márcalo listo para revisión.
   Da unos minutos a la revisión automática antes de integrar.
4. Fusiona con merge commit cuando los checks estén verdes, no haya conflicto
   con `master` y todos los hilos estén atendidos y resueltos. Nunca uses el
   bypass de administrador, force-push ni push directo a `master`.
5. Si cambió `site/`, sigue `.github/workflows/pages.yml` hasta que verificación,
   CI y deploy terminen correctamente; abre el dashboard público para confirmar
   el cambio. Informa el PR, el estado de publicación y cualquier límite real.

Si el entorno carece del warehouse o del expediente privado necesario para el
gate, no reconstruyas ni simules aprobaciones. Prepara el cambio revisable y
usa un entorno autorizado que sí tenga esos insumos para terminar la
publicación. Explica un bloqueo técnico concreto si no hay acceso a él.

### PRs y seguimiento

- **Suscribirte a la actividad de tus PRs** (CI, reviews, comentarios) sin
  preguntar, y dar seguimiento hasta que se fusionen o cierren.
- **Suscripciones y triggers** (ampliado el 27 de septiembre de 2026): puedes
  suscribirte o desuscribirte de cualquier PR de este proyecto, y crear,
  modificar, disparar o eliminar triggers y recordatorios programados
  (`send_later`, `create_trigger`, etc.) para dar seguimiento a tu trabajo, sin
  preguntar. `.claude/settings.json` los preaprueba.
- **Fusionar tus propios PRs** cuando se cumplan las condiciones del flujo de
  entrega, incluidos los hilos de bots como Codex: corrige sus hallazgos con
  un push o responde por qué no aplican y resuélvelos antes del merge.
- **Auto-merge** (habilitado en el repo): puedes activarlo en tu PR en vez de
  esperar a que termine la CI, pero solo después de marcarlo como listo y de que
  llegue la revisión automática (o el aviso de que no habrá revisión, p. ej. el
  límite de uso de Codex, más la revisión cruzada si el PR cambia código) con
  todos sus hilos atendidos. Auto-merge solo espera a
  los checks; no espera revisiones que aún no llegan. Si un push posterior abre
  hilos nuevos, desactívalo hasta atenderlos. Esto también aplica a PRs que
  cambien `site/` por una publicación rutinaria autorizada arriba.
- **Revisión cruzada entre agentes** (pedida por el dueño el 8 de octubre de
  2026): un PR que cambie código (`src/`, `scripts/`, `web/src/`, workflows,
  `Dockerfile.chat` o `railway.toml`) y no reciba revisión de Codex, por
  ejemplo por el límite de uso, no se fusiona solo con el aviso de que no
  habrá revisión. Lo revisa el otro agente: lo que prepare ChatGPT/Codex lo
  revisa Claude, y lo que prepare Claude lo revisa ChatGPT/Codex o el dueño.
  La revisión es adversarial (buscar fallos con pruebas o pasos concretos, no
  resumir el diff) y deja sus hallazgos en el PR; se atienden como cualquier
  hilo antes del merge. Los PRs solo de documentación quedan exentos.
- GitHub borra la rama del PR al fusionarlo ("Automatically delete head
  branches"); no hace falta limpiarla. Si reutilizas el nombre, recréala desde
  `master`.

Esta autorización cubre código, pruebas, workflows, documentación y
publicación rutinaria del sitio. **Pide autorización específica antes de una
acción de mayor riesgo:** aprobar o revocar un análisis; activar
`flight_evidence_v1` u otra evidencia candidata; publicar un periodo nuevo o
cifras cuyo significado, cobertura o elegibilidad cambió y aún requiere
aprobación humana; consumir una API pagada o contratar un servicio; exponer
datos privados o licenciados, secretos o permisos de acceso; borrar datos de
forma irreversible; o saltar controles de GitHub y del gate. Puedes preparar
el código y un PR revisable mientras llega esa decisión. La autorización para
publicar una corrección de interfaz con datos ya aprobados no equivale a
aprobar datos nuevos.

## Ciclo de vida de la documentación

El repositorio documenta el estado actual. La historia se resume en
`docs/archivo/README.md` y los documentos originales viven en Git: se borran
del árbol, no se acumulan.

- **Vigente:** `README.md`, `AGENTS.md`, `REPO_MAP.md`, `ROADMAP.md`,
  `CHANGELOG.md` y `docs/`. Describe cómo funciona hoy el sistema o qué sigue,
  y se actualiza en el mismo PR que cambia lo que describe.
- **Reportes de etapa (`docs/etapas/`):** bitácora fechada de un paso; no se
  reescriben después. Se quedan mientras su esfuerzo siga abierto, mientras
  sean la procedencia de un dato publicado que ningún documento permanente
  explica, o mientras los cite el código.
- **Planes, propuestas y traspasos:** viven en `docs/` mientras están activos.
  Al cerrar el esfuerzo (por ejemplo, al terminar la fase 2 del chat):
  1. pasa lo que siga vigente (cómo funciona, límites, decisiones) a la
     documentación permanente, como `docs/chat/README.md` o `REPO_MAP.md`;
  2. agrega a `docs/archivo/README.md` un párrafo que resuma el esfuerzo y
     enlace los originales en un commit fijo
     (`https://github.com/salvamalfa/aeromexico-tracker/tree/<sha>/<ruta>`);
  3. borra los originales con `git rm` y cambia los enlaces que apuntaban a
     ellos por ese enlace permanente.
- **Decisiones (`docs/decisiones/`):** no se borran ni se reescriben. Una
  decisión que cambia se reemplaza por una nueva y la anterior se marca
  «Reemplazada por …».
- Un documento que ya no aplica y no aporta historia útil se borra sin más;
  Git conserva su versión anterior.
- No borres ni muevas un documento que citen el código, una prueba o un
  contrato sin actualizar esa referencia en el mismo PR.

## Criterio de cierre

Antes de entregar:

1. Regenera todos los artefactos afectados desde sus fuentes.
2. Ejecuta pruebas focalizadas y luego la suite completa cuando el cambio toca
   pipeline, warehouse, generadores o contratos.
3. Ejecuta `git diff --check` y revisa `git status` para no incluir secretos,
   temporales ni cambios ajenos.
4. Documenta en `docs/etapas/` qué cambió, por qué, cómo se validó y qué límites
   permanecen.
5. Reporta por separado código preparado, datos activados, aprobación y
   publicación. Ninguno implica automáticamente los otros.
