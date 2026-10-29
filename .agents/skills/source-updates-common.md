# Contrato común de actualización por fuente

Estas skills preparan candidatos. Una captura no aprueba datos, tesis, noticias
ni publicación. Leer primero `AGENTS.md`, el catálogo aprobado en
`docs/catalogo-fuentes-calendario.md`, `config/source_catalog.yaml` y la
política ejecutable `src/source_updates/catalog.py`. La guía para Salva está al
principio del catálogo; estas instrucciones son referencia interna.

Decisión del dueño del 29/oct: Aerocivil puede usarse con los supuestos
operacionales vigentes, conservando confirmación oficial pendiente. La política
dedicada se adjunta solo tras replay real, conteos/filas/hashes/periodo/linaje y
huellas semánticas revisadas. No rellena datos faltantes, elimina el producto
requerido ni sustituye disponibilidad desconocida. La respuesta oficial queda
como seguimiento; si contradice los supuestos se versionan los cálculos afectados.
Los workers siguen sin habilitar calendarios, datos o publicaciones. La autorización
condicional del calendario pertenece únicamente a su coordinador, tras las
comprobaciones reales de Viva, datos requeridos y despacho nativo.

Los alias de una institución abarcan varias capas. Para capturar, usar
`bronze_source_systems` de `recipe`: empresas SEC requieren `sec`; tráfico
GAP/ASUR admite sus alias aeroportuarios, con `sec_edgar` en la receta; el
adaptador de aerolíneas AFAC requiere `afac`. No intercambiar una etiqueta
Silver por un alias Bronze ni renombrar originales para eludir el control.
Los pasos deben incluir sus predecesores en orden. Un archivo preexistente no
sustituye una validación; una dependencia no disponible bloquea la construcción.

## Procedimiento

1. Confirmar rama, alcance, periodo cerrado y corte con zona explícita. Trabajar
   en `tmp/source-updates/<lote>/`; no restaurar sobre trabajo ajeno.
2. Ejecutar `python -m src.source_updates plan --round monthly --as-of <ISO-con-zona>
   --family <familia>` (para trimestral añadir `--quarter YYYYQn`). El plan
   muestra cobertura y brechas; no descarga ni comprueba frescura Gold.
3. Verificar la ruta vigente desde HOME/menús de la fuente oficial y su
   documentación, además del catálogo: un enlace fallido puede estar obsoleto.
   Hacer esa búsqueda y las alternativas permitidas de forma autónoma, sin
   esperar a que el usuario dirija clics o consiga archivos resolubles.
   Seleccionar catálogos y documentos con URLs reales del dominio permitido.
   Consultar primero `recipe --product <producto>`: resuelve la entrada canónica,
   formato, procedimiento y limitaciones de `config/source_update_acquisition.json`.
   Para `fuel`, `banxico`, `h10` y `equities`, `recipe --output round --period <periodo>
   --as-of <corte>` emite selección, parámetros y controles listos para probar.
   Para índices HTML admitidos, `recipe --output selection` evita redactar la
   selección a mano; no descarga los documentos descubiertos ni certifica su mes.
   Para descubrir enlaces, usar `purpose=catalog` y `extension=html`;
   la captura guarda los enlaces, pero no sigue ni inventa publicaciones.
   Para nuevas publicaciones seleccionar después `purpose=data`.
   Cada elemento declara producto, alias exacto, entidad, periodo, URL,
   extensión y modo. Ver `config/source_update_round.example.json`.
   Usar `relative_dir` cuando el parser exige una estructura concreta (por
   ejemplo `afac/2026/06`); conservar los nombres lógicos esperados por el parser.
4. Ejecutar `collect --selection <seleccion.json> --workspace <ruta> --dry-run`.
   Revisar llamadas máximas y destinos. Si el alcance de la sesión autoriza
   capturar esa fuente pública, usar `--execute`. Las pruebas públicas reales conservan sus recibos; no generalizar su alcance a fuentes no probadas.
