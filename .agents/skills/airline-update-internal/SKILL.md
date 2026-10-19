---
name: airline-update-internal
description: "Actualizar candidatos de la familia derivados y curación de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Derivados y curación

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `internal`. Alcance: peer_profile, curated_primary_sources y derived_gold, sin endpoint propio.

No crear tres descargas ficticias. Reconstruir solo derivados con padres validados, versión de fórmula, unidades y fecha de corte. Preservar N/D, etiquetas reportado/calculado/inferido/estimado/programado y reglas de ponderación. Hash agregado o fuente heredada requiere puente de linaje, no una URL inventada. No reentrenar forecast, recalcular estudios, cambiar cortes de análisis ni activar tesis.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family internal
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: transform.stage4,transform.validate_stage4,transform.validate_stage5,transform.validate_silver,transform.stage6,transform.validate_stage6; requieren todos sus insumos y no incluyen analytics/dashboard/publicación.

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

## Adquisición por producto

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product peer_profiles
```

Consultar cada producto de esta familia:

- `peer_profiles` — sin descarga. Entrada canónica: `catalogue:peer_profile`. Formato: curación con padres.
- `curated_context` — sin descarga. Entrada canónica: `catalogue:curated_primary_sources`. Formato: curación con fuentes primarias.
- `derived` — sin descarga. Entrada canónica: `catalogue:derived_gold`. Formato: transformaciones offline.

### Procedimiento verificable

1. Ejecutar `recipe --product <producto>` y leer su procedimiento, URL resuelta, formato y bloqueo.
2. Para un índice HTML admitido, emitir la selección con `recipe --product <producto> --output selection > tmp/seleccion.json`. Revisarla con `collect --selection tmp/seleccion.json --workspace tmp/source-updates/<lote> --dry-run`. Capturar solo dentro del alcance autorizado.
3. Leer los enlaces y el contexto del catálogo preservado. Elegir el documento real y comprobar su periodo dentro del contenido. No transformar una plantilla histórica en una URL futura. Para importación manual, colocar el original en `imports/` del candidato, calcular SHA-256 y declarar URL, entidad, periodo, formato y directorio que espera el parser.
4. Revalidar documentos/URLs seleccionados en la ronda. Conservar original y revisión por hash. Comparar filas contra una copia previa explícita; sin baseline, registrar que no se compararon revisiones.
5. Ejecutar solo el paso de construcción que el plan declare y cuyos insumos estén presentes. Aplicar `check` al producto, tabla, fuente, entidad y periodo solicitados; compartir institución no permite intercambiar productos.
6. Acreditar éxito solo en la capa comprobada: hash Bronze, contrato/grano/linaje Silver y controles Gold/meses/días/reconciliaciones que correspondan. Si no existe adaptador, terminar en captura o descubrimiento y declarar ese límite. No llenar faltantes ni activar/publicar.

Un 403, TLS, timeout o archivo inválido es un fallo de acceso/contenido; no prueba ausencia de publicación. Registrar pendiente y conservar el dato aceptado. Las fechas de publicación desconocidas siguen nulas.

Para Stage 6 candidato, `transform.gold_lineage` debe seguir a
`transform.validate_stage6`. Reconstruye catálogo y puente mediante los gates
existentes y verifica los archivos Bronze. Reportar aparte declaraciones sin
artefacto exacto; no son trazabilidad documental. `check` no las acepta como
respaldo de cifras solicitadas. No ejecutar Stage 7/modelos/publicación para
superar un control de actualización por fuente.
