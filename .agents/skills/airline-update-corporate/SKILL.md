---
name: airline-update-corporate
description: "Actualizar candidatos de la familia fuentes corporativas y regulatorias de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Fuentes corporativas y regulatorias

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `corporate`. Alcance: SEC/IR/BMV: Aeroméxico, Volaris, Viva, Delta y Ryanair; GAP/ASUR se separan como tráfico aeroportuario.

Revalidar catálogos current y seleccionar anexos reales. No tratar llamadas o anuncios como estados financieros. Preservar moneda, escala, trimestre/acumulado/TTM, instante/duración, preliminar/auditado e IFRS/US-GAAP. Los parsers IR heredados de Aeroméxico son históricos; el descargador Viva termina en 2026Q2. Capturar un documento nuevo no demuestra que esos parsers lo incorporen. Para SEC usar importación manual con URL y hash. No ejecutar la ingesta heredada de peers como actualizador genérico.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family corporate
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.peer_discovery,parse.sec,parse.peers,parse.aeromexico_ir,parse.aeromexico_ir_financial.
BMV: `recipe --product bmv_xbrl --output selection --catalog-file <html> --period <YYYYQn> --ticker AERO` selecciona paquetes publicados reales. La selección candidata admite solo trimestres; rechaza años antes de leer el catálogo o preparar una captura porque no hay comprobador anual. Los paquetes anuales retenidos se conservan y pueden reproducirse offline, sin certificar un periodo anual nuevo. `parse.bmv` verifica hashes, límites/rutas del ZIP, registra un único JSON offline y acota el índice. Une catálogos preservados para no perder paquetes anteriores. No usa fragmentos URL como descargas; la ausencia de Q3 no se sustituye por Q2.

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

## Adquisición por producto

Las capturas SEC corporativas usan `source_system=sec`; `sec_edgar` y
`sec_filing` son alias de otras capas o productos y no satisfacen estos parsers.
Seleccionar `parse.peer_discovery` antes de `parse.sec` o `parse.peers`, con el
paquete de catálogos y documentos que esos pasos requieren. El tráfico GAP/ASUR
usa su contrato aeroportuario separado. `recipe` muestra los alias Bronze por
producto; los controles Silver mantienen los alias de procedencia del catálogo.

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product am_financials
```

Consultar cada producto de esta familia:

- `am_financials` — candidatos retenidos Q2 PDF y Q3 HTML IR revisado; otras ediciones requieren adaptación. Entrada canónica: `catalogue:aeromexico_ir`. Formato: HTML/PDF oficiales.
- `am_traffic_ir` — adaptador mensual candidato dedicado. Entrada canónica: `url:https://ir.aeromexico.com/news-events/traffic-reports`. Formato: índice HTML → PDF inglés seleccionado o 6-K HTML oficial con atribución independiente revisada.
- `am_sec` — selección/importación manual. Entrada canónica: `sec:AEROMEXICO`. Formato: JSON submissions/companyfacts → index.json → anexos HTML.
- `volaris_sec` — selección/importación manual. Entrada canónica: `sec:VOLARIS`. Formato: JSON → anexos HTML.
- `delta_sec` — selección/importación manual. Entrada canónica: `sec:DELTA`. Formato: JSON → 10-Q/10-K/anexos.
- `ryanair_sec` — adaptador retenido acotado de FY2026; otras ediciones con selección/importación manual. Entrada canónica: `sec:RYANAIR`. Formato: JSON → 20-F/6-K/anexos.
- `gap_traffic` — selección/importación manual. Entrada canónica: `sec_group:GAP`. Formato: JSON SEC → anexo HTML.
- `asur_traffic` — selección/importación manual. Entrada canónica: `sec_group:ASUR`. Formato: JSON SEC → anexo HTML.
- `bmv_xbrl` — solo descubrimiento. Entrada canónica: `constant:src.config:SOURCE_URLS:bmv_xbrl`. Formato: HTML → visor → ZIP con JSON.
- `viva_financials` — certificador retenido dedicado de 2T26, con 1T26 como soporte; otras ediciones con selección/importación manual. Entrada canónica: `url:https://www.bmv.com.mx/es/emisoras/eventosrelevantes/GVIVA-34292-CGEN_DEUD`. Formato: HTML → PDF InvestorCloud.
- `viva_traffic` — candidato mensual con formatos nativos separados. Entrada canónica: `url:https://www.bmv.com.mx/es/emisoras/eventosrelevantes/GVIVA-34292-CGEN_DEUD`. Septiembre 2026 BMV comprobado; histórico 2021 en kilómetros permanece separado.
- `ryanair_ir` — solo descubrimiento. Entrada canónica: `constant:src.ingest.peers.stage5:RYANAIR_KEY_STATS_URL`. Formato: HTML.