5. Registrar en el recibo periodo solicitado, publicación conocida o nula,
   captura UTC, URL, SHA-256, original y estado. Un catálogo no es un reporte.
   Revalidar URLs seleccionadas aunque existan: el contenido igual se deduplica;
   el cambiado conserva original y revisión. El escritor único usa bloqueo
   exclusivo de sistema de archivos. No ejecutar varios escritores del mismo lote.
6. Construir solo pasos explícitos con `build --workspace <ruta>
   --steps <lista> --dry-run`, después `--execute` si procede. La ejecución
   es otro proceso con red bloqueada y rutas del candidato. Reutiliza parsers y
   contratos existentes. No invocar `just ingest`, `just rebuild` ni
   analítica/modelos completos como sustituto de una actualización acotada.
7. Ejecutar `check --workspace <ruta> --specification <controles.json>`.
   Bronze: verificar hashes. Silver: contrato, grano, dominio, linaje, fuente,
   entidad y periodo realmente presente. Gold: contrato y linaje directo o puente completo validado con `transform.gold_lineage`.
   En aeropuertos, declarar `operator_group=GAP/ASUR/OMA`; para
   `fact_airport_group_traffic`, usar `airport_group_key` con ese valor.
   Un hash agregado exige reconstruir catálogo y puente contra Bronze mediante el gate existente. Las declaraciones sin artefacto no acreditan linaje documental.
   Declarar `value_columns`; conservar N/D, no llenar con cero. Comparar
   contra una copia previa explícita con `baseline_file`, `revision_keys`
   naturales y valores: altas, bajas, cambios y sin cambios. Los cambios de
   archivo no prueban revisiones de cifras.
8. Registrar por producto último disponible, validado y publicado por Tracker
   por separado. Este coordinador nunca infiere el publicado desde Gold.
   Calcular rezago de publicación solo si hay fecha de publicación explícita;
   de lo contrario conservar nulo. La antigüedad del dato no es el rezago
   de publicación. Un periodo presente no garantiza que esté completo:
   comprobar meses esperados, universos, días cubiertos y reconciliaciones.
9. Entregar resultados y bloqueos para revisión. `round --recipe <receta.json>
   --workspace <ruta> --dry-run` reúne captura, construcción y controles;
   con `--execute` se detiene al fallar captura o construcción. Para captura nueva usar explícitamente `--check-at-completion`; conserva el corte pedido y registra el corte efectivo. Sin esa opción el corte histórico rechaza capturas posteriores. Los controles
   solo certifican su alcance explícito, no una ronda completa ni su publicación.

## Fallos y permisos

- 403, TLS, desafío, timeout o archivo inválido = fallo de acceso/contenido.
  Conservar último dato aceptado. No declarar ausencia de reporte ni cero.
- Si falla la adquisición programática, usar el navegador soportado para abrir
  la página oficial y descargar mediante su interfaz normal. Si el entorno de
  código no dispone de navegador, entregar el enlace, documento/periodo y recibo
  fallido a dot para su navegador cloud o local autorizado y conectado; la
  integración sigue en este entorno. Comprobar capacidades reales, no asumir
  ausencia de navegador. Escalar solo un bloqueo concreto o decisión necesaria,
  sin trasladar al usuario verificaciones que el agente puede realizar.
  `collect` conserva ese handoff pendiente en `manual_recovery`, sin fingir que
  ya hizo clics o descargó. Antes de declarar vías agotadas, intentar esa vía o
  registrar el bloqueo concreto de herramienta/acceso. No evadir denegaciones,
  autenticación, CAPTCHA ni avisos de seguridad. Conservar el fallo anterior.
- Verificar bytes legibles, tipo, identidad, periodo, cobertura, unidades y SHA
  del archivo descargado. Conservar URL, método y fecha reales; transferir por
  Library soportado y verificar de nuevo en el consumidor antes de importar.
  Una ruta del navegador no implica acceso desde el ejecutor. La importación
  manual no es una nueva respuesta HTTP; su fecha tampoco es la observación
  del editor. Una reconstrucción requiere su modo autorizado y nunca se llama
  original. Un error también en el navegador sigue siendo un bloqueo real.
