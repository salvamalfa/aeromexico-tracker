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

### Respaldo primario verificable por atributo o evento

```bash
python -m src.source_updates.primary_review --bundle docs/referencias/source-updates-20261019/peer-primary-review.json --root old_public=<bronze-publico>
```

Para `event-primary-review.json`, añadir raíces `context_primary`,
`context_extra`, `am_july` y `dot_review` con `--root <id>=<carpeta>`.
El auditor es de lectura: comprueba hash, tamaño, manifiesto, sidecar,
localizador documental y versión del código revisado. Rechaza respuestas HTTP
fallidas como respaldo. DOT se limita a un original de investigación sin
registro activo, con recibo exacto; no toma prestado el alias FAA ni entra en
Silver/Gold. Las fechas tipadas conservan mes reportado, fecha de evento,
documento, archivo del emisor, presentación SEC y captura por separado.

Un pasaje coincidente no aprueba su interpretación. Mantener
`agent_eligible=false` y `silver_gold_certification=false`. El mapa de perfiles
abarca cinco empresas, 100 evaluaciones y 60 evidencias; no todos los atributos
quedan respaldados. Conservar las discrepancias Ryanair millas/indicador global
`metric`, Viva matriz/operadora, USD por edición y pasajeros reservados frente
a transportados. No corregir perfiles, conversiones, cohortes o Gold desde el
auditor. Los códigos por entidad y decisiones de comparación requieren revisión.

El mapa de 21 eventos contiene 54 evidencias de 24 originales; el evento DOT de
octubre tiene respaldo parcial. No convertir un enlace 404 en hecho verificado,
ni un documento retrospectivo en publicación contemporánea. Impacto, categoría,
confianza y selección permanecen curados sin aprobación nueva.
Consultar la [guía](../../../docs/catalogo-fuentes-calendario.md) y los mapas
versionados para límites y decisiones pendientes; no inventar un endpoint para
resolverlas.

### Candidato de unidades y emisores por edición

`python -m src.source_updates.curated_profiles --bundle
docs/referencias/source-updates-20261019/peer-primary-review.json --root
old_public=<Bronze-retenido> --workspace tmp/source-updates/<nuevo> --as-of
<corte>` permite `--dry-run`, `--execute` y `--check`. Comprueba el mapa y sus
originales antes de extraer 11 métricas acotadas de Ryanair FY2026 y Viva 2T26.
Conserva escala por métrica: ASM en millas aunque el perfil global diga metric,
USD de la edición Viva y pasajeros reservados no necesariamente transportados.
FY2026 sigue anual, no trimestre. Emisor consolidado y subsidiaria operadora
son entidades distintas; no se asignan sus totales a un código de operador.
El resultado Silver/Gold JSON candidato es determinista e inmutable y exige
inventario exacto. `--baseline` acepta un baseline explícito según su CLI;
sin baseline la comparación se declara no realizada.

`python -m src.source_updates.operator_registry --root <capturas-auditadas>
--as-of <corte>` verifica cuatro filas IATA/FAA capturadas de sus páginas
oficiales, separadas de la fuente activa IASA. No captura ni escribe; comprueba
URL y callback, HTTP, SHA, tamaño, fecha y fila literal. VB/VIV se refieren a
Aeroenlaces; FR y RYR conservan los nombres literales Ryanair Ltd./RYANAIR.
No prueban por sí solos equivalencia jurídica con DAC ni con Holdings.
Una referencia de código no autoriza esa unión, comparabilidad o publicación.
Las tesis 2T26 ya publicadas se preservan; las versiones nuevas conservan sus
puertas de aprobación.
