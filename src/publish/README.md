# Publicación de Airlines Tracker

Este paquete prepara `site/`: la interfaz compilada, los datos públicos y un
manifiesto de integridad SHA-256. Comprueba fuentes, contratos y aprobaciones
antes de sustituir el sitio. GitHub Pages despliega ese directorio sin
reconstruirlo.

Un build local, una aprobación y una versión servida son resultados distintos.
El gate no concede aprobaciones; solo verifica las que exige cada alcance.
Sin los expedientes locales requeridos, un clon público puede inspeccionar
la publicación existente, pero no reproducir todos los pasos de publicación.

## Qué necesitas y qué se genera

| Entradas | Salidas |
|---|---|
| Código de `web/`, Node/npm, contratos y configuración confirmados en Git. | `site/`, versionado para desplegar exactamente sus bytes. |
| Warehouse y Gold para perfiles que reconstruyen datos. | `publication_manifest.json`, con commit de código, contratos, archivos, tamaños, hashes e identidades de análisis. |
| Registros exactos de `analysis_runs/drafts/`, aprobaciones y fuentes exigidas por el perfil. | Recibos de intención/publicación en `analysis_runs/publications/`, privados e ignorados por Git. |
| Baseline, autoridad y recibos adicionales del alcance seleccionado. | Pruebas públicas del alcance cuando el perfil las exige; no los expedientes privados. |

Para revisar el sitio existente sin publicar:

```bash
python -m http.server 4173 --bind 127.0.0.1 --directory site
```

Para verificar una publicación conservada, usa el selector que ejecuta Pages:

```bash
python scripts/check_pages_publication.py site/
```

Selecciona el verificador exigido por los recibos del manifiesto; un fallo no
permite pasar a uno menos estricto. `src.publish.verify` es el verificador
general y sigue disponible, pero no sustituye los perfiles específicos.

## Flujo de trabajo

1. Identifica el cambio: presentación, fuente, datos financieros o lectura.
   Usa el perfil correspondiente de la referencia de abajo.
2. Confirma en Git el código y las entradas de compilación. El gate rechaza
   entradas modificadas sin commit porque el manifiesto identifica ese código.
3. Ejecuta el perfil con sus registros, fuentes y autorizaciones exactas.
   No inventes expedientes, pins o aprobaciones para superar los controles.
4. Verifica el resultado, incluye `site/` en el PR y sigue CI, revisión e
   integración conforme a [`AGENTS.md`](../../AGENTS.md).
5. Después de Pages, comprueba por HTTPS y navegador la versión servida.
   Un recibo de build no acredita el despliegue.

Ejemplo de la modalidad general con un registro ya aprobado:

```bash
uv run python -m src.publish --record analysis_runs/drafts/<periodo>/<version>.json --out site/
uv run python -m src.publish.verify site/
```

Este ejemplo no reemplaza las recetas de perfiles acotados.
La autorización permanente cubre cambios rutinarios solicitados sobre contenido
ya aprobado. Datos nuevos, cambios de significado y aprobaciones conservan
sus requisitos de autorización específica. No copies `web/dist/` a `site/`
a mano. Véanse [la guía web](../../web/README.md) y [el mapa del repositorio](../../REPO_MAP.md).

## Apéndice técnico: verificaciones comunes

### Construcción y sustitución

`gate.py` recibe uno o más registros y verifica
`consumer_payload` y `verified_inputs` bajo el bloqueo de escritura del
registro de aprobaciones. Si un registro no tiene aprobación vigente, lanza
`PublicationRefused` y el comando devuelve código 1 sin publicar.

En el perfil general, exporta los datos en una carpeta temporal, prepara
`web/public/data/v1/` y ejecuta `npm ci && npm run build` en `web/`.
Libera el bloqueo durante la compilación para no impedir una revocación humana.
Antes del intercambio atómico vuelve a verificar los registros bajo un bloqueo
nuevo, que conserva hasta sustituir `site/`. Así detecta una revocación
ocurrida durante el build. Vite ya incluye `public/` en `dist/`.

`manifest.py` registra el commit de código, los hashes de contratos y todos
los archivos de `site/` excepto el propio manifiesto, con orden, SHA-256 y tamaño.
Cada identidad de análisis conserva `period_id`, `version`,
`content_hash`, `evidence_fingerprint`, `approval_event` y `audit_hash`.
Los recibos privados identifican el hash del manifiesto; este ya enumera los
bytes de cada archivo.

`verify.py` valida el esquema del manifiesto, inventario completo, hashes,
tamaños, esquemas JSON, privacidad e identidades de análisis sin datos privados.
Los lectores resuelven los bytes del contrato exacto declarado, incluidos
Mercado y demanda aeroportuaria. Una edición nueva no amplía un contrato histórico.

`site/` se confirma en Git y Pages lo despliega sin modificar
`analysis_runs/`. Los verificadores fuertes usan dependencias del extra
`analytics` fijadas en `uv.lock`; Pages instala con
`--locked --no-group dev --extra analytics`, también para la vista previa con
su propio checkout. Instalar dependencias no ejecuta ingestas o modelos.

Si el replay del productor AFAC falla, agota su tiempo o no devuelve el resultado
esperado, su wrapper conserva stdout, stderr y los diagnósticos anidados antes
de retirar el checkout temporal. Quedan bajo
`tmp/approval-replay-diagnostics/afac-replay-*/`, privados e ignorados por Git.
El manifiesto de cada intento identifica el productor, el resultado y los
tamaños y SHA-256 de los archivos conservados. Revisa esa evidencia antes de
decidir una corrección o un nuevo intento; el error exterior puede ocultar el
rechazo original del productor padre. La retención no cambia el rechazo, los
controles ni las aprobaciones. Los enlaces simbólicos y junctions se rechazan;
si tampoco se puede conservar el diagnóstico, la ejecución sigue fallando y
lo indica. Estos archivos no forman parte del sitio público.

### Cambios de presentación y datos preservados