- Fecha futura oficial: propuesta a +2 hábiles. Fallo técnico: siguiente hábil.
  Fecha desconocida: un intento dentro de 7 días o siguiente ronda mensual.
  `retry` produce propuestas, no tareas; a las dos reprogramaciones bloquea.
- No nuevas llamadas AeroDataBox, pagos, suscripciones, secretos, credenciales,
  cambios de seguridad ni borrado del histórico retenido.
- SEC se importa manualmente aquí; no leer ni configurar identidad/secretos.
  Aena solo por exportaciones manuales autorizadas, sin login automatizado.
- No aprobar, revocar ni activar nuevas versiones de tesis Viva, Volaris o Industria. Se requiere la
  aprobación exacta del dueño por entidad, periodo y versión y el gate vigente.
  No simularla a partir del contenido o de pruebas verdes. La disponibilidad
  de tres reportes compatibles permite preparar Industria, no aprobarla.
  Conservar las tesis 2T26 de las tres entidades ya aprobadas y publicadas; esta
  restricción no exige desactivarlas ni repetir su aprobación.
- No activar noticias candidatas/evidencia, cron, Pages, Railway o auto-merge.
  Separar captura, candidato, aprobación y publicación en cada entrega.

## Reproducción de una ronda con varios adaptadores

`python -m src.source_updates.readiness --recipe <receta.json> --workspace
tmp/source-updates/<recibo-nuevo> --dry-run` valida todas las tareas antes de
leer sus insumos. La receta declara `required_items` y por tarea `id`, `product`,
`period`, `adapter`, `workspace`, `receipt_id`, `required` y `candidate_as_of`.
`as_of` es el corte de revisión de la ronda; `candidate_as_of` conserva el corte
inmutable de cada candidato histórico y no puede ser posterior al de la ronda.
No se pueden omitir tareas declaradas requeridas, reutilizar workspace ni
intercambiar producto/adaptador.

`--execute` comprueba offline candidatos existentes, verifica que sus archivos
no cambien y escribe un recibo de ronda inmutable; **no captura fuentes**.
`--check` vuelve a comprobar el mismo recibo y sus flags. Soporta `retained`,
`am_traffic_ir`, `h10`, `aerocivil`, `gdelt`, `government`, `bts`,
`airport_group`, `series`, `viva_financial` `rss_retained` y `carrier_source`; el registro de `retained` incluye
los productos admitidos por sus lectores. Los demás adaptadores se rechazan y
mantienen sus comandos específicos. Curación usa su auditor separado.

Usar en cada replay el `effective_as_of` exacto del recibo aceptado, incluida
su representación de zona. H.10, tráfico Aeroméxico, Aerocivil y los productos
retenidos rechazan un corte distinto o ausente antes de recalcular. Un nuevo
corte necesita una certificación nueva; no sobrescribir el recibo histórico.

Una tarea requerida fallida bloquea la ronda y conserva éxitos previos; las
opcionales pendientes se listan. `ready_for_review` solo acredita las tareas
declaradas y sus reproducciones, no disponibilidad actual, catálogo completo ni
preparación para activar automáticamente. Los productos no ejercitados y las
condiciones de fuente quedan explícitos; todas las activaciones siguen falsas.


## Originales retenidos y lote offline

