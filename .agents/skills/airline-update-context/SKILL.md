---
name: airline-update-context
description: "Actualizar candidatos de la familia referencias y contexto de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Referencias y contexto

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `context`. Alcance: OurAirports, FAA IASA y diccionario Loughran–McDonald.

Versionar crosswalk y diccionario. Un código nuevo requiere revisar filas no mapeadas y monto AFAC sin mapear. OurAirports es referencia comunitaria; IASA evalúa al país, no a una aerolínea y no demuestra causalidad. Cambiar versión del diccionario exige revisar comparabilidad del tono, sin recalcularlo automáticamente.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family context
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.airport_reference escribe dim_airport en Gold candidato; requiere data/reference. FAA y diccionario necesitan curación/adapter explícitos.

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

## Adquisición por producto

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product airports_reference
```

Consultar cada producto de esta familia:

- `airports_reference` — condicionado a insumos/formato. Entrada canónica: `constant:src.ingest.airports.reference:OURAIRPORTS_URL`. Formato: GET → CSV.
- `iasa` — solo descubrimiento. Entrada canónica: `catalogue:faa_iasa`. Formato: PDF FAA.
- `dictionary` — selección/importación manual. Entrada canónica: `catalogue:loughran_mcdonald`. Formato: CSV de diccionario versionado.

### Procedimiento verificable

1. Ejecutar `recipe --product <producto>` y leer su procedimiento, URL resuelta, formato y bloqueo.
2. Para un índice HTML admitido, emitir la selección con `recipe --product <producto> --output selection > tmp/seleccion.json`. Revisarla con `collect --selection tmp/seleccion.json --workspace tmp/source-updates/<lote> --dry-run`. Capturar solo dentro del alcance autorizado.
3. Leer los enlaces y el contexto del catálogo preservado. Elegir el documento real y comprobar su periodo dentro del contenido. No transformar una plantilla histórica en una URL futura. Para importación manual, colocar el original en `imports/` del candidato, calcular SHA-256 y declarar URL, entidad, periodo, formato y directorio que espera el parser.
4. Revalidar documentos/URLs seleccionados en la ronda. Conservar original y revisión por hash. Comparar filas contra una copia previa explícita; sin baseline, registrar que no se compararon revisiones.
5. Ejecutar solo el paso de construcción que el plan declare y cuyos insumos estén presentes. Aplicar `check` al producto, tabla, fuente, entidad y periodo solicitados; compartir institución no permite intercambiar productos.
6. Acreditar éxito solo en la capa comprobada: hash Bronze, contrato/grano/linaje Silver y controles Gold/meses/días/reconciliaciones que correspondan. Si no existe adaptador, terminar en captura o descubrimiento y declarar ese límite. No llenar faltantes ni activar/publicar.

Un 403, TLS, timeout o archivo inválido es un fallo de acceso/contenido; no prueba ausencia de publicación. Registrar pendiente y conservar el dato aceptado. Las fechas de publicación desconocidas siguen nulas.
