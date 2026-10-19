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
controles al integrar esta rama aislada anterior. No cambiar la rama de su
responsable ni activar candidatos. El contrato Silver conserva un
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

GDELT `seendate` es primera observación del agregador, no publicación. No
ejecutar el parser legado de esta base sobre GDELT: al integrar, preservar la
corrección de PR142 y cuarentena de publicación desconocida. El intento normal
de septiembre devolvió 503; no repetirlo en esta continuación. Guardar el fallo
y esperar una ronda posterior autorizada, sin inferir cero noticias.

Los auditores no escriben Silver/Gold ni activan el índice. La
[muestra](../../../docs/referencias/source-updates-20261019/curation-news-verification.json)
declara sus capas y límites.