- `--ui-only` exige que todo `site/` coincida por bytes con un commit fijado
  de `origin/master`. Reproduce cada aprobación exacta con su implementación
  retenida y reutiliza los JSON públicos sin llamar al warehouse. Conserva
  hashes y tamaños de todos los datos y los contratos del manifiesto confiable.
  Repite las comprobaciones antes del intercambio, rechaza un remoto que se
  movió y verifica el candidato después de los controles lentos.
- `--presentation-only` comprueba además el sitio servido y la cadena exacta
  trimestral/AFAC, con fuentes, aprobaciones, revocaciones y solicitud privada.
  Solo permite cambiar `index.html` y `assets/**`; conserva los otros HTML,
  sus recursos y todos los datos, contratos, fuentes, recibos y evidencias.
  Repite la cadena bajo bloqueo antes y después del build. El marcador HTML
  liga la interfaz al commit confiable y al productor AFAC original.
  No reconstruye datos ni crea aprobaciones; el verificador `--ui-only`
  histórico permanece separado.
- `--business-metrics-only` conserva el baseline público exacto y la aprobación
  editorial vigente. Añade solo métricas y recibo con sus pins independientes,
  valida el candidato y repite baseline y aprobación bajo bloqueo antes del
  reemplazo.
- `--preserve-published-data` conserva todos los bytes de `data/v1/` del
  sitio exacto de `origin/master`, con sus renderizadores, fuentes y contratos.
  Reproduce expedientes y aprobaciones por cohorte antes y después del build;
  no ejecuta modelos ni activa nuevos datos.
- `--flights-only` proyecta las celdas aceptadas de 2T26 sobre el sitio
  auditado. Exige la edición exacta, cada valor sustituido y reconciliación
  por operador, mes y ámbito. Conserva el resto de los datos y aprobaciones
  antes y después del build, sin reconstruir warehouse u otros exportadores.
  La autorización retenida del 19 de octubre cubre esa proyección y su tarjeta
  ponderada, no tesis nuevas, M11 o calendarios.

Ninguna modalidad convierte datos editados en aprobados mediante un manifiesto
nuevo. El producto `official_routes` tiene una receta separada:
[alcance y controles del mapa oficial](../../docs/mapa-oficial.md).

### Aprobaciones, entidades y reproducción histórica

`config/publish/preserved-analysis.json` identifica la implementación original
de lecturas congeladas. El gate contrasta manifiesto, ascendencia publicada,
identidades y bytes, y repite los cuatro registros con expedientes y revocaciones
actuales antes y después del build. `code_commit` identifica el código que
genera la interfaz actual; conservar la implementación anterior no aprueba
contenido nuevo.

`config/publish/approval-cohorts.json` fija, por cohorte, aprobación completa,
commit del verificador y hash/tamaño del JSON público. Los pins se leen del
commit confiable y deben cubrir todas las identidades sin duplicados ni
huérfanos. Rama y verificador nuevo deben descender de la publicación confiable;
los verificadores históricos deben pertenecer a su historia publicada.
La configuración de trabajo debe coincidir con la confirmada en Git.
Un trimestre nuevo admite solo el pin adicional comprometido y ligado al
registro aprobado; un pin no concede aprobación. Todo se repite bajo bloqueo.

Los registros por entidad usan
`analysis_runs/drafts/<entity_key>/<period>/<version>.json`.
Pasa cada registro con `--record`; el gate rechaza dos versiones de la misma
entidad y trimestre. La ruta histórica `data/v1/analysis/<period>.json`
corresponde a Aeroméxico. Las nuevas lecturas usan
`data/v1/analysis/<entity_key>/<period>.json`, con entidad coherente entre
ruta, encabezado y manifiesto.

La paridad reproduce la configuración del sitio publicado en un worktree
aislado, no un pin pendiente de HEAD. El sitio de cuatro lecturas exige esas
cuatro identidades; la quinta se exige cuando el manifiesto incorpora
Aeroméxico 3T26. Los artefactos deben estar confirmados antes de esa prueba.

`--financial-publication-base` verifica una publicación SourceData intacta
con su productor publicado, aislado y sin red. Exige base exacta del historial
de `origin/master`, inventario y bytes completos, autoridad y contratos
conservados y el mismo lock de Python. No aprueba un runtime nuevo:
sus tipos, build y pruebas se verifican aparte. El gate conserva su rechazo
ante una huella distinta y no usa otra vía tras un fallo histórico.

## Referencia de perfiles acotados

Las recetas siguientes conservan los límites de cada entrega implementada.
Un periodo citado restringe ese perfil; no describe por sí solo el último
periodo del dashboard. Consulta el manifiesto servido y
[la guía de periodos](../../docs/periodos-dashboard.md) para el estado actual.

### Entrega independiente de Viva y Volaris 3T26

`src.publish.issuer_update` incorpora una entidad por ejecución desde un paquete
`issuer_quarter_v1` aprobado, con replay físico de fuentes, cálculo, auditoría y
ledger. La proyección validada es la frontera pública: no concatena observaciones
candidatas con `fact_carrier_metrics`, no reconstruye el warehouse ni altera la
historia. Usa las gráficas existentes y mantiene separados pasajeros con boleto,
ocupación regular y medidas totales. El comparativo anual del reporte afecta solo
la vista nueva; no reemplaza una cifra histórica de distinta precisión/edición.

Las etapas son independientes. `data_only` recibe el paquete técnico validado,
auditoría independiente de la fuente/proyección y autorización específica de
datos; verifica los registros históricos, sin exigir una tesis nueva ni modificar
su ledger. `editorial_only` añade después una tesis aprobada y conserva el
ejecutivo idéntico. `combined` permite una entrega con ambas partes ya listas.
El ancla liga `stage`, `package_id`, `evidence_fingerprint`, `source_binding`
exacto y las salidas revisadas. No hereda autorización de otra fuente o periodo.

