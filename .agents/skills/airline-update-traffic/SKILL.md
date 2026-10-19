---
name: airline-update-traffic
description: "Actualizar candidatos de la familia tráfico afac y bts de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Tráfico AFAC y BTS

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `traffic`. Alcance: AFAC: aerolínea, aeropuertos, países y marginales como productos distintos; BTS T-100 International Segment MX↔US.

AFAC exige misma edición acumulada para O-D y marginal por operador. El parser candidato de boletines 2026 exige PDF y base de fletamento del mismo mes: un control para agosto bloquea si falta cualquiera. No asignar el total de ruta a una aerolínea. BTS usa mode=bts_year con año explícito y FORM_URL de src/ingest/bts/t100.py: GET del formulario y POST, incluso para años revisados. No llamar ingest_t100 para descargar toda la historia. Verificar máximo mes realmente presente en MX-US; el anuncio de BTS no lo demuestra. Separar operador de comercializador, realizados de programados y Segment de Market. Seleccionar también años afectados por revisiones, no solo el corriente.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family traffic
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.bts,parse.afac

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

## Adquisición por producto

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product afac_carriers
```

Consultar cada producto de esta familia:

- `afac_carriers` — parser candidato de boletines y base 2026, condicionado a sus insumos. Entrada canónica: `constant:src.ingest.afac.download:DATATUR_CATALOG_URL`. Formato: HTML → PDF/XLS/ZIP DATATUR.
- `afac_airports` — adaptador pendiente. Entrada canónica: `url:https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404`. Formato: archivo independiente por edición.
- `afac_countries` — adaptador pendiente. Entrada canónica: `url:https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404`. Formato: boletín/archivo de países.
- `afac_margins` — selección/importación manual. Entrada canónica: `url:https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404`. Formato: XLSX sase/resumen de la misma edición.
- `bts_segments` — condicionado a insumos/formato. Entrada canónica: `constant:src.ingest.bts.t100:FORM_URL`. Formato: formulario GET + POST → ZIP CSV.

### Procedimiento verificable

1. Ejecutar `recipe --product <producto>` y leer su procedimiento, URL resuelta, formato y bloqueo.
2. Para un índice HTML admitido, emitir la selección con `recipe --product <producto> --output selection > tmp/seleccion.json`. Revisarla con `collect --selection tmp/seleccion.json --workspace tmp/source-updates/<lote> --dry-run`. Capturar solo dentro del alcance autorizado.
3. Leer los enlaces y el contexto del catálogo preservado. Elegir el documento real y comprobar su periodo dentro del contenido. No transformar una plantilla histórica en una URL futura. Para importación manual, colocar el original en `imports/` del candidato, calcular SHA-256 y declarar URL, entidad, periodo, formato y directorio que espera el parser.
4. Revalidar documentos/URLs seleccionados en la ronda. Conservar original y revisión por hash. Comparar filas contra una copia previa explícita; sin baseline, registrar que no se compararon revisiones.
5. Ejecutar solo el paso de construcción que el plan declare y cuyos insumos estén presentes. Aplicar `check` al producto, tabla, fuente, entidad y periodo solicitados; compartir institución no permite intercambiar productos.
6. Acreditar éxito solo en la capa comprobada: hash Bronze, contrato/grano/linaje Silver y controles Gold/meses/días/reconciliaciones que correspondan. Si no existe adaptador, terminar en captura o descubrimiento y declarar ese límite. No llenar faltantes ni activar/publicar.

Un 403, TLS, timeout o archivo inválido es un fallo de acceso/contenido; no prueba ausencia de publicación. Registrar pendiente y conservar el dato aceptado. Las fechas de publicación desconocidas siguen nulas.

### Boletines candidatos de 2026

`parse.afac` del coordinador exige el ZIP DATATUR verificado y los PDF de todos
sus meses contiguos, además de los libros anuales, crosswalk y SEC preservados.
Extrae un único XLSX offline; contrasta meses regular/fletamento y el mes
comparado en ambas páginas PDF. Conserva las notas de cobertura y estimación por página y mercado: página 1 doméstico, página 2 internacional, igual que el parser canónico. Las notas PDF se añaden solo a sus filas regulares de ese mes y mercado; el fletamento mantiene las notas de su propio artefacto.
No basta el nombre del PDF. El límite se deriva de esas observaciones, sin
corte fijo de junio. El parser nuevo se limita al formato 2026; otro año o
esquema exige revisión. La ruta heredada fuera del coordinador conserva su
corte por defecto. Septiembre ausente del catálogo no se inventa.