`python -m src.source_updates.retained` dispone de adaptadores dedicados para
AFAC aeropuertos/países/marginales, ANAC, CAA, Aena, OMA, slots AICM, referencias
IASA/diccionario y cuatro documentos de rutas. La tabla de alcances y los roles
están en el [catálogo canónico](../../docs/catalogo-fuentes-calendario.md#certificación-de-originales-retenidos).
Son candidatos con contratos locales y linaje comprobado; no añaden tablas al
warehouse ni amplían los pasos del `build` genérico.

1. Seleccionar rutas exactas en `_manifest.jsonl` de Bronze. `retain` exige
   producto, roles y alias compatibles, URL pública admitida, bytes con el SHA
   original y sidecar coincidente. No relabelar `afac_research` ni otros alias.
2. Mostrar `retain --dry-run`; después `--execute` si el trabajo autoriza el
   candidato. Copia los originales sin cambiar `downloaded_at`; `retained_at`
   es otra fecha. No hace una captura, no revalida URLs ni comprueba la última
   publicación disponible. Nunca usar AeroDataBox ni fuentes privadas/inactivas.
3. `certify --retention <id> --period <periodo> --as-of <corte>` muestra el plan.
   `--execute` construye Silver/Gold aislados y un recibo inmutable. `--check`
   reconstruye en memoria y contrasta filas, hashes y linaje, sin red/escrituras.
   Los originales, notas de la fuente y roles de soporte se vuelven a verificar.
4. Para revisiones, seleccionar `--baseline baselines/<archivo.parquet>` en el
   comando individual. La comparación usa claves naturales y campos de valor;
   también las marcas y notas de estimación AFAC y todos los campos nativos del diccionario. El
   hash y selección del baseline quedan fijados en el recibo y en cada replay.
   Sin baseline se declara que no se compararon revisiones, aunque cambie SHA.
5. `python -m src.source_updates.retained_round --recipe <receta.json>
   --workspace tmp/source-updates/<lote-nuevo> --dry-run` orquesta el lote.
   `--execute` encadena retención → Bronze → Silver → Gold/linaje → replay por
   producto. Se detiene en el primer fallo y conserva salidas previas y recibo
   con etapa/objetivo/error. No reusa candidatos ni instala tareas. El lote no
   acepta baseline implícito: las comparaciones se preparan individualmente.

La revisión de periodo en snapshots de referencia o programación no convierte
su contenido en tráfico del mes/trimestre. FAA conserva la fecha de su propio
documento; slots conserva toda la temporada; países solo cajas acumuladas
exactas y documentos de rutas solo pasajes fechados. Un formato/edición fuera
del alcance revisado queda bloqueado para adaptar y probar antes de ejecutar.

Para AICM/AIFA, el adaptador `government` usa retención por alias, un
certificador integral y el recibo `government-<producto>-<mes>.json`; no se
admite sustituirlo por `retained` o comprobaciones genéricas de Gold. Ver la
[skill de aeropuertos](airline-update-airports/SKILL.md#certificación-integral-aicmaifa).

Para GAP/ASUR, `airport_group` exige el HTML SEC del CIK exacto y emite
`airport-group-<producto>-<mes>.json`. La retención no consulta SEC ni configura
su identidad de acceso. El recibo conserva redondeo/preliminar, país y linaje
calculado; `retained` genérico no puede certificar este producto. Ver la
[skill de aeropuertos](airline-update-airports/SKILL.md#certificación-integral-gap-asur).

Excepción autorizada solo para ASUR septiembre 2026: admite las cuatro
representaciones reconstruidas verificadas, con roles `reconstruction_json`,
`reconstruction_html`, `reconstruction_csv` y `reconstruction_manifest`.
Usar su importador offline específico y alias `asur_visible_reconstruction`,
no `collect` ni alias de original SEC. Hash e identidad corresponden al
derivado, con original/captura HTTP desconocidos. Se mantiene el mismo
producto requerido y Gold México; no cambia el alcance de otras fuentes.
Ver [procedimiento y límites](airline-update-airports/SKILL.md#asur-septiembre-representación-reconstruida-autorizada).

Para RSS usar su certificador retenido dedicado, `python -m
src.source_updates.rss_candidate`, y el adaptador `rss_retained` en readiness.
Su lote propio admite selección explícita de varios XML de la misma revisión
mensual; no se añade al registro `retained` ni al build genérico. Ver la
[skill de noticias](airline-update-news/SKILL.md#certificación-integral-de-rss-retenido).

Para `volaris_sec` y `afac_carriers` usar el CLI dedicado
`carrier_source_candidate` y el adaptador readiness `carrier_source`;
`retained certify` y comprobar Gold heredado no satisfacen estos productos.
`retained_round` encadena sus roles explícitos, parseo, contrato, Gold propio,
linaje y replay; conserva la etapa y motivo si falla antes de escribir salidas.
Cada producto/ventana exige candidato separado, nuevos originales no alteran
candidatos aceptados. `--baseline` es una ruta explícita a
`baselines/<snapshot>/data/silver/<producto>_source_native.parquet`: exige el
dossier original, manifiesto/sidecars y recibo de retención del snapshot.
Se reconstruye y coteja todo el nativo antes de comparar historia, columnas
anuales/acumuladas y flags/notas. Reordenamientos quedan como altas/bajas,
sin suponer equivalencia. No se acredita revisión oficial por comparar hashes.
No hay baseline implícito; publicación inicial, disponibilidad y rezago no
acreditados siguen nulos. Ver límites de cada fuente en sus skills/guía.

La receta de `readiness` y la global admiten el campo opcional `availability`
por tarea con campos exactos `workspace`, `run_id`, `catalog_item` y
`artifact_item` para AIFA, AICM, OMA, Viva, BTS y tráfico IR de Aeroméxico. Identifican una colección física
separada del candidato. Se relee el índice oficial del producto, se determina
el último documento y se comprueban URL, manifiesto, HTTP, hashes y su aporte
al nativo completamente certificado. OMA conserva el bloqueo del PDF actual;
un contrato implementado no acredita una descarga fallida.

AFAC por aerolínea tiene su contrato propio: sustituye `artifact_item` por
`artifact_items={"pdf": "<id-boletin>", "database": "<id-base>"}`. Exige el
boletín y la base anunciados, capturados y realmente usados por el dossier
reproducido. Mantiene `complete_month_certified=false` y la advertencia de
cobertura internacional; lo reportado íntegramente no prueba un universo
completo. No permite ese binding multioriginal en otras familias.
BTS exige su historial FJE y los ZIP México de cada año añadido o revisado,
con el formulario y POST canónicos. Comprueba el máximo mes del archivo;
conserva `complete_month_certified=false` y la cobertura por operador sin
acreditar. La comparación de historia necesita un baseline explícito; capturar
un año revisado no demuestra cambios de filas ni vigencia de otro mes.
RSS usa `workspace`, `run_id` y `feed_items={"google_es": "<id>",
"google_en": "<id>"}`. Son las dos consultas canónicas actuales, con URLs y
locales exactos; no hay índice de reportes. Se comprueba su aporte al dossier
completo de metadatos y se mantienen los días no observados, incompletitud
mensual, cobertura del medio y elegibilidad del agente sin acreditar. No
convertir este vínculo en última fecha de publicación ni sustitución de GDELT.
Las series usan `workspace`, `run_id` y `series_items` con todos los roles
canónicos del producto: tres Banxico, un libro EIA o cinco tickers. El vínculo
comprueba las respuestas actuales y su aporte nativo; no aporta un calendario
esperado de observaciones por sí solo. Banxico admite el cuarto original
`fix_methodology` en su retención: el resultado se calcula y reproduce desde
los cuatro cuerpos y el calendario bancario, no desde un flag del usuario.
Tres roles antiguos, EIA y mercado mantienen calendario no certificado.
Mercado puede añadir al binding `equity_calendar_root` con las cuatro referencias
físicas NYSE, Nasdaq, OTC y días NYSE. La captura OTC MHTML nativa se importa
como `browser_mhtml`, con `http_status=null` y fecha de su encabezado; no como
HTML HTTP ni reconstrucción. Se verifica únicamente su documento raíz oficial,
sin ejecutar scripts/frames. El suplemento reconstruye las cinco series desde
sus originales y compara sesiones, ancla anual e historia para treinta retornos.
Solo esa prueba completa puede despejar el control de calendario de septiembre
y trimestre; no cambia el recibo antiguo ni sus cifras. Los parciales son
sesiones y OTC conserva sus14:00, sin tomar el calendario de NYSE prestado.
La prueba se limita a2026 y no acredita festivos2027.

AFAC aeropuertos admite el handoff `afac_airports_browser_download_v1`: paquete
Library con el XLSX original descargado por UI, manifiesto de adquisición y
texto accesible del índice. El texto es evidencia de navegación, nunca HTML
original. Comprueba una sola edición aeroportuaria y sus dos enlaces PDF, URL,
fecha real, hash, periodo y reproducción completa del libro. Mantiene separado
el momento de importación y la observación del navegador; HTTP desconocido.
La alternativa manual no amplía la exención de las tres ediciones retenidas.
Banxico septiembre pasó; Q3 sigue no certificado frente al universo diario,
sin inferir error del proveedor. Último periodo y primera publicación siguen
desconocidos y la ronda global permanece bloqueada. La
identidad SEC de mercado sigue siendo original retenido, sin nueva captura.
La disponibilidad HTTP se limita a la fecha local de captura y corte real de la
ronda; no acredita primera publicación, rezago ni activación. El vínculo
inválido bloquea; no hay fallback ni booleano manual. Sin vínculo, o para una
familia aún sin contrato, la disponibilidad permanece sin verificar.

La excepción aprobada el 28/oct a las 23:15 UTC acepta ediciones cerradas ya
validadas de GAP septiembre, ASUR septiembre y Volaris financiero 3T26 con sus
contratos específicos. Conserva las fechas originales y reconstrucciones como
tales. `validated_closed_edition` acredita el periodo solicitado, separado de
`latest_source_availability_verified`: no exige recaptura del mismo día ni
afirma última edición. No tiene un vencimiento diario artificial; un periodo
distinto o una edición nueva conocida exige validación nueva. Las consultas de
novedades se registran aparte, con recibo físico, fecha y fallo/incertidumbre;
sin consulta se declara `not_checked`. `known_new_edition` bloquea la reutilización.
Nunca se extiende a noticias, precios ni fuentes ausentes. Siguen pasando hash,
Bronze/Silver/Gold, unidades, conciliación y replay; no autoriza publicación.

GAP tiene una forma histórica específica: `source_scope`, `historical`,
`snapshot_day`, `workspace`, `submissions` y `filings`, con índice y documentos
por accession. Solo admite julio 2026 con el snapshot y corte mexicano
`2026-08-20T18:20:00-06:00`. Verifica los originales retenidos y su orden sin crear una colección
ni cambiar las capturas. El corte global real también debe coincidir: un
`candidate_as_of` antiguo no permite presentarlo como disponibilidad actual.
El protocolo y sus límites están en la skill de aeropuertos y la guía canónica.

Las conciliaciones derivadas comparables admiten la política inicial autorizada
el 27/oct: hasta 5 % relativo a una referencia oficial explícita y estable,
con mismo periodo, unidad, definición y cobertura. El primer uso acotado es
CASM Volaris; conserva cifra oficial, cálculo, fuentes y advertencia visible.
No aplicar a ausencias, citas oficiales incompatibles, unidades/periodos,
integridad o autoridad. Cero/casi cero no admite un porcentaje automático.
La revisión con advertencias no se convierte en aprobación de publicación.

La cobertura exhaustiva conserva su diagnóstico. Para promedios/cierres
observados de Banxico/EIA ya verificados no es un denominador necesario y queda
como advertencia global; para retornos/volatilidad bursátiles sigue bloqueando.
Todos los meses, entradas, fuentes, cifras y linaje requeridos siguen pasando
sus controles. Un aviso de reporte confirmado tampoco espera esa ronda global:
separar detección, comprobación primaria, aviso, incorporación y autorización.

## Noticias y el calendario unico

La autorización del 29/oct reemplaza GDELT obligatorio por una tarea editorial
mensual en el mismo calendario. Web nativa y lectura del editor son la vía
principal; RSS es complemento y GDELT opcional. Aplicar la skill de Noticias y
el contrato editorial, sin renombrar esos metadatos como originales HTTP.
Cada tarea conserva su resultado y las independientes avanzan; la ronda con
componentes obligatorios pendientes no se declara completa. Se conservan
los gates de publicación y los fallos históricos. No hay un segundo calendario.
