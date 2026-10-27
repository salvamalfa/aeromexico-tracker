---
name: airline-update-news
description: "Actualizar candidatos de la familia noticias mensuales de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Noticias mensuales

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `news`. Alcance: Google News RSS y GDELT; news_http_error conserva fallos y permanece inactivo.

Una revisión mensual, también cuando se combina con una ronda trimestral.
Capturar solo metadatos autorizados (título, URL, emisor, fecha y consulta);
no artículos completos. El adaptador candidato `src/source_updates/news.py`
deduplica URL normalizada y fecha local, conserva todas las procedencias y
separa ediciones de días distintos. No resuelve enlaces opacos de Google News.
Los feeds no garantizan recuperar el mes entero: mostrar cobertura real.
Distinguir fecha del evento, publicación y captura; noticias no sustituyen
fuentes financieras oficiales. `news_http_error` nunca cuenta como noticia ni
ausencia de noticias. PR142 ya está integrado en `194ff92c`; conservar sus
controles en esta rama reconciliada. No cambiar la rama de su responsable ni
activar candidatos. El contrato Silver conserva un
representante por noticia y `provenance_json` conserva los metadatos de cada
fuente. `check` proyecta cada contribución, exige la misma URL canónica y fecha
local, y verifica su propio archivo/hash Bronze. Los valores y revisiones de
GDELT no se toman del representante RSS ni viceversa. Esto no certifica que el
mes esté completo.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family news
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.news

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