El baseline debe coincidir con Git remoto y Pages/HTTPS. Su verificador original
liberado comprueba íntegramente sus bytes; fallar con un runtime posterior no
autoriza ignorar un error histórico. Los registros anteriores se reproducen por
sus cohortes y el registro nuevo con el productor actual, antes y después del
build. Solo cambian la tesis nueva, el bloque ejecutivo de esa entidad y el recibo
`issuer-publication.json`. Industria, las otras entidades, frontend y todos los
demás datasets se conservan. No hay una barrera que espere otras aerolíneas.
Si el baseline lleva el marcador HTML de una publicación de tarifas o de
presentación, primero lo autentica su verificador histórico. La comparación
del frontend aplica ese mismo marcador al build nuevo y exige igualdad exacta
de todo el cierre de archivos; el emisor conserva el HTML y los recibos servidos.

```bash
python -m src.publish.issuer_update --inspect-data <paquete-tecnico.json>
# Retener auditoría y autorización auténticas ligadas al binding exacto mostrado.
python -m src.publish.issuer_update --prepare-data <paquete.json> --data-authorization <autorizacion-por-hash.json>
# Confirmar el ancla; solo se conservan las cohortes anteriores.
python -m src.publish.issuer_update --record <cada-registro-anterior> --package <paquete.json> --out site/
# Después del despliegue de datos, añadir la tesis de forma independiente:
python -m src.publish.issuer_update --prepare-record <registro-nuevo-aprobado> --editorial-only
```

Para la entrega combinada, cuando ambas partes ya estén aprobadas:

```bash
python -m src.publish.issuer_update --prepare-record <registro-nuevo-aprobado>
# Revisar y confirmar los pins de issuer-release.json y approval-cohorts.json.
python -m src.publish.issuer_update --record <cada-registro-anterior> --record <registro-nuevo> --out site/
python -m src.publish.issuer_scope site/
```

La preparación genera pins reproducibles de entidad/periodo, aprobación,
SHA/tamaño de las dos salidas y huella del productor; no aprueba contenido. Un
registro idéntico ya servido se reconcilia sin otra publicación. Una edición
distinta del mismo periodo requiere `--replace-version <version-servida-exacta>`:
el ancla fija el registro y archivo anteriores, y la nueva versión debe estar
auditada y aprobada. El gate reproduce ambas aprobaciones y sus fuentes; reemplaza
solo ese slot, conserva los demás pins y no revoca ni elimina la versión anterior.
Seleccionar los registros que seguirán publicados y el nuevo; el registro anterior
se recupera de su ruta canónica privada. El modo está limitado a las ediciones
verificadas Viva/Volaris 3T26;
un trimestre nuevo requiere extender y revisar su adaptador, no cambiar una fecha.

`issuer_authority` verifica los JSON privados retenidos por SHA-256 bajo
`analysis_runs/dashboard_updates/authorizations/` y `audits/`: estado vigente,
consentimiento auténtico, auditoría independiente sin hallazgos pendientes y el
binding exacto de fuente, paquete, baseline, productor y salida. Solo data-only
usa esa autoridad: nunca crea eventos de aprobación editorial. Una actualización
sin efecto visible se reproduce con `issuer_update.verify_no_visual_change`;
una etiqueta del worker no sustituye esa comprobación. Macro/cotizaciones no
alimentan las gráficas servidas actuales: Mercado usa pasajeros AFAC.

Pages selecciona el perfil vigente entre los recibos declarados y conservados,
según la precedencia Git descrita abajo, sin fallback.
Los recibos financieros/editoriales anteriores siguen como evidencia histórica;
no afirman que su antiguo alcance incluya esta actualización. La verificación
offline prueba integridad, pins y preservación, y reproduce el verificador del
baseline; no autentica por sí sola observaciones remotas. El gate observa la red
y el agente comprueba por HTTPS la versión realmente servida tras el despliegue.
Build, merge y publicación servida son estados distintos. La
[skill del agente dashboard](../../.agents/skills/airline-update-dashboard/SKILL.md)
documenta QA, recibos, integración y recuperación idempotente.

### Corrección de movimientos Aerocivil

`src.publish.movements_update` prepara y publica exclusivamente la corrección
semántica de Aerocivil en la red internacional existente. El perfil privado
reproduce los originales retenidos y la certificación nativa de julio; conserva
captura, SHA, metadatos y supuestos. Si el verificador dedicado rechaza una
certificación por cambio de productor, requiere otra certificación offline
aislada desde esos originales, sin HTTP ni renovar sus fechas. Un recibo global
antiguo no se revalida con otro runtime: se conserva con su código histórico.
Movimientos provisionales permanecen separados de salidas; no se dividen entre
dos ni certifican vuelos regulares o cobertura trimestral completa.

La solicitud privada tiene `schema_version: aerocivil_movements_request_v1`,
`source_profile: {path, sha256}`, los siete `record_paths` exactos del manifiesto
publicado y `authorization: {path, sha256}`. Para inspeccionar antes de retener la
autorización, usar `authorization: null`. El perfil contiene sus originales y
metadatos fijados por SHA, referencia de aeropuertos, `july_item` certificado y
`round_as_of` original con zona horaria. El esquema
`aerocivil_movement_source_profile_v1` exige tres originales: histórico de
8/sep, corte 2T26 de 19/oct y julio de 21/oct. Cada original y la referencia
declaran `path`, `sha256`, `metadata_path` y `metadata_sha256`. Sus archivos
físicos y el candidato/disponibilidad deben materializarse en el checkout
consumidor; cambiar rutas no cambia sus bytes, capturas ni ediciones.
La proyección cubre exactamente 38 redes existentes y `flights/quarters.json`;
Industria cambia solo en el widget de datos, nunca en su tesis.
`movements_history.source_projection` verifica ese cierre físico, devuelve las
filas tipadas y la proyección acotada. La lista de archivos públicos procede del
alcance revisado en `movements_scope.TARGETS`; no se infiere desde un candidato.

```bash
python -m src.publish.movements_update --inspect <solicitud-privada.json>
# Retener consentimiento auténtico con el authority_scope exacto de la inspección.
python -m src.publish.movements_update --prepare <solicitud-privada.json>
# Revisar y confirmar config/publish/aerocivil-movements-release.json.
python -m src.publish.movements_update --request <solicitud-privada.json> --out site/
python -m src.publish.movements_scope site/
```

