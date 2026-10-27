---
name: airline-update-macro-market
description: "Actualizar candidatos de la familia macro y mercado de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Macro y mercado

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `macro_market`. Alcance: Banxico FIX/INPC/tasa, H.10 de respaldo, EIA y precios bursátiles.

Capturar la historia diaria dentro de la ronda mensual o trimestral, sin refresh diario/semanal. Las series Banxico tienen calendarios distintos. H.10 conserva su etiqueta como respaldo y no sustituye silenciosamente FIX. Reportar días observados de combustible y tipo de cambio; promedios parciales no son trimestre completo. Combustible spot no es costo contratado. Mantener identidad de AERO e IPO; no empalmar la acción vieja. Los ajustes de precios requieren comparación por fecha/ticker. Respetar entidad y periodo que espera cada parser: EIA usa EER_EPJK_PF4_RGC_DPG y periodo inicio_fin.

## Ejecución

### Ejemplo completo de combustible

```bash
python -m src.source_updates recipe --product fuel --period 2026M09 --as-of 2026-10-18T18:00:00-06:00 --output round > tmp/combustible.json
python -m src.source_updates round --recipe tmp/combustible.json --workspace tmp/source-updates/combustible --dry-run
# Solo si está autorizada la captura pública del lote:
python -m src.source_updates round --recipe tmp/combustible.json --workspace tmp/source-updates/combustible --execute
```

El generador obtiene `EIA_XLS_URL` y `EIA_SERIES_ID` de
`src.ingest.macro.fuel`: GET del XLS histórico, hoja `Data 1`, encabezado en
fila 3, serie `EER_EPJK_PF4_RGC_DPG`, entidad idéntica y ventana
`2015-01-01_2026-09-30`. `parse.fuel` lee ese original y el control exige filas
reales de septiembre, fuente EIA, serie correcta y valores observados. El
piloto real produjo 21 filas. La fuente original llega al 14 de octubre;
la receta no presenta su corte de septiembre como última disponibilidad.
[Artefactos y hashes del piloto](../../../docs/referencias/source-updates-20261018/real-source-pilot.json).

### Banxico y respaldo H.10

El mismo comando con `--product banxico` emite tres selecciones POST públicas:
SF43718 = FIX, SP1 = INPC y SF61745 = tasa. La URL y el formulario se obtienen
de `SIE_EXPORT_URL` y `sie_export_form`; el JSON generado muestra los campos
exactos, año inicial 2015, año final y formato CSV. No usa token. `parse.fx`
exige las tres capturas y los controles verifican cada serie por separado.
Si devuelve HTML, 403 o una serie distinta, queda bloqueado; no aceptar cero.

`--product h10` emite el GET de `H10_EXPORT_URL` con los parámetros de
`h10_export_params`: `rel=H10`, paquete `FED_H10_PACKAGE`, `filetype=csv`,
`layout=seriescolumn`, fechas `from/to` y columna `RXI_N.B.MX`. El paso
`parse.h10` conserva `federal_reserve_h10` y la serie `H10/H10/RXI_N.B.MX`.
Es solo un respaldo FX; INPC y tasa siguen faltantes. Elegirlo explícitamente
si falla FIX; no empalmar silenciosamente las series. Ninguno de esos
adaptadores se declara accesible en vivo sin el recibo correspondiente.

### Precios bursátiles

`recipe --product equities --output round --period 2026M09 --as-of <ISO>`
emite cinco GET públicos acotados. `parse.market_chart` lee los JSON originales,
exige ticker/USD/EQUITY, precios y ajustes explícitos, volumen entero observado
y SEC local verificable. AERO comienza el 6 de noviembre de 2025; no empalmar
su acción anterior. Una serie faltante bloquea el conjunto. Conservar los JSON
y comparar revisiones por fecha/ticker; no convertir faltantes en cero.
El parser `parse.market` conserva la alternativa histórica de cinco CSV
normalizados. No invocar `run()` activo. `parse.complementary` candidato usa
JSON si hay alguna selección chart, y exige entonces las cinco; nunca oculta
un lote incompleto con CSV anteriores.
```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family macro_market
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.fx,parse.h10,parse.fuel,parse.market,parse.market_chart

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
`parse.fx` exige los tres CSV Banxico SF43718, SP1 y SF61745. H.10 usa el paso
separado `parse.h10`, solo FX rotulado: no satisface INPC/tasa ni se llama FIX.
`parse.market` requiere `data/silver/sec_report_text.parquet`
preparado en el candidato desde evidencia SEC y los cinco CSV Yahoo normalizados
(AERO, VLRS, RYAAY, DAL, ICAGY). Si seleccionas `parse.sec` en la misma receta,
debe preceder a `parse.market`. No fabricar evidencia de identidad ni abrir
credenciales para evitar ese bloqueo. El modo en seco enumera los requisitos.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

## Adquisición por producto

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product banxico
```