### Procedimiento verificable

1. Ejecutar `recipe --product <producto>` y leer su procedimiento, URL resuelta, formato y bloqueo.
2. Para un índice HTML admitido, emitir la selección con `recipe --product <producto> --output selection > tmp/seleccion.json`. Revisarla con `collect --selection tmp/seleccion.json --workspace tmp/source-updates/<lote> --dry-run`. Capturar solo dentro del alcance autorizado.
3. Leer los enlaces y el contexto del catálogo preservado. Elegir el documento real y comprobar su periodo dentro del contenido. No transformar una plantilla histórica en una URL futura. Para importación manual, colocar el original en `imports/` del candidato, calcular SHA-256 y declarar URL, entidad, periodo, formato y directorio que espera el parser.
4. Revalidar documentos/URLs seleccionados en la ronda. Conservar original y revisión por hash. Comparar filas contra una copia previa explícita; sin baseline, registrar que no se compararon revisiones.
5. Ejecutar solo el paso de construcción que el plan declare y cuyos insumos estén presentes. Aplicar `check` al producto, tabla, fuente, entidad y periodo solicitados; compartir institución no permite intercambiar productos.
6. Acreditar éxito solo en la capa comprobada: hash Bronze, contrato/grano/linaje Silver y controles Gold/meses/días/reconciliaciones que correspondan. Si no existe adaptador, terminar en captura o descubrimiento y declarar ese límite. No llenar faltantes ni activar/publicar.

Un 403, TLS, timeout o archivo inválido es un fallo de acceso/contenido; no prueba ausencia de publicación. Registrar pendiente y conservar el dato aceptado. Las fechas de publicación desconocidas siguen nulas.

## Candidato mensual IR de Aeroméxico

Seleccionar un mes cerrado mediante `recipe --product am_traffic_ir --output selection --catalog-file <indice-preservado.html> --period YYYYMmm`. `collect` captura el PDF seleccionado, o el 6-K HTML oficial acotado que se describe abajo. A continuación ejecutar la vista previa de `python -m src.source_updates.am_traffic_candidate --workspace <candidato> --period <mes> --as-of <corte-con-zona> --collection <id-del-recibo>`. `--execute` certifica el original preservado sin red; `--check` reconstruye y compara las siete salidas y el hash del recibo. Usar un candidato por mes, sin otros productos ni salidas previas.

Exigir título y entidad Grupo Aeroméxico, orden mes/acumulado y años actual/anterior, cuatro métricas y tres segmentos completos. No importar acumulados como mes. Conservar 12 cifras del mes y 12 comparativos del mismo mes del año anterior, con fecha de publicación dentro del documento. Pasajeros están en miles; ASM/RPM en millones de millas; ocupación en porcentaje. Los tres primeros incluyen itinerario/fletamento; ocupación es itinerario y no se calcula desde ese RPM/ASM. Conservar estado no auditado, unidad literal, token, extracto, página, captura y SHA-256. No equiparar no auditado con preliminar.

El candidato aislado `aeromexico_ir_monthly_metrics` reutiliza el contrato estructural de observaciones operativas y añade su dominio explícito IR; no es una presentación SEC ni se registra automáticamente como tabla del warehouse productivo. Gold aplica su contrato existente, dimensiones y puente exacto. Esta cadena dedicada no añade `parse.am_traffic_ir` al runner genérico, no suma trimestres ni activa reportes/tesis. La certificación se limita al formato y los meses realmente comprobados. Documentar cualquier cambio de formato y mantener el fallo cerrado.

### Descubrimiento y vínculo físico del tráfico IR

`recipe --product am_traffic_ir --output selection` emite el índice oficial.
Después de conservarlo, `--catalog-file <ruta-real.html> --period latest`
selecciona septiembre en la lista actual comprobada. El selector valida cada
artículo y cada enlace pertinente, su mes, entidad y ruta documental; no toma
la fecha del directorio de subida como publicación. Un diseño nuevo o dos
versiones incompatibles bloquean. El mes explícito histórico sigue disponible.

Para el vínculo actual, revalidar índice y PDF en **una colección**. Combinar
las selecciones devueltas por el CLI, sin escribir URLs a mano:

```python
import json
from pathlib import Path
index = json.loads(Path("tmp/am-index-selection.json").read_text())
pdf = json.loads(Path("tmp/am-pdf-selection.json").read_text())
Path("tmp/am-paired-selection.json").write_text(
    json.dumps({"version": 1, "items": index["items"] + pdf["items"]})
)
```