La autorización privada se conserva en
`analysis_runs/dashboard_updates/authorizations/<SHA256>.json` y contiene
`schema_version: aerocivil_movements_authorization_v1`, `status: authorized`,
`scope` idéntico a `authority_scope` y
`owner_consent: {source_reference, instruction, received_at}` con referencia a
la delegación auténtica, instrucción literal y recepción real con zona horaria.
No inventar identificadores de mensajes ni presentar una delegación como cita
verbatim del usuario. El publicador solo la lee: no
crea consentimiento, aprobaciones ni eventos editoriales. El ancla pública fija
su hash, baseline, productor, fuente nativa, proyección y recursos compilados;
los expedientes privados no se incorporan al repositorio público.

El gate reproduce el verificador liberado del baseline y las siete aprobaciones
con sus cohortes originales. Comprueba baseline remoto y bytes servidos, y repite
replay de fuente, autorización y cohortes bajo el lock antes del intercambio
atómico. Coteja el cierre físico, metadatos Library, ledger, código, ancla y remoto
tras los verificadores lentos. Conserva todas las tesis, datos financieros y bytes
ajenos a los targets; permite solo sus payloads de movimientos, el contrato de
Vuelos y la nueva clausura frontend revisada. Conserva los recursos históricos.
La selección conjunta de aerolíneas combina únicamente componentes de
movimientos con grano operador, designador literal, sentido y mes distintos.
Conserva SHA y locator de cada original, rechaza duplicados o ediciones
superpuestas y reconcilia cada subtotal; nunca suma esos movimientos a vuelos.

Tras cambiar datos o tesis de `site/`, ejecutar
`python -m scripts.chat.render_f29_coverage_matrix` y las pruebas
`python -m pytest tests/test_chat_f29_final_campaign_preflight.py -q` antes de CI.
La matriz F2.9 deriva los bytes conversacionales del sitio actual: se regenera
la documentación, conservando fixture, Gold y pins, sin ejecutar campañas.

Pages, outbox y el lector de baselines históricos comparten el selector de
`check_pages_publication.py`. Cada recibo declarado debe coincidir con el SHA y
el tamaño del manifiesto y nombrar un objeto commit existente. Si conserva
varios recibos, el vigente es el único cuyo baseline Git desciende estrictamente
de los demás. Empates, ramas ajenas, historial ausente, pruebas alteradas o
perfiles desconocidos bloquean; ninguna fecha de archivo o bandera JSON elige
el gate. Después de elegir, el verificador específico comprueba toda su ancla,
alcance y fuentes según corresponda. La relación Git no concede aprobación.
Esto permite movimientos → financiero/issuer → movimientos con revisión propia,
sin hacer permanente la prioridad de un recibo histórico. Las pruebas de paridad
siguen la misma cadena, conservan ejecutivo y siete tesis en el salto de
movimientos y reproducen la fuente financiera original. El recibo
acredita `site_built_verified`; solo QA posterior por HTTPS acredita lo servido.
No usar `--ui-only`, el scope financiero ni `flight_evidence_v1` para esta entrega.

Cierre documental: se conservan el publicador y sus pruebas como procedimiento
reutilizable; esta guía y la skill del dashboard son la referencia vigente. El
perfil, consentimiento y recibos quedan privados como evidencia de recuperación.

### Publicación editorial acotada

El dueño autorizó el 24 de octubre separar la lectura de los indicadores.
`--editorial-only` recibe únicamente el registro nuevo aprobado de Aeroméxico
3T26. Verifica sus fuentes, cálculos, auditoría y aprobación con el lifecycle
actual, nuevamente bajo lock antes del reemplazo atómico. No modifica
`executive.json`, métricas del chat, noticias, vuelos ni las cuatro tesis 2T26.

La autoridad del baseline es el commit remoto de `master`, fijado en
`config/publish/editorial-release.json` y revisado en el PR. El gate exige una
corrida Pages exitosa con exactamente ese árbol `site/` (el commit de despliegue
puede ser anterior si el árbol permanece idéntico). Comprueba el manifiesto y
cada archivo servido por HTTPS contra sus bytes en Git, antes y después del
build; rechaza redirecciones y cambios remotos concurrentes. No usa un baseline
local autofirmado. El ancla también fija los bytes aprobados de la tesis y el
inventario exacto de recursos compilados del dashboard. Conserva los recursos
anteriores y el HTML de las otras aplicaciones.

`python -m src.publish.editorial site/` es el verificador explícito de esta
modalidad. Contrasta el recibo editorial contra el ancla comprometida y el
árbol Git; conserva los contratos históricos, aprobación histórica e inventario, y aplica
todos los controles estructurales y de privacidad. Solo para los bytes
históricos demostrados omite la reproducción semántica de noticias y métricas.
El recibo registra observaciones del gate; el verificador offline no autentica
por sí mismo una observación de red ni reproduce las fuentes antiguas. Esta
garantía se sustituye por la identidad exacta con el despliegue anterior
verificado. El verificador general `src.publish.verify` conserva sus controles.
Pages selecciona el verificador vigente según los recibos que declara el
manifiesto. Cuando solo declara `editorial-publication.json`, exige el
verificador editorial y su ancla exacta, sin fallback ante errores. Si conserva
otros recibos, aplica la precedencia Git. Un sitio sin recibos declarados usa
el verificador general, aunque un ancla histórica siga en Git.
Un recibo aislado nunca concede autoridad. El gate de la modalidad posterior
sigue exigiendo sus aprobaciones y fuentes; no hereda la excepción editorial.
CI y revisión siguen siendo obligatorios y la publicación se comprueba por HTTPS.

El contrato adicional `analysis_editorial.schema.json` se aplica exclusivamente
a `data/v1/analysis/2026Q3.json`. Fija el trimestre y la entidad y admite la
distribución primaria del comunicado en GlobeNewswire. Su hash se añade al
manifiesto y al ancla revisada; todos los hashes de contratos previos permanecen
intactos. No amplía los dominios permitidos para las cuatro tesis históricas.
El verificador y el lector de snapshots resuelven ese hash exacto, sin fallback.
Las últimas comprobaciones de código, ancla, baseline y remoto se repiten después
de las verificaciones lentas, dentro del callback previo al intercambio; el lock
excluye cambios del ledger, no movimientos externos de GitHub.

