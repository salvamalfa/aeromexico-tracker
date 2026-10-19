---
name: airline-update-airports
description: "Actualizar candidatos de la familia aeropuertos y grupos de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Aeropuertos y grupos

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `airports`. Alcance: OMA, AICM, AIFA y tráfico GAP/ASUR publicado vía SEC.

Descubrir el archivo de tráfico nuevo; los enlaces del catálogo pueden ser históricos. Separar aeropuerto de total de grupo y México de otros países de ASUR. AICM slots es otro producto: programación estacional, no tráfico realizado. AIFA XLSX puede cambiar de estructura; contrato y periodo real deben pasar. No atribuir totales aeroportuarios a Aeroméxico.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family airports
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.airports

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

## Adquisición por producto

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product oma_traffic
```

Consultar cada producto de esta familia:

- `oma_traffic` — solo descubrimiento. Entrada canónica: `constant:src.ingest.airports.groups:OMA_IR_URL`. Formato: HTML → PDF.
- `aicm_traffic` — solo descubrimiento. Entrada canónica: `constant:src.ingest.airports.groups:AICM_STATS_INDEX`. Formato: HTML → PDF.
- `aicm_slots` — selección/importación manual. Entrada canónica: `constant:src.ingest.airports.groups:AICM_STATS_INDEX`. Formato: PDF estacional de slots.
- `aifa_traffic` — solo descubrimiento. Entrada canónica: `constant:src.ingest.airports.groups:AIFA_STATS_INDEX`. Formato: HTML → XLSX.

### Procedimiento verificable

1. Ejecutar `recipe --product <producto>` y leer su procedimiento, URL resuelta, formato y bloqueo.
2. Para un índice HTML admitido, emitir la selección con `recipe --product <producto> --output selection > tmp/seleccion.json`. Revisarla con `collect --selection tmp/seleccion.json --workspace tmp/source-updates/<lote> --dry-run`. Capturar solo dentro del alcance autorizado.
3. Leer los enlaces y el contexto del catálogo preservado. Elegir el documento real y comprobar su periodo dentro del contenido. No transformar una plantilla histórica en una URL futura. Para importación manual, colocar el original en `imports/` del candidato, calcular SHA-256 y declarar URL, entidad, periodo, formato y directorio que espera el parser.
4. Revalidar documentos/URLs seleccionados en la ronda. Conservar original y revisión por hash. Comparar filas contra una copia previa explícita; sin baseline, registrar que no se compararon revisiones.
5. Ejecutar solo el paso de construcción que el plan declare y cuyos insumos estén presentes. Aplicar `check` al producto, tabla, fuente, entidad y periodo solicitados; compartir institución no permite intercambiar productos.
6. Acreditar éxito solo en la capa comprobada: hash Bronze, contrato/grano/linaje Silver y controles Gold/meses/días/reconciliaciones que correspondan. Si no existe adaptador, terminar en captura o descubrimiento y declarar ese límite. No llenar faltantes ni activar/publicar.

Un 403, TLS, timeout o archivo inválido es un fallo de acceso/contenido; no prueba ausencia de publicación. Registrar pendiente y conservar el dato aceptado. Las fechas de publicación desconocidas siguen nulas.

Para OMA, AICM y AIFA, `recipe --output selection --catalog-file <html>
--period <YYYYMmm|latest>` elige un enlace visible y no ambiguo. La fecha de
ese enlace es descubrimiento; el PDF/XLSX debe acreditar el periodo en filas.
Un 404 en el documento enlazado es fallo de acceso. No sustituirlo por una
URL construida. El control Stage 4 conserva el mínimo histórico de siete
meses contiguos AICM/AIFA y admite meses posteriores realmente parseados.