Aplicar `collect --selection tmp/am-paired-selection.json --workspace
<coleccion-nueva> --dry-run`; solo ejecutar con la adquisición autorizada y
sin reintentos prohibidos. Son dos llamadas base y cero pagadas. Conservar
originales/sidecars/manifiesto/recibo y copiar esa colección íntegra a un
candidato nuevo antes de certificar: mismo contenido, hashes y recibo, sin
inventar otra captura. No copiar Gold ni aceptaciones anteriores. El
certificador permite un PDF y, opcionalmente, su índice oficial; rechaza
productos extra, duplicados, cambios del recibo o fechas inconsistentes.
La fecha impresa no puede ser posterior a la captura.

Tras `--execute` y `--check`, `availability` de readiness identifica la colección
separada con `workspace`, `run_id`, `catalog_item` y `artifact_item` realmente
emitidos. Se cotejan el índice actual, el PDF nativo y la fecha local de la
ronda. `complete_month_certified=true` cubre las doce cifras mensuales del
reporte corporativo y sus doce comparativas; no certifica un censo de operadores,
trimestres ni otra aerolínea. Publicación inicial y hora desconocidas siguen
nulas. Un PDF retenido de otro día prueba historia, nunca actualidad del día.

### Alternativa oficial HTML mensual, septiembre 2026

El lector separado `am_traffic_html.py` admite el 6-K IR exacto
`https://ir.aeromexico.com/node/9131/html`, con producto `am_traffic_ir` y
entidad `am_traffic_ir_2026M09_6K`. Seleccionar ese original explícito y el
índice de tráfico en una colección pareada, dos GET base y cero pagados.
No reciclar la colección financiera ni reetiquetar su producto. El índice
anuncia septiembre; el cover del 6-K atribuye el comunicado del 6/oct al
Exhibit 99.4. Se extraen solo sus doce cifras mensuales y doce comparativas,
no el 99.1 financiero, julio/agosto ni acumulados. No afirmar enlace directo
desde el índice al HTML o equivalencia de bytes con el PDF.

Los comandos `am_traffic_candidate` y readiness conservan preview/execute/check.
Exigir glosario explícito de millas y ocupación itinerario. Estado preliminar
no declarado permanece nulo en nativo y `not_stated` en notas/recibo. El booleano
Gold existente «Fuente lo marca preliminar» es falso solo para esa pregunta;
no clasifica el reporte como definitivo. Otro mes, URL, caption, unidad o
flag desconocido bloquea. La prueba real del 27/oct dio 24 filas iguales en
valor/unidad/ámbito a las del PDF retenido, sin igualar bytes ni capturas.
Fecha documental y captura son conocidas; primera publicación/hora siguen nulas.

## Finanzas IR retenidas de Aeroméxico