Consultar cada producto de esta familia:

- `banxico` — adaptador candidato implementado. Entrada canónica: `constant:src.ingest.macro.banxico:SIE_EXPORT_URL`. Formato: POST público → CSV latino-1.
- `h10` — adaptador candidato implementado. Entrada canónica: `constant:src.ingest.macro.banxico:H10_EXPORT_URL`. Formato: GET con parámetros DDP → CSV.
- `fuel` — adaptador candidato implementado. Entrada canónica: `constant:src.ingest.macro.fuel:EIA_XLS_URL`. Formato: GET → XLS histórico, Data 1/header=2.
- `equities` — captura pública candidata y parseo offline del JSON chart; exige las cinco series y evidencia SEC local.

### Procedimiento verificable

1. Ejecutar `recipe --product <producto>` y leer su procedimiento, URL resuelta, formato y bloqueo.
2. Para un índice HTML admitido, emitir la selección con `recipe --product <producto> --output selection > tmp/seleccion.json`. Revisarla con `collect --selection tmp/seleccion.json --workspace tmp/source-updates/<lote> --dry-run`. Capturar solo dentro del alcance autorizado.
3. Leer los enlaces y el contexto del catálogo preservado. Elegir el documento real y comprobar su periodo dentro del contenido. No transformar una plantilla histórica en una URL futura. Para importación manual, colocar el original en `imports/` del candidato, calcular SHA-256 y declarar URL, entidad, periodo, formato y directorio que espera el parser.
4. Revalidar documentos/URLs seleccionados en la ronda. Conservar original y revisión por hash. Comparar filas contra una copia previa explícita; sin baseline, registrar que no se compararon revisiones.
5. Ejecutar solo el paso de construcción que el plan declare y cuyos insumos estén presentes. Aplicar `check` al producto, tabla, fuente, entidad y periodo solicitados; compartir institución no permite intercambiar productos.
6. Acreditar éxito solo en la capa comprobada: hash Bronze, contrato/grano/linaje Silver y controles Gold/meses/días/reconciliaciones que correspondan. Si no existe adaptador, terminar en captura o descubrimiento y declarar ese límite. No llenar faltantes ni activar/publicar.

Un 403, TLS, timeout o archivo inválido es un fallo de acceso/contenido; no prueba ausencia de publicación. Registrar pendiente y conservar el dato aceptado. Las fechas de publicación desconocidas siguen nulas.

Los agregados Gold usan periodo observado y puente verificado. La tasa objetivo se expresa en `percent`, FX en `mxn_per_usd`; no reescalar el valor reportado.


## Certificador integral de originales retenidos

