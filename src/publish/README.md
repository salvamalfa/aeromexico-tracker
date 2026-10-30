# `src/publish`

The publication gate for `site/`: the *signed object* the dashboard ships
as — a directory built from `web/` plus the exported v1 payloads. See
`web/README.md`.

## Responsabilidad

- `gate.py`: given one or more `analysis_runs/drafts/<period>/<version>.json`
  records, verifies each through
  (`src.analysis_agent.lifecycle.consumer_payload`/`verified_inputs`, under
  the ledger's writer lock) and refuses (raises `PublicationRefused`, CLI
  exit 1) if any record is not exactly, currently approved — nothing is
  written. On success it runs `src.web_export` into a temp directory
  (flights and executive for every period, analysis only for the given,
  now-verified records), copies that into `web/public/data/v1` (local,
  gitignored dev scratch — see `.gitignore`), and runs `npm ci && npm run
  build` in `web/`, all with the ledger lock released (an `npm run build`
  is slow; a human's approval/revocation should not block on it). Records
  are then **re-verified a second time**, under a fresh ledger lock held
  through the swap itself, immediately before `site/` is replaced — closing
  the window where a revocation could otherwise land between the first
  check and the swap. Only after that second check passes does it assemble
  `site/` from the built `web/dist/` (Vite already copies `public/` into
  `dist/`, so this *is* "dist + data").
  For a strictly interface-only change, `--ui-only` reuses the existing
  public `data/v1/` payload. It first requires the whole tracked `site/` to
  be byte-for-byte unchanged from one pinned `origin/master` commit, verifies the site manifest
  and replays each exact approved analysis-manifest entry with its pinned
  cohort implementation, then checks that the
  frontend build preserved every data file hash and size. It retains the
  trusted manifest's contract hashes too, so a UI release does not change the
  conversation's data version merely because this codebase added a dormant,
  optional contract. It repeats the trusted-site and approval checks
  immediately before the atomic swap, and refuses if the trusted ref moved
  during the build. Before the swap it also verifies the completed candidate
  and compares every data hash and size again, closing changes to dist during
  the second approval check. This mode cannot bless edited data by
  rebuilding its manifest, and it never invokes warehouse exporters.
- `--business-metrics-only` uses the same immutable published-site baseline
  and exact current analysis approval, then adds only the separately pinned
  business-metrics payload and receipt. It requires the baseline data files to
  remain byte-identical, validates the completed candidate site before swap,
  and rechecks both the trusted baseline and Analysis Agent approval under the
  ledger lock immediately before the atomic replacement.
- `--preserve-published-data` prepara el mapa solo de vuelos con el histórico
  completo. Toma el `site/` firmado exacto de `origin/master`, revalida las
  aprobaciones por su cohorte de implementación y los expedientes
  actuales antes/después del build, y conserva **todos** los archivos de
  `data/v1/` byte por byte. Protege los renderers de análisis, fuentes y
  contratos; no reconstruye modelos, crea aprobaciones ni activa datos nuevos.
  El gate normal conserva sus comprobaciones estrictas. El candidato se
  verifica antes del reemplazo. Integrar y publicar requiere la autorización
  aplicable al cambio y el flujo normal del repositorio.
- `config/publish/preserved-analysis.json` conserva la referencia a la
  implementación original de las tesis congeladas. El gate comprueba el hash
  del manifiesto histórico, que sus commits pertenecen al historial publicado
  confiable y que todas las identidades y bytes de tesis siguen idénticos.
  Después revalida los cuatro registros completos con esa implementación,
  incluyendo revocaciones y expedientes actuales, antes y después del build.
  `code_commit` sigue identificando el código que genera la interfaz actual.
  La referencia no autoriza versiones ni contenido nuevos, no cambia huellas
  aprobadas y no evita ninguna validación de datos o de privacidad.
- `config/publish/approval-cohorts.json` fija las ediciones posteriores por
  cohorte: entrada completa de aprobación, commit del verificador y SHA/tamaño
  del payload público. Conserva el ancla original sin modificarla. El gate lee
  los pins del commit confiable, exige una partición completa sin duplicados ni
  entradas huérfanas y reproduce autorización, fuentes y payload con cada
  implementación. La rama y el verificador nuevo deben descender de la publicación
  confiable; los verificadores históricos deben estar en su historial ya publicado.
  La configuración de trabajo debe coincidir con la comprometida;
  todo se vuelve a comprobar bajo lock. Para el nuevo trimestre solo admite un
  pin adicional comprometido y ligado al registro aprobado actual. Un pin no
  concede aprobación. Los modos que preservan datos, UI-only y el modo de vuelos reutilizan
  esta comprobación; incorporar 3T26 no bloquea la siguiente publicación del sitio.
- `--flights-only` proyecta las celdas aceptadas de 2T26 sobre el sitio público
  auditado, sin reconstruir el warehouse ni los otros exportadores. Exige la
  edición exacta de vuelos, el valor anterior de cada sustitución y la
  conciliación por operador/mes/ámbito. Revalida las aprobaciones por cohorte con su
  implementación publicada y conserva el resto de payloads e identidades antes
  y después del build. La autorización específica del 19 de octubre cubre esta
  proyección y su tarjeta ponderada; no aprueba tesis nuevas, M11 ni calendarios.
- `manifest.py`: builds and (de)serializes `publication_manifest.json` —
  the code commit (`git rev-parse HEAD`), each `contracts/web/*` file's own
  SHA-256 (its "version"), every other file under `site/` with its
  SHA-256/size (sorted, manifest itself excluded), and the current
  analysis-manifest entries (`period_id`, `version`, `content_hash`,
  `evidence_fingerprint`, `approval_event`, `audit_hash` — the same fields
  the published page's `#analysis-manifest` carries).
- `verify.py` (`python -m src.publish.verify site/`): CI-safe, no private
  data. Checks the manifest against `contracts/web/
  publication_manifest.schema.json`, every listed file's hash/size, no
  unlisted file present, every `data/v1/**/*.json` file against its
  `contracts/web/*.schema.json` sub-schema and `contracts/web/privacy.yaml`,
  and that every `analysis_manifest` entry is well-formed. This is exactly
  what `.github/workflows/pages.yml` runs before deploying.
- `site/` itself is *not* gitignored: an approved run's output is committed
  like any other file, then deployed as-is by CI (`.github/workflows/
  pages.yml` never rebuilds it, never touches `analysis_runs/`).
- The `intent`/`published` receipt goes to
  `analysis_runs/publications/` (local, gitignored — see `.gitignore`'s
  `analysis_runs/` rule) and hashes the *manifest*, not the raw `site/`
  bytes, since the manifest already lists every file's own hash.

Las pruebas de paridad usan el manifiesto firmado que existe en `site/` y la
configuración comprometida con esa misma publicación. Leen esa configuración en
un worktree temporal aislado; el ledger, los originales y los verificadores se
reproducen sin sustituir sus controles. Un pin pendiente en HEAD no se trata como
parte del sitio anterior. El sitio de cuatro tesis exige las cuatro identidades
históricas; la quinta solo se exige cuando el manifiesto incorpora Aeroméxico
3T26. Los artefactos del gate deben estar comprometidos antes de esa paridad.

Never writes to the approval ledger, never approves/revokes/records
anything. `web/` is the only implementation of each view, this gate its
only publication path. `AGENTS.md` permanently authorizes agents to run this
gate for a requested routine site change using an already approved record, to
commit `site/` in a PR, and to follow the Pages deploy through live
verification. A new approval, changed data meaning, or another higher-risk
action still needs the owner's specific authorization. See `REPO_MAP.md`.

## Entradas / salidas

- **Entradas:** one or more `analysis_runs/drafts/<period>/<version>.json`
  record paths (local, non-versioned); the local warehouse (via
  `src/dashboard/`, same as `src/web_export`); `web/` (Node/npm); `contracts/
  web/`.
- **Salidas:** `site/` (versioned); an intent/published receipt under
  `analysis_runs/publications/` (local, non-versioned).

Los nuevos registros de entidad viven en
`analysis_runs/drafts/<entity_key>/<period>/<version>.json`. Para publicar el
mismo trimestre de Aeroméxico, Volaris, Viva e Industria, pasar los cuatro
registros mediante cuatro opciones `--record`. Cada uno debe conservar su
aprobación vigente y su identidad de entidad, trimestre y versión. El gate
rechaza dos versiones de una misma entidad y trimestre.

El registro histórico de Aeroméxico conserva
`data/v1/analysis/<period>.json` y sus bytes publicados. Los nuevos registros
se exportan a `data/v1/analysis/<entity_key>/<period>.json`, con `entity_key`
en el payload y el manifest. Una entrada histórica sin ese campo corresponde
a Aeroméxico. El verificador comprueba que ruta, encabezado y manifest
coincidan; la presencia de un archivo por sí sola no acredita aprobación.

## Punto de entrada

### Handoff independiente de Viva y Volaris 3T26

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

Pages selecciona el verificador de issuer cuando existe su recibo, sin fallback.
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
captura, SHA, metadatos y supuestos. Si cambió el productor, requiere una nueva
certificación offline desde esos originales, sin HTTP ni renovar sus fechas.
Movimientos provisionales permanecen separados de salidas; no se dividen entre
dos ni certifican vuelos regulares o cobertura trimestral completa.

La solicitud privada tiene `schema_version: aerocivil_movements_request_v1`,
`source_profile: {path, sha256}`, los siete `record_paths` exactos del manifiesto
publicado y `authorization: {path, sha256}`. Para inspeccionar antes de retener la
autorización, usar `authorization: null`. El perfil contiene sus originales y
metadatos fijados por SHA, referencia de aeropuertos y `july_item` certificado.
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
Pages y outbox seleccionan el verificador específico sin fallback. El recibo
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
Pages selecciona el verificador según el sitio que despliega: si contiene
`editorial-publication.json`, exige el verificador editorial y su ancla exacta,
sin fallback ante errores. Una publicación posterior de interfaz o datos sin
ese recibo usa el verificador general, aunque el ancla histórica siga en Git.
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

The negative fixtures under `tests/fixtures/site/` (altered byte, extra
file, missing file, disallowed carrier, undeclared field, malformed
approval entry) run in CI with no private data. A full local run of
`gate.py` itself (`local_data`, needs the warehouse and an approved
`analysis_runs/` record) is exercised by `tests/test_publish_gate.py` and,
for the built site's visible parity against the published page, by
`tests/test_site_parity.py` (`browser` + `local_data`).

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

Pages selecciona primero el verificador financiero si existe
`financial-publication.json`, sin fallback ante errores; exige ancla, output y
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