## Adquisición por producto

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product rss
```

Consultar cada producto de esta familia:

- `rss` — condicionado a insumos/formato. Entrada canónica: `mapping:src.ingest.news.rss_gdelt:RSS_FEEDS:google_es`. Formato: RSS XML de metadatos.
- `gdelt` — condicionado a insumos/formato. Entrada canónica: `constant:src.ingest.news.rss_gdelt:GDELT_API_URL`. Formato: GET Doc API → JSON articles.
- `news_errors` — inactivo. Entrada canónica: `catalogue:news_http_error`. Formato: evidencia de fallo.

### Procedimiento verificable

1. Ejecutar `recipe --product <producto>` y leer su procedimiento, URL resuelta, formato y bloqueo.
2. Para un índice HTML admitido, emitir la selección con `recipe --product <producto> --output selection > tmp/seleccion.json`. Revisarla con `collect --selection tmp/seleccion.json --workspace tmp/source-updates/<lote> --dry-run`. Capturar solo dentro del alcance autorizado.
3. Leer los enlaces y el contexto del catálogo preservado. Elegir el documento real y comprobar su periodo dentro del contenido. No transformar una plantilla histórica en una URL futura. Para importación manual, colocar el original en `imports/` del candidato, calcular SHA-256 y declarar URL, entidad, periodo, formato y directorio que espera el parser.
4. Revalidar documentos/URLs seleccionados en la ronda. Conservar original y revisión por hash. Comparar filas contra una copia previa explícita; sin baseline, registrar que no se compararon revisiones.
5. Ejecutar solo el paso de construcción que el plan declare y cuyos insumos estén presentes. Aplicar `check` al producto, tabla, fuente, entidad y periodo solicitados; compartir institución no permite intercambiar productos.
6. Acreditar éxito solo en la capa comprobada: hash Bronze, contrato/grano/linaje Silver y controles Gold/meses/días/reconciliaciones que correspondan. Si no existe adaptador, terminar en captura o descubrimiento y declarar ese límite. No llenar faltantes ni activar/publicar.

Un 403, TLS, timeout o archivo inválido es un fallo de acceso/contenido; no prueba ausencia de publicación. Registrar pendiente y conservar el dato aceptado. Las fechas de publicación desconocidas siguen nulas.

El candidato rechaza los textos de error GDELT aunque su captura histórica tenga
HTTP 200. Conserva el original y el motivo en el recibo; RSS válido no acredita
que GDELT funcionó. Silver mantiene la edición fechada más reciente por URL y
consulta para respetar su grano. Las anteriores quedan en Bronze y
`data/quality/news_metadata_selection.json`, con fecha, archivo y hash. No
fusionar fechas distintas bajo una procedencia prestada. El archivo mensual de
PR142 conserva ese historial; esta selección no acredita un mes completo.

GDELT aporta primera observación, no fecha de publicación verificada. La integración
con Noticias conserva esos metadatos con publicación nula en
`data/quality/news_metadata_selection.json`, campo `publication_unknown_metadata`.
No los mezcla con una edición RSS fechada aunque compartan URL. Si solo hay
metadatos sin fecha de publicación, `parse.news` se detiene sin sobrescribir
Silver ni su recibo aceptados; guarda el intento bloqueado en
`data/quality/news_metadata_selection_attempt.json`. Los originales permanecen
para revisión y los recibos usan JSON estricto, con nulos para los no finitos. La consulta
canónica compartida cubre Aeroméxico, Viva y Volaris; no acredita cobertura total.

Los RSS con XML o fecha malformados se conservan como artefactos rechazados,
con archivo y motivo. Otras capturas válidas pueden construirse como cobertura
parcial; si no queda ninguna, se registra un intento bloqueado y se conservan
Silver y su recibo aceptados. Un archivo rechazado no acredita ausencia de noticias.

### Auditoría del corte observado, sin escrituras

```bash
python -m src.source_updates.news_cut rss --root <bronze-publico> --month 2026-09 --as-of 2026-10-19T12:00:00-06:00
python -m src.source_updates.news_cut candidate --file <corte-no-aprobado.json>
```

El primer comando verifica cuerpo, manifiesto y sidecar de cada RSS y deduplica
por URL canónica y día de publicación en México. Conserva todas las
contribuciones, consultas exactas y días no observados. No resuelve enlaces
opacos ni visita artículos; fecha RSS declarada no es fecha de evento ni prueba
de primera disponibilidad. El corte probado contiene 12 URLs de septiembre en
seis días, entre siete capturas retenidas; no promete cobertura de todo el mes
ni de todas las empresas. Una fecha ingenua o posterior a la captura se rechaza.

El segundo comando comprueba identidad, hashes propios y orden de fechas del
corte candidato upstream. No vuelve a verificar el cuerpo del emisor si no
está disponible y no concede aprobación. Los 11 registros de PR142 siguen
`candidate_unapproved`; su alcance es selección manual parcial junio–octubre.

GDELT `seendate` es primera observación del agregador, no publicación. Esta
rama conserva la corrección de PR142 y la cuarentena de publicación
desconocida. El intento normal de septiembre del 19 de octubre devolvió 503.
La nueva continuación autorizada del 21 de octubre volvió a comprobar septiembre
y la consulta canónica actual: ambos HTTP 503. Conservar los recibos y el cuerpo
fallido separado de Bronze válido; ninguna prueba con fixtures acredita una
extracción real. No continuar repitiendo esas consultas durante este lote.

El adaptador `python -m src.source_updates.gdelt recipe --period YYYYMmm
--as-of <corte>` delimita el mes de primera observación en México y máximo 250
resultados. Después de `collect`, `gdelt certify --workspace <candidato>
--period <mes> --as-of <corte-original> --collection <id>` permite `--dry-run`,
`--execute` y `--check`. Es un candidato Silver/Gold JSON propio, con contrato,
original/manifiesto/sidecar, punteros exactos, deduplicación URL/observación y
recibo inmutable. Se rechazan errores HTTP-200, recibos alterados, fechas fuera
de la consulta y cambios de corte. Publicación y evento siguen nulos, no se
descargan artículos ni se alimenta el archivo mensual aprobado. Vacío o tope
de resultados no prueba ausencia ni mes completo. El servicio sigue pendiente
de respuesta válida del periodo; no se amplía a otro proveedor o servicio pagado.

Investigación posterior del mismo 21/oct: diccionario y documentación oficiales
conservados en el paquete de revisión. GDELT respondió 200 con 164 artículos a
la consulta mensual, pero 14 observaciones caen en octubre de México; la
normalización rechaza el mes completo sin filtrar filas ni escribir Silver/Gold.
El recibo diagnóstico `current` tampoco satisface la identidad mensual de
certificación; no editarlo. El diagnóstico reducido siguiente recibió 429 y
terminó la investigación de red. El cuerpo oficial exige una petición cada
cinco segundos: `collect` usa el limitador GDELT de seis segundos por proceso
y bloquea nuevas peticiones de esa fuente tras 429 en la misma captura.
No ejecutar varios procesos en paralelo ni reintentar este lote. HTTP 200,
fixtures o disponibilidad del blog no certifican el periodo; conservar los
503 históricos y consultar la guía/matriz actuales antes del próximo lote.

Los auditores no escriben Silver/Gold ni activan el índice. La
[muestra](../../../docs/referencias/source-updates-20261019/curation-news-verification.json)
declara sus capas y límites.

## Certificación integral de RSS retenido

El certificador `python -m src.source_updates.rss_candidate` procesa solo
metadatos Google News de originales retenidos seleccionados. No invoca
`parse.news`, no modifica el archivo mensual aprobado y no visita artículos.
No resuelve URLs opacas ni atribuye compañías o idioma del artículo por el feed.

La receta de `batch` exige exactamente `version: 1`, `as_of` con zona,
`source_root`, `period` (`YYYYMmm`) y `originals` (lista explícita de rutas
Bronze). Admite 1–32 XML y 16 MB combinados, con 2 MB/250 items por captura. Primero
usar `batch --recipe <receta.json> --workspace tmp/source-updates/<lote-nuevo>
--dry-run`; `--execute` encadena retención, certificación y replay en el hijo
`rss-<period>`. Conserva un recibo de lote con etapa/objetivo/motivo al fallar.

Para selección individual: `retain --source-root <Bronze> --original <ruta>`
(repetible) `--workspace <candidato-nuevo> --dry-run/--execute`. Después usar
`certify --workspace <candidato> --period <mes> --as-of <corte> --retention <id>`
con `--execute` o `--check`. El modo sin ejecución muestra el plan.

Exigir HTTP 200 explícito, original/hash/tamaño/manifiesto/sidecar coincidentes,
canal RSS2.0 Google correspondiente a consulta y región, generación con zona
anterior a captura y todas las fechas declaradas de los items válidas. Un item
inválido bloquea el producto completo antes de escribir Silver/Gold, incluso
si estaba fuera del mes. Rechazar DOCTYPE, entidades y cambios de formato.

Silver conserva todos los items, repetidos y fuera del mes, con índice físico,
consulta exacta, título/URL/medio/guid declarados y procedencia propia. Gold
selecciona el mes de la fecha RSS en America/Mexico_City y agrupa por URL
canónica/día, manteniendo todos los padres/variantes. Cuatro JSON candidatos
(native, Gold, artefactos, puente) cumplen contrato estricto y se reconstruyen
sin red ni escrituras. No son tablas del warehouse ni contenido aprobado.

`--baseline baselines/<gold-previo.json>` admite comparación del mismo mes,
consultas y semántica; registra altas/bajas/cambios de metadatos y SHA del
baseline. Recapturas idénticas no son revisiones. Una discrepancia no acredita
una corrección del medio. Sin baseline, declarar comparación no realizada.

La fecha es declaración del agregador: publicación del cuerpo del medio no
verificada, evento/primera disponibilidad/rezago nulos. Días no observados no
significan ausencia de noticias. Las consultas históricas retenidas solo
buscan Aeroméxico: no acreditan cobertura de Viva/Volaris ni un mes completo.
Disponibilidad actual queda sin acreditar. `readiness` usa `rss_retained`,
recibo `rss-retained-<id>.json` y `rss-<mes>.json`; la política global conserva
GDELT requerido y las demás condiciones. Ningún comando aprueba/activa/publica.

### Disponibilidad física de las consultas RSS canónicas

`recipe --product rss --output selection` emite juntos `google_es` y
`google_en` desde `RSS_FEEDS`, con sus consultas exactas: dos GET base y cero
pagados. Aplicar `collect --selection <seleccion> --workspace <coleccion-nueva>
--dry-run` antes de una captura autorizada. No usar la rutina de ingesta activa,
visitar artículos ni cambiar consultas o cuotas para forzar un mes completo.

Retener ambos XML explícitos desde Bronze mediante el lote dedicado de arriba;
construir y reproducir el dossier del mes cerrado. El vínculo de readiness usa
`availability={workspace,run_id,feed_items:{google_es:<id>,google_en:<id>}}`
con IDs de la colección separada. Exige ambos feeds del mismo día local de la
ronda, HTTP200, manifiesto único, sidecars, consultas/locale y artefactos nativos
exactos. Un feed aislado o una consulta distinta no acredita esta disponibilidad.

El vínculo prueba respuestas actuales a esas dos consultas. Mantiene
`latest_available_period=null`, primera publicación desconocida, mes incompleto,
cobertura del medio no verificada y `agent_eligible=false`. Conservar todos los
items en Silver y el subconjunto mensual con sus contribuciones y días no
observados. No hay noticia validada desde un titular ni un archivo completo de
Google News. GDELT conserva su requisito y sus fallos, sin nuevas consultas o
sustitución. No comparar como revisiones dos snapshots de consultas distintas.