La lectura obtiene los trimestres disponibles de `analysis_manifest` y usa
`readingPeriod` en la URL. No añade observaciones financieras ni altera el
selector compartido de indicadores y vuelos. La herramienta financiera del
chat mantiene su edición anterior. Monthly permanece separado y privado.

```bash
python -m src.publish --editorial-only --record <registro-3T26-aprobado> --out site/
python -m src.publish.editorial site/
```

### Publicación financiera completa

La modalidad general `--quarterly-only` agrega
solo `analysis/2026Q3.json` y la proyección ejecutiva de Aeroméxico del
paquete primario auditado. Conserva byte por byte los demás datasets,
incluidos vuelos mensuales, noticias y las cuatro tesis de 2T26. Dentro del
ejecutivo, conserva los registros y vistas previos y los tres bloques de
entidades sin actualización. El selector financiero incorpora 3T26; el mapa
mantiene sus cortes de cobertura propios.

Se proporcionan los cuatro registros publicados exactos y el nuevo registro
aprobado mediante cinco opciones `--record`. El gate verifica las cuatro
aprobaciones históricas con su implementación original y la nueva con el
runtime actual. Repite la verificación de expedientes, fuentes y baseline
bajo lock antes del reemplazo atómico, y valida el candidato contra contratos
y privacidad. El contrato anterior de citas queda retenido por hash para
seguir verificando el sitio histórico; esa retención no concede aprobación.

La conversión de indicadores nativos por asiento-milla a asiento-kilómetro
usa 1.609344. No se equipara CASM publicado con el gasto total del estado de
resultados; los comparativos calculados desde valores redondeados pueden
diferir de los porcentajes del comunicado. No se reconstruyen meses, Gold,
modelos, calendarios ni tesis de otras entidades.

La tabla financiera estructurada del chat mantiene su edición aprobada anterior.
Una consulta de ingresos de 3T26 por esa herramienta devuelve el periodo faltante;
no toma el ingreso de 2T26 ni transforma automáticamente la tesis en otra edición
de métricas. La medición offline del chat distingue ese faltante del nuevo periodo
ejecutivo y conserva el fixture histórico de campaña.

```bash
python -m src.publish --quarterly-only --record <registro-historico> --record <otros-registros-exactos> --record <registro-3T26-aprobado> --out site/
python -m src.publish.verify site/
```

```
uv run python -m src.publish --record analysis_runs/drafts/2026Q2/<hash>.json --out site/
uv run python -m src.publish --ui-only --record analysis_runs/drafts/2026Q2/<hash>.json --out site/
uv run python -m src.publish --business-metrics-only --record analysis_runs/drafts/2026Q2/<hash>.json --out site/
uv run python -m src.publish.verify site/
```

## Comando de prueba focalizada

```
uv run pytest -q tests/test_publish_manifest.py tests/test_publish_verify.py tests/test_publish_ui_only.py
```

Los casos negativos de `tests/fixtures/site/` prueban bytes alterados,
archivos añadidos o ausentes, aerolíneas prohibidas, campos no declarados
y aprobaciones mal formadas. Corren en CI sin datos privados.
`tests/test_publish_gate.py` prueba el gate completo con warehouse y registros
aprobados (`local_data`); `tests/test_site_parity.py` verifica la paridad
visible del sitio (`browser` + `local_data`).

El ledger conserva aprobaciones técnicas históricas cuando cambia la huella
de implementación. Para reproducir una publicación, selecciona todos sus
registros exactos con `--record`; toma las identidades de
`site/publication_manifest.json`. El descubrimiento automático rechaza
múltiples versiones aprobadas de una misma entidad y trimestre. En un
export de desarrollo, pasa ese `analysis_manifest` explícitamente a
`src.web_export.analysis.export_analysis(..., manifest=...)`; no revoques
autorizaciones históricas ni elijas una versión por fecha para eludir el guard.

### Indicadores financieros sobre una lectura ya publicada

`--financial-kpis-only` añade exclusivamente los registros/vistas financieros
Aeroméxico 3T26, con las cuatro tarjetas y gráficas existentes. La lectura 3T26,
las cuatro lecturas históricas, contratos y todos los demás archivos de datos
permanecen idénticos. Dentro de `executive.json` se conserva la serialización de
los registros/vistas anteriores y los bloques de Industria, Volaris y Viva;
solo se añade el trimestre Aeroméxico y metadatos de cobertura permitidos. El
trimestre global inicial conserva el corte común anterior. Un enlace con
`period=2026Q3&sel_kpis=AEROMEXICO&sel_unit=AEROMEXICO&sel_volume=AEROMEXICO&sel_load=AEROMEXICO`
selecciona los nuevos indicadores. Un competidor sin ese trimestre muestra
faltantes; Vuelos identifica su corte real sin reemplazar la cabecera financiera.

La autoridad nueva es `config/publish/financial-release.json`, comprometida y
revisada: fija baseline Git/manifiesto servido, aprobación original y productor
congelado de la tesis, paquete/cálculos, productor financiero revisado,
bytes/SHA del nuevo `executive.json`, cierre de recursos frontend y hash de la
autorización financiera privada. Esta última conserva el consentimiento explícito
del dueño para esta exposición, alcance, salida exacta y revisión independiente;
no crea ni renueva una aprobación de la tesis. Una autorización revocada,
alterada o sin revisión exacta rechaza la publicación.

El gate reproduce íntegramente las fuentes y el lifecycle de a470 mediante su
implementación original y conserva el payload público ya aprobado. Reproduce la
proyección con el productor financiero archivado, incluidas sus dependencias.
Comprueba todo el baseline remoto y HTTPS antes/después del build. Bajo el lock
común repite aprobación/fuentes y verifica finalmente HEAD, baseline remoto,
autorización, captura de fuentes y candidato después de los verificadores lentos.
No solicita la reconstrucción de las cohortes históricas que no cambian.