Usar `python -m src.source_updates.series_candidate retain|certify` para
`banxico`, `fuel` y `equities`; ver [contrato y comandos](../../../docs/catalogo-fuentes-calendario.md#certificación-de-series-retenidas-22-de-octubre).
`retain --dry-run` muestra la selección sin escribir; `--execute` copia originales
locales y conserva su captura, sin red. `certify --dry-run` muestra salidas;
`--execute` reconstruye Silver/Gold candidatos; `--check` repite sin escribir.
Banxico exige SF43718/SP1/SF61745, EIA workbook y equities los cinco tickers más
identity SEC físico. Mes y trimestre son ventanas separadas; todos los meses
son obligatorios. No usar el certificador nativo `retained` para estos productos.

Integrar el recibo con `adapter=series` y su ID de retención en `readiness` o
`global_readiness`. No pasar una revisión local como ronda completa. Las series
completas significan todas las observaciones de los originales seleccionados;
el calendario no se acredita por defecto. Banxico puede aportar el método
físico adicional descrito abajo; EIA/mercado conservan su límite. Publicación
y rezago desconocidos quedan nulos. El pipeline anterior
conserva su utilidad para adquisición/diagnóstico, no recibe certificación por
la existencia de este adaptador. No cambia Gold público ni activa calendario.

### Disponibilidad física de las respuestas canónicas

Después de `series_candidate` y su replay integral, readiness admite
`availability={workspace,run_id,series_items:{<rol>:<id>}}` para una colección
separada del mismo día local. Roles exactos: Banxico `SF43718`, `SP1`,
`SF61745`; EIA `workbook`; mercado `AERO`, `VLRS`, `RYAAY`, `DAL`, `ICAGY`.
Usar IDs emitidos por la selección de `recipe --output round` y revisar el
plan de `collect` antes de la captura autorizada: tres POST, un GET o cinco
GET respectivamente, cero pagados. No ejecutar la ingesta activa.

El contrato verifica URL, ventana y, en Banxico, formulario realmente enviado;
colección completa, manifiesto único, sidecars, alias, hash y aporte de cada
serie a su tabla nativa reproducida. No reetiquetar una respuesta como otro
producto. Mercado conserva por separado la identidad SEC retenida y verificada;
no representa una consulta SEC nueva ni cambia su identidad de acceso.
Si hace falta reunir originales de dos raíces, copiar literalmente archivo,
sidecar y registro del manifiesto a un inventario de staging nuevo. No inventar
capturas, fechas, métodos o recibos; conservar raíces y recibos originales.

Este vínculo acredita respuestas actuales para la ventana histórica solicitada.
`latest_available_period` y primera publicación siguen nulos. El calendario
de observaciones no se acredita con las respuestas por sí solas; sin evidencia
adicional bloquea incorporación tanto mensual como trimestral. Los recuentos de datos y
el último día observado no prueban los días en que debía existir una observación.
No compartir calendario entre FIX, tasa, inflación, EIA y bolsas. La evidencia
Yahoo `tradingPeriods` de AERO es solo un insumo candidato, sin prueba aún de
exhaustividad ni de los cinco tickers; no se usa para cambiar esos flags.

### Calendario de observaciones Banxico

La retención admite exactamente tres roles, o esos tres más
`--original fix_methodology=<ruta-Bronze-exacta>`. El cuarto es el HTML oficial
`METHOD_URL` de `src.source_updates.banxico_calendar`, edición revisada SHA
`f49a330d…`; conservar original, manifiesto, sidecar y captura. No representa
una cotización ni se incorpora como padre del linaje numérico. Otra edición
requiere revisión; no transformar una página nueva en la ya revisada.

Ejecutar primero `series_candidate retain --dry-run` con los cuatro roles y
después `--execute`. En un candidato nuevo, `certify --period 2026M09 --as-of
<corte-posterior-a-las-capturas> --retention <id>` admite preview, ejecución y
replay `--check`. El corte real probado fue `2026-10-27T06:30:00-06:00`.
Usar después el binding de disponibilidad de las **tres consultas CSV**:
la evidencia metodológica adicional se relee desde el candidato, no exige
fingir una cuarta consulta de datos ni reescribir la colección original.

FIX usa Fecha de Determinación y el conjunto exacto de hábiles bancarios
mexicanos verificados. INPC exige una observación por mes, anclada al día 1.
Para tasa, cubrir todas las etiquetas diarias posibles es condición suficiente;
no se infiere el calendario esperado del proveedor desde una ausencia.
Septiembre verificó 21/1/30. Q3 verificó 65/3/91 y queda no certificado frente
al universo diario por el 12/julio no observado. No imputar ni reducir el
requisito. Tres roles antiguos mantienen `false`; un booleano manual no lo cambia.

El recibo liga método, cuatro originales, calendario bancario y cálculo por
hash, con reproducción física en `check`, Gold, disponibilidad y readiness.
2027 permanece bloqueado sin calendario oficial. Las 12 h de la metodología
no fechan primera publicación; publicación y rezago siguen nulos. Esta prueba
no acredita otros productos, ronda completa ni activación.
