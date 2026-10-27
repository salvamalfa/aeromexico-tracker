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

La comprobación física de actualidad admite AICM y OMA mediante sus índices
oficiales, además de AIFA. Vincular `availability` al recibo de colección que
contiene el índice y el PDF/XLSX exacto usado por el candidato. Exige HTTP200,
manifiesto, sidecars, hashes y captura en la misma fecha local de la ronda;
después reproduce el producto completo sin red. Un enlace sin PDF descargable,
un desafío HTTP202, una edición ambigua o un título nuevo bloquean el vínculo.
El 27/oct el índice OMA anuncia septiembre pero su PDF devolvió HTTP404; el
candidato retenido de julio no sustituye ese original ni acredita actualidad.

## Adquisición por producto

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product oma_traffic
```

Consultar cada producto de esta familia:

- `oma_traffic` — descubrimiento nuevo y adaptador offline de reporte retenido. Entrada canónica: `constant:src.ingest.airports.groups:OMA_IR_URL`. Formato: HTML → PDF.
- `aicm_traffic` — descubrimiento y certificador integral offline del PDF retenido. Entrada canónica: `constant:src.ingest.airports.groups:AICM_STATS_INDEX`. Formato: HTML → PDF.
- `aicm_slots` — adaptador offline de asignaciones verano 2026; nuevas ediciones requieren revisión. Entrada canónica: `constant:src.ingest.airports.groups:AICM_STATS_INDEX`. Formato: PDF estacional de slots.
- `aifa_traffic` — descubrimiento y certificador offline con fechas, etiquetas y unidades obligatorias; el julio retenido falla el control de fechas. Entrada canónica: `constant:src.ingest.airports.groups:AIFA_STATS_INDEX`. Formato: HTML → XLSX.

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


### Reportes y slots retenidos

Aplicar el [flujo común](../source-updates-common.md#originales-retenidos-y-lote-offline).
OMA exige `pdf`. El reporte julio retenido produce 168 observaciones y 80
reconciliaciones: 13 aeropuertos/grupo, tres mercados y mensual/acumulado con
comparativo anual. Pasajeros terminales incluyen comercial, chárter y aviación
general; excluyen tránsito. No atribuirlos a una aerolínea ni acreditar
septiembre desde ese original o desde el índice cuyo enlace falló.

Slots AICM exige `pdf`; el formato revisado es verano 2026, 61 páginas y 2.836
asignaciones únicas reconciliadas por fecha/frecuencia/conteo. Conservar temporada
completa, horario UTC y designador AM sin inferir operador. La fecha interna
05/02/2026 12:13 no prueba publicación de esa versión. No son vuelos realizados
ni un total trimestral/mensual; tampoco se resuelven solapamientos como hechos
operativos. Un conteo, fecha o edición distinto requiere revisión del adaptador.

### Certificación integral AICM/AIFA

`python -m src.source_updates.government_candidate` conserva el protocolo de
originales, hashes, corte y revisión. Roles: `pdf` para `aicm_traffic` y
`workbook` para `aifa_traffic`. `retain` exige `--source-root`, `--original
<rol>=<ruta-exacta-en-manifiesto>` y `--workspace` nuevo. `certify` exige
`--product`, `--workspace`, `--period YYYYMmm`, `--as-of` con zona y
`--retention <id>`. Mostrar primero `--dry-run`, construir con `--execute`
y reproducir con `--check`; nunca sobreescribir un candidato.

El recibo `government-<producto>-<mes>.json` comprueba observaciones nativas,
`airport_traffic`, `fact_airport_traffic`, dimensiones y puente físico. Mantiene
mensual, comparativo y acumulado separados; revisiones usan el grano nativo
con aeropuerto, métrica, mercado y periodo, más unidad y alcance de aviación.
`--baseline baselines/<copia.parquet>` exige la misma identidad aeroportuaria;
sin copia explícita no se afirma haber comparado revisiones. `retained_round`
despacha este adaptador en ejecución y replay; la ronda usa `adapter=government`.

AICM exige catorce páginas, columnas de mercado, fechas y unidades físicas,
meses completos y reconciliación acumulada/anual. Los pasajeros son comerciales;
las operaciones incluyen comercial y general, y la carga está en toneladas.
AIFA separa comercial/general/carga, comprueba exclusión de aerolíneas mixtas
antes de sumar operaciones y convierte kg a toneladas solo en la proyección.
Rechazar fechas internas anteriores al cierre del mes o posteriores a la
captura local, datos ausentes, plantillas futuras con observaciones o cambios
de formato. El julio AIFA retenido declara 11 Jul frente al cierre 31 Jul:
queda bloqueado, sin Silver/Gold ni sustitución por cero. Una prueba sintética
positiva no resuelve esa contradicción de la fuente oficial.

Los originales no acreditan última disponibilidad, primera publicación ni
activación; conservar esos límites en la ronda global y en la entrega.

La edición oficial de septiembre 2026 tiene operaciones de carga desplazadas
dos filas y notas de revisión de junio/agosto. El lector revisado comprueba
las fórmulas y sus valores almacenados, las notas literales y los marcadores.
Conserva fechas internas de 16/oct y actualización propia de Carga desconocida:
su C5 contiene el periodo, no una fecha. No interpreta las notas como deltas
firmados ni modifica julio. Otra disposición requiere adaptación y pruebas.

Para acreditar disponibilidad en una ronda, se admite el vínculo `availability`
descrito en el protocolo común: índice oficial capturado, colección completa
y el mismo XLSX usado por el candidato. La captura debe pertenecer a la fecha
local de la ronda; retener ese original para otra fecha no acredita actualidad.
La primera publicación y su rezago siguen desconocidos.

### Certificación integral GAP/ASUR

El plan `--family airports` incluye ambos productos SEC sin trasladar los
reportes financieros SEC a esta familia. La institución sigue siendo SEC.

`python -m src.source_updates.airport_group_candidate` usa el mismo protocolo
`retain`/`certify --dry-run|--execute|--check` con rol `html`. Seleccionar un
original SEC del CIK GAP `1347557` o ASUR `1123452`; no usar el mes del formulario
6-K como mes del tráfico. `--period YYYYMmm` identifica el mes cerrado dentro
del contenido; se exigen sus comparativos y acumulados separados. El lector
revisado se ha contrastado con originales julio 2026, no con toda edición futura.
La ronda usa `adapter=airport_group`; `retained_round` lo despacha sin activar.

GAP exige los tres títulos de mercados y la unidad miles con un decimal,
catorce aeropuertos (doce mexicanos y dos jamaicanos), total mundial y nota
CBX. CBX ya pertenece a internacional Tijuana y no se suma otra vez. Cada
celda redondeada tiene cota de 50 pasajeros; se comprueba el límite matemático
de redondeo de las sumas y no se ajustan cifras para forzar igualdad. México
se calcula sumando los doce aeropuertos: cota de 600 pasajeros por mercado.
Mantener condición preliminar. Gold conserva los números convertidos por mil;
Silver y cada linaje aclaran precisión, cálculo y alcance. No son conteos exactos.

ASUR exige el resumen por país y los nueve aeropuertos mexicanos con mercados,
igualdad entera exacta y exclusión de tránsito/aviación general declarada solo
para México/Colombia. Puerto Rico, Colombia y total mundial quedan en evidencia
nativa separada; las dos tablas Gold estándar contienen únicamente México.
Carga y operaciones ausentes siguen nulas. No atribuir tráfico a una aerolínea.

El resultado incluye nueve tablas: nativa y `airport_traffic` Silver, hechos
Gold por aeropuerto/grupo, dimensiones aeropuerto/grupo/periodo, artefactos y
puente físico. Revisiones comparan grano nativo, unidades, precisión, país,
definición, preliminar y estado reportado/calculado; `--baseline` exige copia
nativa explícita del mismo grupo bajo `baselines/`. Sin ella no hay comparación.
La fecha declarada del reporte no acredita primera publicación ni frescura
actual. No publica, reemplaza Gold público ni habilita un calendario.

Para GAP julio existe un vínculo de descubrimiento **histórico**, separado de
una colección nueva: `availability` declara `source_scope=gap_sec_submissions_snapshot_v1`,
`historical=true`, `snapshot_day=2026-08-20`, `workspace`, `submissions` y
`filings`. Cada accession declara su `index` y mapa `documents` con las rutas
Bronze exactas. Se requieren el 6-K utilizado y todos los posteriores del
snapshot revisado; un anexo o edición desconocido bloquea. Se verifican los
cinco originales, manifiestos, sidecars, orden de captura y aporte nativo.
Los contenedores SEC listados pero no descargados permanecen explícitos; no
se afirma haberlos leído. El corte real de readiness debe ser exactamente
`2026-08-20T18:20:00-06:00` en México. No reutilizar ese expediente como disponibilidad de octubre o
como tráfico de septiembre; no fabricar un `run_id` ni renovar fechas.