TRASM significa ingreso **total** por asiento-milla; el RASK de estas tarjetas
es su conversión por 1,609344 a centavos USD por asiento-kilómetro. No se usa
solo ingreso de pasajeros ni yield. Los ingresos/ASM publicados reproducen el
crecimiento reportado de 12,2% a su precisión visible, mientras el cociente de
TRASM redondeado 17,2/15,4 da 11,7%. Ambas bases quedan documentadas. CASK conserva
CASM reportado convertido: crecimiento anual reportado 19,4%, frente a 18,9%
calculado con 15,1/12,7. No se fuerza equivalencia con gastos del estado de
resultados. Las comparativas anuales usan el reporte 3T26; las trimestrales y
el margen unitario usan la serie publicada. El comparativo de ocupación 3T25
88,2% del nuevo reporte no sustituye el 88,3% histórico. Trimestre, nueve meses
y saldos al cierre se mantienen separados.

Una publicación cuyo perfil vigente es `financial-publication.json` exige
su verificador financiero, sin fallback ante errores; exige ancla, output y
recursos exactos, preservación estructural/bytes, contratos y privacidad. El
recibo editorial anterior se conserva como evidencia histórica. Una publicación
UI posterior sin recibo financiero usa el verificador general y conserva todos
sus controles; además revalida la autorización/fuentes financieras antes y
después del build y tras el verificador lento del candidato. No permite omitir
esa autoridad eliminando el ancla o una de las señales del trimestre.

```bash
python -m src.publish --financial-kpis-only --record <registro-a470-existente> --out site/
python -m src.publish.financial_scope site/
```

Para verificar **solo localmente** un runtime nuevo que conserva esa publicación,
existe `python -m src.publish.financial_continuity site/ --local-only`. Exige
`config/publish/financial-continuity-local.json` comprometido, con consentimiento
del procedimiento local y hash de una revisión independiente privada exacta.
La política vincula el commit/runtime técnico, los 811 archivos publicados y la
clausura completa de fuentes y aprobaciones. Reproduce el verificador y productor
originales, conserva la autoridad financiera y repite las comprobaciones después
de los verificadores lentos, bajo el lock del ledger. No escribe el sitio ni
crea aprobaciones o recibos de publicación. La confianza procede de la política
Git revisada y su informe verificado; el hash no autentica criptográficamente al
revisor. La cadena recuperada acredita su snapshot, no eventos externos posteriores.

Las pruebas reales seleccionan expresamente este procedimiento con
`--financial-continuity-local --require-local-data`. Sin un perfil explícito
conservan el verificador ordinario. El gate financiero, Pages y `--financial-kpis-only` no
consumen esta política local ni aceptan por ella otro runtime. Esta comprobación
no concede integración, publicación, ingestas o activación de calendarios.

CI pública dispone de un perfil de pruebas retrospectivo separado:
`--financial-publication-base <SHA-base-confiable>`. Solo verifica el sitio ya
publicado, íntegramente idéntico a esa base Git, con el código señalado por el
manifiesto de esa publicación. Exige base en la rama protegida, ancla y autoridad
pública intactas, dependencias bloqueadas idénticas y ejecución archivada sin
red ni imports desde HEAD. Repite la comprobación de entradas al terminar.
No consume el consentimiento local ni aprueba el runtime de la rama para publicar.
El perfil local y el retrospectivo son mutuamente excluyentes y no tienen fallback.
El workflow conserva el mismo subconjunto de pruebas: selecciona retrospectiva
solo si `site/` no cambia frente a la base del evento; una publicación cambiada
conserva el perfil ordinario. Las omisiones por expediente privado ausente siguen
explícitas; no sustituyen el replay completo que exige la validación local.

Las pruebas financieras específicas no dependen del warehouse. Con
`--require-local-data` fallan si falta el candidato o expediente nuevo, y
reproducen las fuentes completas. Los verificadores generales permanecen intactos;
las excepciones semánticas de datos antiguos solo aplican tras demostrar sus
bytes exactos contra Git y el baseline servido. CI, revisión, merge normal,
Pages y verificación real por HTTPS siguen siendo obligatorios.


### Llegadas mensuales de datos por fuente

`src.publish.source_data_update` incorpora una fuente validada sin esperar otra
fuente ni redactar una tesis. Conserva íntegro el manifiesto editorial servido
(siete lecturas en el corte de octubre de 2026), reproduce sus cohortes con sus
productores históricos y cambia solo el payload de su adaptador revisado.
Aeroméxico IR añade una serie corporativa mensual separada en
`flights/quarters.json`; no sustituye AFAC ni agrega un trimestre desde un mes.
Los adaptadores aeroportuarios usan su propio universo de demanda.

El request privado `source_data_request_v1` declara `product`, `period`,
`source_profile: {path, sha256}`, `record_paths` con todos los registros exactos
del manifiesto anterior y `authorization`, inicialmente `null`. El perfil AM
`am_monthly_source_profile_v1` contiene `item` de readiness y `as_of` congelado.
El replay contrasta originales, sidecars, recibos, siete salidas y disponibilidad
al corte retenido; una recuperación no acredita actualidad del día de ejecución.

```bash
python -m src.publish.source_data_update --inspect <request.json>
# Retener la autorización de exposición real para authority_scope exacto.
python -m src.publish.source_data_update --prepare <request.json>
# Revisar y confirmar config/publish/source-data-release.json en Git.
python -m src.publish.source_data_update --request <request.json> --out site/
python -m src.publish.source_data_scope site/
```

`--inspect` no concede autoridad. `source_data_authorization_v1` exige estado
`authorized`, el `scope` exacto inspeccionado y `owner_consent` con referencia,
instrucción y fecha reales; vive por hash en el ledger privado de autorizaciones.
No se fabrica desde un candidato ni reemplaza la aprobación editorial. El gate
repite fuentes, cohorte, hashes, identidad Library y baseline antes del intercambio
atómico. Requiere Git y Pages vigentes, no acepta una salida de otro producto,
no activa Gold/warehouse ni permite `--ui-only` para introducir datos nuevos.