Aplicar el [flujo común de retención](../source-updates-common.md#originales-retenidos-y-lote-offline)
con `am_financials`, rol `pdf` y periodo `2026Q2`. El adaptador dedicado
[`financials.py`](../../../src/source_updates/financials.py) verifica 13 páginas,
20 cifras del trimestre, encabezados y columnas trimestral/acumulado y
actual/comparativo, unicidad de cada fila y dos identidades contables. Cambios
de edición o formato se bloquean para revisión; Q3 usa el lector separado descrito abajo.

Conservar preliminar/no auditado y la precisión redondeada de los estados.
Importes en millones de USD, pasajeros en miles, ASM/RPM en millones de millas,
combustible en miles de litros y CASM sin combustible en centavos USD por ASM.
No renombrar ASM/CASM como ASK/CASK ni armonizar históricos automáticamente.
La fecha impresa 13 de julio de 2026 no prueba primera disponibilidad:
publicación inicial y rezago siguen nulos. El candidato conserva captura, SHA,
página, token y extracto. No modifica M11, parsers heredados, warehouse
productivo, elegibilidad, tesis ni aprobaciones.


Para `2026Q3` seleccionar solo rol `html` del 6-K oficial
`https://ir.aeromexico.com/node/9131/html`, alias `aeromexico_ir`, entidad de
selección `am_financials_2026Q3_6K`. No combinarlo con `pdf` ni usar el HTML
GlobeNewswire como alias IR. `financials_html.py` limita el contenido financiero
al Exhibit 99.1 atribuido por el cover; excluye tráfico 99.2–.4, nueve meses y
comparativos. Conserva las mismas veinte métricas y unidades. No auditado es
`true`; preliminar desconocido es nulo. No infiere hora ni primera publicación.

Tras retención/certificación/replay, `availability` usa la colección física
separada con `workspace`, `run_id`, `catalog_item` y `artifact_item`. El índice
actual anuncia un PDF y acredita el último trimestre; el 6-K HTML acredita por
su propio contenido emisor, trimestre y fecha. Son formatos oficiales distintos:
no afirmar enlace directo al HTML desde el índice ni equivalencia de bytes con
el PDF. Ambos deben estar capturados en el día local de la ronda y el HTML
exacto debe aportar las veinte filas del candidato. Una edición pertinente
ambigua, moneda/escala contradictoria o anexo equivocado bloquea; el 5 % no
corrige esos errores.

## Tráfico Viva: original BMV autorizado y formato nativo

El dueño autorizó únicamente añadir `bmv.com.mx` a `viva_ir.allowed_hosts` y
capturar el PDF oficial de septiembre de 2026. Se comprobó que el intento previo
no ejecutó HTTP antes de repetirlo: un GET, HTTP 200, 86.488 bytes y SHA-256
`b0acad4f5131220a58c7ee41f25af581d75ff1a7ec8756d3f65869f8f1d636c2`.
No se habilitó S3 ni se amplió otra política.

Para una URL oficial opaca usar `recipe --product viva_traffic --output selection
--source-url <PDF-oficial-real> --period <mes>`, sin `--catalog-file`. El enlace
seleccionado no demuestra el periodo: `collect` conserva el original y
`retained retain --product viva_traffic --original pdf=<ruta>` permite preparar
la cadena candidata, seguida de `retained certify` con `--execute` y `--check`.
La retención conserva la fecha real de la captura anterior; no vuelve a descargar.

El índice BMV actual sí contiene filas físicas de tráfico. Conservar su HTML
de `GVIVA-34292-CGEN_DEUD` y usar `recipe --product viva_traffic --output selection
--catalog-file <indice-BMV.html> --period latest` o el mes explícito. El selector
exige la identidad del emisor, título mensual y un único PDF de esa fila;
rechaza ZIP/visor XBRL, formatos nuevos y ediciones ambiguas. El reloj sin zona
de BMV no se convierte en primera publicación ni fecha de un reporte financiero.
El vínculo `availability` solo acredita actualidad si índice y PDF realmente
utilizados se capturaron en la fecha local de esa ronda, después de certificar
todo el producto. No acredita otras familias ni activa el calendario.

El lector actual produce 24 filas mensuales/comparativas: cuatro métricas por
tres segmentos (total/nacional/internacional) y septiembre 2026/2025. Pasajeros
reservados en miles, ASM/RPM en millones de millas y ocupación solo itinerario.
Mantener preliminar, el glosario reservado/no necesariamente transportado y
unidades por métrica. Comprobar encabezados, orden mensual/acumulado, suma de
segmentos con tolerancia del redondeo fuente y dominios. No recalcular ocupación
desde totales que incluyen chárter. El formato 2021M11 mantiene ASK/RPK en km.
Las fechas documentales y su rezago se conservan separados de publicación
inicial y rezago de publicación, que siguen nulos. Formatos distintos y meses
incorrectos bloquean antes de Gold; no se activa el candidato ni se publica.

## 20-F retenido de Ryanair

El comando `retained` admite `ryanair_sec`, roles `html`, `submissions` e
`index`, para la presentación `0001104659-26-076131`. Usar `--period 2026Q2`
como periodo de revisión. Las seis filas siguen siendo **FY2026, del 1 de abril
de 2025 al 31 de marzo de 2026**, o instantes de balance de ese cierre. No son
cifras trimestrales. El lector inline XBRL comprueba CIK, entidad, DEI, contextos
consolidados sin dimensiones, taxonomía IFRS, EUR, escala y precisión. Comprueba
los 14 hechos repetidos del documento y la identidad del balance; un conflicto
se bloquea. Conserva cada identificador y la escala original.

La presentación SEC fue el 22 de junio, con aceptación a las 12:47:18 UTC:
83 días desde el cierre fiscal. Eso es rezago de presentación SEC, no primera
publicación IR. Esta última y su rezago permanecen desconocidos. No sustituir
un 20-F por la página IR mensual: el comprobador heredado no tiene filas SEC
Ryanair para ese trimestre. La copia retenida de companyfacts llega a FY2025 y
no sustituye los hechos del 20-F FY2026. No modificar el parser histórico ni
incorporar estas filas automáticamente al warehouse o a comparaciones.

## Dossier Volaris SEC retenido

Usar `python -m src.source_updates.carrier_source_candidate`, separado de
`retained certify` y del build heredado. `retain --product volaris_sec` exige
`--source-root <Bronze> --workspace <nuevo>` y cuatro `--original rol=ruta`:
`html` (anexo), `primary` (6-K), `submissions` e `index`. Primero vista previa;
`--execute` conserva hashes, sidecars y capturas. `certify --product volaris_sec
--workspace <candidato> --period 2026Q2 --as-of <corte-con-zona> --retention <id>`
produce la vista previa; `--execute` valida antes de escribir; `--check`
reconstruye sin red y compara cada salida/recibo sin cambiarlos.

El formato revisado es exclusivamente el accession `0001292814-26-003836`:
11 tablas y sus comparativos completos, H1 separado de Q2, balances/aviones
como instantes, USD con escala, pasajeros reservados y ASM/RPM en millas.
No usarlo como tráfico mensual ni presentación de otro trimestre. Preservar
no auditado/auditado y los guiones desconocidos; no resolverlos como cero.
Gold propio aplica solo escala explícita, omite resúmenes duplicados y contexto
cambiario del emisor, y conserva padres/artefactos exactos. Nada se incorpora
al warehouse productivo.

La política autorizada el 27/oct conserva el primer control por intervalos de
redondeo. Si CASM derivado no solapa, admite hasta 5 % relativo a la cifra
oficial absoluta, solo con la misma entidad, periodo, unidades, definición,
cobertura y originales. CASM H1 2025 conserva 7,97; `1403/17622×100` deriva
7,96163886…, diferencia relativa de 0,1049076472 %. Se muestra como advertencia,
sin modificar la cifra oficial ni omitir el comparativo. Una referencia cero
o menor/igual a una unidad de su resolución impresa no recibe porcentaje
automático. Más del 5 % o entradas incompatibles bloquean.

Los recibos propagan `numeric_warnings`, `numeric_warning_count`,
`numeric_check_status=passed_with_warnings` y `numeric_policy_id`; el estado
compatible sigue `checks_passed`. Cada advertencia conserva valores, diferencia
absoluta/relativa, referencia, unidad, definición y fuentes/locators. No aplicar
la tolerancia a copias de cifras oficiales, integridad, ausencias o periodos.
Fecha impresa y aceptación SEC no acreditan primera publicación o disponibilidad
actual; esos campos siguen desconocidos. Ver evidencia en la guía canónica.

## Finanzas Viva retenidas: tablas y comparación entre ediciones

Usar `python -m src.source_updates.viva_financial_candidate retain` con
`--product viva_financials`, roles `--original pdf=<PDF-2T26>` y
`--original prior_quarter=<PDF-1T26>`, `--source-root <Bronze>` y
`--workspace tmp/source-updates/<candidato-nuevo>`. Revisar sin `--execute`
antes de retener los originales. Luego usar `certify --product viva_financials
--period 2026Q2 --workspace <candidato> --as-of <corte-con-zona>
--retention <id>`: sin modo muestra el plan; `--execute` certifica sin red y
`--check` reconstruye y compara sin modificar archivos. El lote `retained_round`
y el verificador `readiness` usan el adaptador `viva_financial`.

El contrato acota las dos ediciones revisadas. Conserva todas las filas de las
tablas de indicadores, resultados, balances, flujos, deuda y flota, con columna,
página, token, escala y procedencia. Gold solo proyecta lo reportado en la
edición 2T26; separa trimestre, semestre e instantes, incluyendo comparativos.
El 1T26 aporta exclusivamente diagnóstico. No convertir H1−Q2 en un nuevo 1T26.
Registrar diferencias entre ediciones y exigir revisión antes de armonizar
históricos; no inferir su causa ni sobrescribir cifras anteriores.

USD en miles/millones se escala explícitamente a USD; ASM/RPM permanecen en
millas y CASM en centavos por asiento-milla. Los pasajeros son reservados,
independientemente de si volaron; ocupación es itinerario, con denominador
distinto de los totales. Flota excluye ACMI. Las filas de contexto de tipo de
cambio y jet fuel se conservan en Silver y se excluyen de Gold. No invertir la
etiqueta cambiaria ambigua ni sustituir fuentes macro. Mantener preliminar y
no auditado solo donde lo declara el documento; desconocido sigue nulo.

Las identidades y ratios aplicables usan intervalos de precisión publicada;
un desajuste propio bloquea antes de escribir Silver/Gold. Cada cifra Gold
tiene un padre nativo de la edición correcta y su artefacto físico verificado.
La retención no prueba disponibilidad reciente, fecha inicial de publicación,
aprobación de datos ni preparación completa del calendario.
