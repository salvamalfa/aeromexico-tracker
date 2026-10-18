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
ausencia de noticias. Reutilizar el archivo mensual de PR136 tras integrarlo;
no cambiar su rama ni activar candidatos. El contrato Silver conserva un
representante por noticia y `provenance_json` registra sus fuentes; una fuente
sin representante debe revisarse en esa procedencia antes de afirmar cobertura.

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