El outbox mensual entrega `release_kind=source_data` al agente dashboard con
su skill existente. Una llegada recuperada conserva el documento original y su
fecha de captura; no crea una ejecución programada histórica inexistente. El
build local, la integración y la comprobación HTTPS/browser servida se registran
como estados distintos conforme al flujo general.


Una llegada `source_data` cuyo resultado ya coincide termina con
`source_data_update.verify_no_visual_change`: reproduce fuente/alcance, contrasta
bytes con el baseline Git, verifica cohortes y conserva un recibo de equivalencia
sin build ni nueva autorización editorial. El outbox revalida ese recibo antes
de cerrar `no_change`. Si el mismo gate ya produjo el build exacto, su recuperación
revalida fuente, autoridad vigente, aprobaciones, manifiesto y pins; devuelve
`already_built_verified` sin otro intercambio ni recibos de publicación duplicados.
Eso no acredita el despliegue ni sustituye la verificación servida.
Los payloads nuevos se serializan como JSON estricto: NaN e infinitos bloquean.


El request puede añadir `additional_sources`, una lista opcional de unidades
`{product, period, source_profile: {path, sha256}}` ya listas. No existe una lista
global obligatoria: una sola fuente sigue siendo una entrega válida. Cada unidad
se reproduce por separado; las proyecciones se componen preservando lo que la
anterior cambió. El alcance de autorización contiene los bindings individuales
y los pins finales. Esto permite reunir fuentes listas que comparten payload en
un build y PR, sin esperar otra fuente. Un miembro inválido no autoriza publicar
el lote; se conserva su evidencia y se puede entregar cualquier unidad válida
mediante la modalidad individual. Los jobs restantes pueden comprobar la versión
ya servida con su equivalencia física, sin otro build ni publicación.

En fuentes con rezago admitido por el calendario, el ledger conserva el mes
solicitado y `source_period` nativo. Readiness y el binding usan el mes real del
original. Por ejemplo, una tarea de septiembre puede entregar AFAC agosto o BTS
julio; no se etiqueta el contenido como septiembre. El publisher usa ese mes
nativo en su request y la verificación del handoff coteja ambos contextos.

La llegada BTS liga el ZIP original al `source_hash` literal de
`silver/bts_t100_segment`, sólo después del replay completo de Gold y linaje.
Silver debe figurar en los hashes de salida comprobados y sus bytes deben
coincidir: el `source_hash` de Gold es un agregado, no el SHA literal del ZIP.
Las demás llegadas conservan su comprobación del original contra Gold.


La proyección corporativa mensual de Viva y Volaris es independiente de la de
AM y de AFAC. Guarda cada emisor en `corporate_peer_monthly_passengers` sin tocar
el bloque de la otra aerolínea. La gráfica existente ofrece la base corporativa
para una sola aerolínea y conserva AFAC en comparaciones. Son tramos reservados,
incluido fletamento, con unidad, preliminar y atribución del reporte. Muestra el
mes y su comparativo anual de la misma edición, con documento/captura y fuente;
no activa una historia retrospectiva, acumulados ni un trimestre incompleto.

## Sustitución explícita de fuentes y lecturas de 3T26

`quarterly_story_release_v1` reúne cuatro nuevas lecturas y doce salidas de
datos reproducidas: Industria financiera, AFAC de septiembre, las observaciones
ANAC de Brasil y el archivo de noticias aprobado. Cada lectura conserva su
versión, auditoría independiente y aprobación propias en el lifecycle normal.
Las 23 noticias nuevas requieren además la decisión real del lote y los hashes
de sus registros; el gate rechaza una preview o un índice anterior incompleto.
Los indicadores financieros de los tres emisores se cotejan con las fuentes
antes de calcular Industria. No se activan modelos ni estimaciones candidatas.

El adaptador nuevo de Volaris conserva cuatro respuestas HTTP originales de SEC,
sus fechas y SHA-256. Comprueba 446 celdas y 187 reconciliaciones. Distingue los
bytes recibidos del documento cuyo tamaño declara el índice SEC: sólo admite el
script vacío exacto observado al final de ambas respuestas y retiene una prueba
separada de tamaños y hashes. Un script distinto, duplicado, con contenido o en
otra posición bloquea. Los importadores de reconstrucciones Library y sus
controles anteriores permanecen intactos.

La sustitución no consume las tres lecturas Q3 anteriores como fuente. Conserva
sus registros y aprobaciones históricos y los contrasta con Git y el ledger;
declara expresamente que su fuente no se volvió a reproducir. La autoridad nueva
debe nombrar las cuatro versiones, la sustitución y la proyección exactas. Las
cuatro lecturas Q2 sí repiten la verificación original completa de fuentes,
cálculos y aprobación y permanecen idénticas. Una revocación durante el build
bloquea el intercambio, incluidas las aprobaciones Q2 conservadas.

La preparación se ejecuta en un checkout limpio del commit real, con expediente
privado restaurado y warehouse regenerado desde Gold. El extractor histórico de
Industria Q2 requiere Linux por sus supuestos de rutas; no se modifica su cápsula
fijada por hash para ejecutarla en Windows. El transporte puede copiar y cotejar
bytes cuando Windows rechaza crear enlaces; eso no elimina las restricciones del
extractor ni fabrica atributos Library.

```bash
python -m scripts.prepare_quarterly_story_release --descriptor <descriptor-privado.json> --output tmp/source-updates/story-release-final
# Auditar las cuatro versiones y el scope; conservar la decisión auténtica.
python -m src.publish.quarterly_story_update --prepare <request-autorizado.json>
# Revisar y confirmar config/publish/quarterly-story-release.json.
python -m src.publish --quarterly-story-request <request-autorizado.json> --out site/
python -m src.publish.verify site/
python scripts/check_pages_publication.py site/
```

La preparación sólo importa borradores y produce material para revisión. El gate
exige código y ancla confirmados, autoridad y auditoría exactas, baseline remoto
y servido, repetición de fuentes y aprobaciones y sustitución atómica. Pages
selecciona `quarterly_story_scope` por su prueba declarada; un fallo no cae a otro
verificador. El PR, CI del head final, revisión independiente, merge y comprobación
HTTPS/navegador siguen siendo obligatorios. Un artifact de Actions acredita sólo
lo que contienen sus hashes y recibos; no acredita una publicación servida.

