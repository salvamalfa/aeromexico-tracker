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

AFAC por aerolínea puede vincular su disponibilidad documental después del
replay integral del boletín y la base: `availability` lleva `workspace`,
`run_id`, `catalog_item` y `artifact_items={"pdf": "<id>", "database": "<id>"}`.
Los dos IDs son distintos y pertenecen a la misma colección oficial, posterior
al índice y de la fecha local de la ronda. El índice debe anunciar el último
boletín y `DB_AFAC.zip`; su miembro es `DB_AFAC.xlsx`. Se comprueban los pares
archivo/hash de ambos originales en la tabla nativa, sin usar solo el PDF.
Mantener `complete_month_certified=false` y la advertencia internacional.
Verificar todo lo reportado no prueba un universo observacional completo ni
autoriza participaciones de mercado con denominadores supuestos. La ronda
global y la publicación conservan sus puertas independientes.

## Adquisición por producto

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product afac_carriers
```

Consultar cada producto de esta familia:

- `afac_carriers` — parser candidato de boletines y base 2026, condicionado a sus insumos. Entrada canónica: `constant:src.ingest.afac.download:DATATUR_CATALOG_URL`. Formato: HTML → PDF/XLS/ZIP DATATUR.
- `afac_airports` — adaptador offline de original retenido revisado. Entrada canónica: `url:https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404`. Formato: archivo independiente por edición.
- `afac_countries` — adaptador offline de cajas exactas acumuladas; no serie mensual desde gráficas. Entrada canónica: `url:https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404`. Formato: boletín/archivo de países.
- `afac_margins` — adaptador offline de dos libros de la misma edición. Entrada canónica: `url:https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404`. Formato: XLSX sase/resumen de la misma edición.
- `bts_segments` — certificador integral de originales T-100, descubrimiento FJE y vínculo físico; mes explícito y diccionario incorporado revisado. Entrada canónica: `constant:src.ingest.bts.t100:FORM_URL`. Formato: formulario GET + POST → ZIP CSV.

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


### Productos AFAC retenidos

Aplicar el [flujo común de retención](../source-updates-common.md#originales-retenidos-y-lote-offline).
`afac_airports` exige rol `workbook`: 65 nombres de aeropuerto, tres métricas,
dos mercados y meses enero–julio de la edición julio 2026, con 173 cruces
visibles. Son totales de aeropuerto, sin operador. Los ceros futuros de plantilla
no se importan; los ceros de meses cubiertos se conservan como reportados.

`afac_margins` exige `routes` y `carriers`. La edición se comprueba en el
contenido del resumen, año/tablas O-D y 28 reconciliaciones exactas entre
marginales; 120 controles contrastan totales de las tablas. Se conservan las
notas por empresa/métrica/mes: cinco celdas estimadas por la fuente. No se
estima ninguna celda empresa×ruta ni se modifica la cohorte de Vuelos.

`afac_countries` exige `pdf` y `routes`. Solo se extraen las cajas exactas
acumuladas actuales/comparativas de 29 países. Los pasajeros actuales cuadran
con O-D; los vuelos literales del boletín no se armonizan con vuelos O-D que
incluyen otro universo. El acumulado no se presenta como julio mensual; las
gráficas redondeadas y los países ausentes no se rellenan.

## Dossier mensual por aerolínea

El certificador aislado `python -m src.source_updates.carrier_source_candidate`
admite `afac_carriers` con `retain --source-root <Bronze> --workspace <nuevo>`
y roles `--original pdf=<ruta> --original database=<ruta>`. `--dry-run` revisa
la selección; `--execute` retiene sin nuevas llamadas. `certify --product
afac_carriers --workspace <candidato> --period 2026M08 --as-of <corte-con-zona>
--retention <id>` admite vista previa, `--execute` y replay `--check` inmutable.
El lote `retained_round` lo despacha; readiness requiere `carrier_source`.

Se conservan seis conteos por fila PDF: anual 2024/2025, acumulados y meses
actual/comparativo. Se concilian operadores, subtotales y totales contra las
filas regulares de la base 2024/2025/2026. Año, servicios y último mes de la
base deben corresponder al boletín. Silver guarda también historia/fletamento;
Gold propio selecciona solo el mes actual: regular PDF con padres de soporte
DB y cada fila charter única. Un duplicado charter actual bloquea. No hay
suma tácita, reparto a rutas ni cambio del parser/estimador existente.

Conservar literalmente `World 2 Fly`, nombres desconocidos sin mapeo y Aerovías
separada de Connect. Crosswalk exacto, efectivo y por hash/fila. Exigir la
declaración documental de preliminar y limitar estimados a nombre/periodo de
la nota; la base no recibe flags PDF. La advertencia de información incompleta
internacional permanece visible: filas reportadas conciliadas no acreditan
el universo completo ni disponibilidad reciente. Sin activación/publicación.

### BTS retenido: certificación mensual completa del candidato

Usar `python -m src.source_updates.bts_candidate retain` con producto
`bts_segments`, rol único `archive` y un ZIP público ya retenido. Después,
`certify --period YYYYMmm --as-of <corte zonificado> --retention <run_id>`:
primero `--dry-run`, luego `--execute` en un candidato nuevo, y `--check`
para la repetición offline. `retained_round` lo dirige al adaptador `bts`;
no usar el certificador genérico ni el parser global `build_t100`, que escribe
el crosswalk del proyecto. El verificador de ronda requiere `adapter=bts`.

El ZIP debe contener exactamente datos y `Documentation.csv` revisados.
Comprobar 30 columnas, unidades, año/mes/trimestre, continuidad de meses,
grano operador/entidad/dirección/aeronave/configuración/clase y cada identidad
contra los seis campos exactos del crosswalk. Usar la dimensión de aerolíneas
aprobada como referencia versionada, conservando sus dos huellas en el recibo;
no modificarla ni resolver identidades por parecido del nombre.

Silver conserva todo el archivo y el localizador de cada fila. Gold contiene
solo el mes pedido, que puede ser anterior al máximo observado para revisar
meses previos. Suma pasajeros por tramo, asientos y vuelos programados/realizados
por separado; calcula ASM/RPM antes de agregar, ocupación como RPM/ASM, distancia
mediana y conversiones libras→kg/millas→km. Capacidad cero conserva ocupación
nula. Mantener todos los padres de cada agregado en el linaje. Comparar
revisiones contra el Silver nativo completo bajo `baselines/`; distinguir
altas retrospectivas de meses recién añadidos.

No suponer realizados≤programados. Conservar literalmente F/G/L/P: el
diccionario retenido dice «Service Class» y no acredita una leyenda de
regularidad. Si hay pasajeros superiores a asientos en el mes pedido,
bloquear antes de Silver/Gold; conservar el original para investigación.
Incidencias en meses no proyectados siguen visibles en Silver y en el recibo,
sin certificarlos como datos válidos para publicar.

La certificación se limita a las observaciones retenidas MX↔US del operador.
No prueba cobertura completa por aerolínea, itinerarios/codeshares, red mundial,
última disponibilidad ni primera fecha de publicación. Esos límites permanecen
en el recibo; la aprobación humana, el control global y la activación siguen
separados. La guía canónica conserva los originales, hashes y pruebas reales.

### Descubrimiento y disponibilidad física BTS

```bash
python -m src.source_updates recipe --product bts_segments --output selection > tmp/bts-index.json
python -m src.source_updates collect --selection tmp/bts-index.json --workspace tmp/source-updates/bts-index --dry-run
# Tras capturar el índice autorizado, usar su ruta real; no una fecha supuesta.
python -m src.source_updates recipe --product bts_segments --output selection --catalog-file <historial-retenido.html> --period latest > tmp/bts-years.json
python -m src.source_updates collect --selection tmp/bts-years.json --workspace tmp/source-updates/bts-years --dry-run
```

La selección revisada del 27/oct incluye historial, año 2026 con julio añadido
y año 2023 revisado: cinco llamadas base, cero pagadas. Solo la fila exacta
FJE «T-100 International Segment (All Carriers)» determina el descubrimiento;
Market y US Carriers son productos distintos, aunque anuncien la misma fecha.
No descargar toda la historia ni inventar agosto desde una fecha de anuncio.
La fecha 9/oct del historial es una fecha declarada, sin hora ni prueba de
primera publicación. El vínculo `availability` usa el índice, `run_id` y el
ZIP del año actual; verifica además los años revisados de esa colección.

El lexer de aeronave conserva el código crudo `094` y su entero 94 según
el lookup oficial; las demás claves y conteos siguen estrictos. Se rechaza
la colisión de grano tras normalizar. La configuración 3 está respaldada por
el lookup como combinación de pasajeros/carga; 0, 4 y 9 quedan fuera del
formato físico revisado. No inferir flota, nombres ni regularidad de estos
códigos. Guardar lookups, fechas y hashes junto a la evidencia técnica.