### Corrección histórica compuesta de AFAC y comparativos BTS

`afac_history_update` prepara una corrección de datos sobre un padre trimestral
verificado que todavía no fue servido. El perfil cerrado distingue el baseline
servido A, observado físicamente mediante HTTPS, del padre B en Git. B conserva
su productor original `602ea2a4…`, su commit de código `2f6045aa…`, el scope
`708bedf9…` y las ocho identidades de lectura. No se renueva una tesis ni se
transfiere esa autoridad editorial a los datos corregidos.

Los únicos miembros admitidos son `afac_carriers_history` (ocho originales
2019–2026, Mercado y el bloque AFAC `monthly_passengers` de Vuelos) y
`bts_unchanged_source_comparisons` (julio de 2026, dos archivos y únicamente
`routes[*].previous.departures`). El segundo recalcula sólo comparativos
regulares previamente existentes, desde los ZIP originales y el crosswalk
fijado; mantiene elegibilidad, razones, hechos actuales y faltantes sin respaldo.
El resto del sitio, incluidas las ocho lecturas y sus aprobaciones, permanece
idéntico a B. Los contratos de los perfiles y sus proyecciones cierran el alcance;
no se acepta una lista libre de parches o de adaptadores.

El miembro AFAC exige además `native_dataset`, validado por el adaptador normal
cerrado. Sus cinco Gold DATA canónicos deben coincidir por SHA tanto físicamente
como en HEAD y forman parte del cierre de insumos; Gold de evaluación permanece
separado e inmutable. Sin ese adaptador o sin el cierre, la inspección falla.
Las cinco copias usadas como baseline de preservación deben coincidir además con
los Gold del commit original de B en Git, sin sustituirlos por otro dataset válido.

El expediente original de B se restaura separado de Gold corregido: un inventario
ordenado `afac_history_parent_inputs_v1` fija cada archivo por ruta, tamaño y SHA.
No incluye código ni lifecycle. El ledger vigente se incorpora aparte para
reproducir las fuentes, cálculos y aprobaciones originales y detectar revocaciones.
La reproducción se ejecuta con código original; el extractor Q2 sigue requiriendo
Linux. Ni la inspección ni un recibo verde crean una aprobación humana.

```bash
python -m src.publish.afac_history_update --inspect <request-privado.json> --inspection-out tmp/source-updates/correction-review
# Revisar scope y cuatro JSON; retener decisión auténtica y auditoría exactas.
python -m src.publish.afac_history_update --prepare <request-autorizado.json>
# Revisar y confirmar config/publish/afac-history-release.json.
python -m src.publish.afac_history_update --request <request-autorizado.json> --out site/
python scripts/check_pages_publication.py site/
```

La inspección opcional sólo retiene material privado en un directorio nuevo bajo
`tmp/`; nunca sustituye el replay de publicación. El gate repite las fuentes y
aprobaciones bajo el lock, comprueba HEAD, autoridad, huellas y remoto antes del
intercambio atómico, y restaura el sitio anterior si falla el intercambio. El
witness nuevo permite hasta tres GET para errores transitorios concretos, con
esperas acotadas; un HTTP200 con tamaño/SHA distintos, 403 o 404 falla sin retry.
El witness V1 original no cambia. El selector sólo trata la prueba B como una
dependencia cuando verifica ese enlace exacto; los empates V1 siguen fallando.

El verificador público conserva la huella de productor fijada en el ancla. Si el
runtime actual cambió después de generar el sitio, vuelve a calcular esa huella
en el `code_commit` del manifiesto publicado. Solo acepta ese replay si el
commit es antecesor de `HEAD`, contiene los mismos bytes del ancla comprometida
y reproduce la huella exacta. Después ejecuta las verificaciones completas de
la composición, el padre, los payloads y el manifiesto; no actualiza pins ni
permite cambiar datos o autoridad.

Esta implementación está preparada para revisión. Antes de activarla faltan el
cierre físico de Gold AFAC derivado, el replay privado completo en Linux, la
inspección del candidato final y su autoridad de datos. PR, CI y comprobación del
sitio realmente servido conservan sus controles normales.

## Promedios de precios y puntos

`--fare-quotes-only --fare-input <Gold privado>` añade exclusivamente
`data/v1/fare-averages.json` y `fare-quotes-publication.json`, además de la interfaz.
Requiere todos los expedientes aprobados existentes y vuelve a ejecutar su cadena
de fuentes y revocaciones antes y después del build. Conserva los datos heredados
y las identidades de aprobación byte por byte. El consentimiento del dueño para
las tarifas se mantiene separado de las aprobaciones financieras.

`src.publish.fare_scope` verifica la publicación base con su selector y verificador
fuertes del `code_commit` original, ejecutados en un worktree. Exige el manifiesto
bruto y todos los hashes/bytes exactos de Git, rechaza archivos extra y symlinks,
comprueba la adición exacta, el contrato y las medias/conteos. No acepta una
modificación de datos heredados aunque tenga un manifiesto nuevo coherente.
La fuente detallada sigue privada; la fórmula y el grano están en
[`src/fare_quotes/README.md`](../fare_quotes/README.md).

El recibo de tarifas participa en la precedencia por el commit de su publicación
base; un perfil posterior con base más reciente conserva la responsabilidad de
verificar la composición. La presencia del recibo no fija el verificador para
siempre. La reconstrucción de presentación puede conservar el producto de tarifas:
mantiene sus datos y recibos y reproduce las autoridades dos veces. El compuesto
de tarifas hereda la autoridad del perfil base real, que puede ser SOURCE aunque
retenga pruebas AFAC anteriores. No etiqueta el commit del frontend como productor
AFAC ni necesita ese marcador: su recibo ya vincula la publicación fuerte original.
El camino de presentación sobre AFAC directo conserva su marcador y sus guardias.
