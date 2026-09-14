# Estimador de pasajeros por ruta y aerolínea

AFAC publica dos marginales del mismo cubo y nunca la celda. Este módulo
reconstruye la celda ajustando una matriz semilla de oferta a ambas marginales,
y **mide** su exactitud contra un mercado donde la respuesta correcta sí es
pública.

Contexto y evidencia de que el cubo existe: [`pasajeros-por-ruta-y-aerolinea.md`](pasajeros-por-ruta-y-aerolinea.md).

- Código: `src/analytics/route_carrier.py`
- Pruebas: `tests/test_route_carrier_ipf.py`
- Ejecutar la medición: `uv run python -m src.analytics.route_carrier`

## Qué insumos ya tenemos

| Insumo | Dónde vive | Papel en el estimador |
|---|---|---|
| Pasajeros por ruta y mes (nacional regular) | `data/reference/afac_od_nacional_regular.csv` | **Marginal de fila.** 10,051 filas, 17 meses (2024M01–2025M03, 2026M01–2026M02) |
| Pasajeros por aerolínea y mes (nacional regular) | `data/reference/afac_carrier_domestic.csv` | **Marginal de columna.** Los mismos 17 meses |
| Ciudad AFAC ↔ código IATA | `data/reference/afac_city_iata_crosswalk.csv` | Traduce la semilla al vocabulario de las marginales. 58 ciudades, verificadas contra `dim_airport` |
| Nombre AFAC ↔ `carrier_key` | `data/reference/afac_carrier_crosswalk.csv` | Alinea las aerolíneas de la semilla con las de la marginal |
| Vuelos por ruta y mes | mismo CSV de rutas, columna `vuelos` | Control de calidad de la semilla, no insumo del ajuste |
| T-100 por ruta, aerolínea y mes | `data/gold/fact_route_traffic.parquet` | **Arnés de validación.** Verdad publicada para medir el error |
| Identidades de aerolínea | `data/gold/dim_carrier.parquet`, `config/carrier_crosswalk.csv` | Resolución de entidades |

Falta **una sola cosa**: la semilla, es decir vuelos o asientos por aerolínea ×
ruta × mes en el mercado nacional. Es el único insumo que no es público en
México y hay que traerlo de fuera (ADS-B, itinerarios comerciales o un
proveedor). Todo lo demás ya está en el repositorio.

### Por qué los vuelos por ruta no entran al ajuste

Es la sorpresa del método. El IPF es invariante a escalar una fila o una
columna completa de la semilla, así que:

- el **calibre medio** de cada aerolínea (escalado de columna) se cancela — por
  eso contar vuelos rinde casi igual que conocer asientos;
- la **cobertura incompleta** de una ruta (escalado de fila) se cancela — por
  eso una fuente ADS-B que pierda vuelos no rompe el resultado, mientras los
  pierda parejo entre aerolíneas.

Conocer los vuelos totales de la ruta por AFAC no añade información al ajuste,
porque el ajuste ya fuerza la fila al total de pasajeros. Sirve para otra cosa,
que es igual de importante: **auditar la semilla**. Si los vuelos de la semilla
en una ruta se apartan de los de AFAC más allá de una tolerancia, es señal de
cobertura desigual entre operadores, que es justo el único sesgo que el método
no absorbe. También delata rutas de carga con muchos vuelos y casi cero
pasajeros, que deben excluirse.

## El método

1. Semilla `S[ruta, aerolínea]` con la oferta del mes (vuelos o asientos).
2. Marginal de fila: pasajeros por ruta de AFAC.
3. Marginal de columna: pasajeros por aerolínea de AFAC.
4. Ajuste iterativo proporcional hasta que ambas marginales cuadren.

Propiedades que importan en producción:

- Los ceros de la semilla son **estructurales**: a una aerolínea que no opera
  una ruta jamás se le asignan pasajeros.
- Las rutas de un solo operador salen **exactas** por construcción y se marcan
  con `is_exact`.
- Las dos marginales casi siempre suman igual —15 de 17 meses cuadran exacto—
  pero cuando no, el
  módulo reescala la marginal de columna al total de filas y **reporta** el
  factor en `column_scale` en vez de esconderlo.
- Si una marginal exige pasajeros donde la semilla no ofrece nada, se levanta
  `InfeasibleMarginsError` en lugar de repartir a ciegas.
- `estimate_route_carrier` devuelve la estimación **y** un cuadro de
  diagnóstico. Una estimación cuyo ajuste no convergió no debe leerse como
  número.

## Exactitud medida

No es una afirmación, es una medición. Se esconde el desglose por aerolínea del
T-100, se derivan las dos marginales que AFAC publicaría, se reconstruye el
reparto y se compara contra la verdad. Rutas México–EE. UU. competidas, 12 meses
de 2025, error ponderado por tamaño de ruta:

| Semilla | Error en participación | Error en pasajeros |
|---|---:|---:|
| Asientos por ruta | 1.40 pp | 4.21 % |
| Solo conteo de vuelos | 1.98 pp | 5.96 % |
| Solo presencia (0/1, sin frecuencias) | 13.04 pp | 39.38 % |
| Participación nacional de cada aerolínea | 100+ pp | 153 % |

Las dos últimas filas son las que deciden el diseño.

**La participación nacional no sirve como semilla.** No es una cuestión de
calidad: es *matemáticamente idéntica* a una semilla de puros unos, porque el
ajuste cancela cualquier escalado de columna. Ya está en el modelo, como
marginal de columna; usarla también de semilla es darle la misma información dos
veces. Al intentarlo, el 75 % de los pasajeros termina asignado a rutas que la
aerolínea no vuela.

**Saber solo qué rutas vuela cada aerolínea tampoco alcanza.** Una semilla de
presencia, sin frecuencias, deja 13 puntos porcentuales de error. Es decir, los
mapas de rutas públicos y las tablas de destinos por aeropuerto **no** bastan:
hay que saber *cuántos* vuelos, no solo *si* vuela.

Por la misma razón, los vuelos por ruta que AFAC sí publica no mejoran el ajuste:
encadenar un IPF sobre vuelos y usar su salida como semilla produce exactamente
el mismo resultado, porque el IPF solo aplica escalados de fila y columna y el
segundo ajuste los vuelve a cancelar.

El reparto simple por asientos, sin ajustar a la marginal de aerolínea, queda
peor: la marginal por aerolínea es lo que absorbe la diferencia sistemática de
ocupación entre bajo costo y servicio completo. Hay una prueba que lo fija.

Las rutas monopólicas se excluyen del cálculo del error porque salen exactas y
inflarían el promedio. Sobre el mapa completo, el error mezclado es menor.

### Dos salvedades

El banco de pruebas es **transfronterizo**, donde compiten aerolíneas de red
estadounidenses con perfiles de ocupación más dispares que los tres operadores
nacionales. Es razonable esperar que el doméstico salga mejor, pero **eso es un
supuesto, no una medición**. Convertirlo en medición requiere un trimestre de
verdad doméstica, vía solicitud de transparencia.

El residuo que queda es la desviación de la ocupación de cada aerolínea en esa
ruta concreta respecto de su promedio nacional. Es irreducible sin datos de
ocupación por ruta.

## Operación

Corre el arnés **cada mes**, no una sola vez. Publica las cifras nacionales con
la barra de error medida ese mismo mes, no con una afirmada una vez. El T-100
que ya se ingiere sirve de termómetro permanente y gratuito.

Etiqueta siempre con `is_estimated`; no mezcles estimado y reportado en la misma
columna, igual que el proyecto ya separa reportado de derivado.

## Contrato de la semilla

`estimate_route_carrier` espera un `DataFrame` con
`period_id, route_key, carrier_key, weight`.

`route_key` usa el vocabulario de AFAC, que nombra **ciudades**, no aeropuertos:
`MEXICO-CANCUN`, `SANTA LUCÍA-TIJUANA`, `DEL BAJIO-MONTERREY`. No hay que
construir esa traducción: `build_seed_from_flights` la aplica a partir del
crosswalk de 58 ciudades, y rechaza con `UnmappedSeedError` cualquier aeropuerto
que no reconozca, en vez de descartarlo en silencio.

Dos casos que el crosswalk resuelve y que es fácil equivocar: `MEXICO` es Benito
Juárez (`MEX`) y `SANTA LUCÍA` es el AIFA (`NLU`) — misma zona metropolitana,
aeropuertos distintos que AFAC nunca junta; y `DEL BAJIO` es `BJX`, en Silao, no
León ni Guanajuato capital.

`weight` puede ser vuelos o asientos; la unidad es indiferente por la
invariancia de escala. Itinerarios publicados sirven igual que vuelos operados:
las cancelaciones son escalado de fila y se cancelan.

### Fuente de semilla: decisión

La medición de arriba descarta las opciones gratuitas basadas en mapas de rutas.
La semilla **tiene que traer frecuencias**, así que la elección es entre un feed
ADS-B propio y un proveedor de itinerarios.

| Fuente | Costo | Veredicto |
|---|---|---|
| **AviationStack / Aviation Edge** | ~USD 50–200/mes | **Opción por defecto.** Itinerarios históricos con aerolínea, ruta y fecha; se agregan a frecuencias mensuales. Menor esfuerzo de integración |
| Cirium Diio / OAG | Alto | Si hay presupuesto. Trae asientos reales por ruta, que bajan el error de 5.96 % a 4.21 % |
| OpenSky Network | Gratis, uso no comercial | ADS-B histórico. Requiere credenciales OAuth2 desde 2025; la cobertura desigual es tolerable por la invariancia de fila. Viable pero con más trabajo de limpieza de callsigns |
| Mapas de rutas, Wikipedia, tableros de aeropuerto | Gratis | **Descartado.** Dan presencia, no frecuencia: 13 pp de error |

Cualquiera de las tres primeras entrega una tabla
`period_id, origin_iata, dest_iata, carrier_key, flights`, que es justo lo que
`build_seed_from_flights` consume. El adaptador de cada proveedor es lo único
específico; el resto de la tubería no cambia.

## La semilla tiene que estar completa

Es el error más fácil de cometer y el más difícil de detectar a ojo. La marginal
de columna es el total **nacional** de cada aerolínea, así que una semilla que
solo cubra parte de su red le exige a esas pocas rutas más pasajeros de los que
llevan. El ajuste no falla: converge, respeta todos los totales por ruta y
devuelve números de aspecto razonable — pero el reparto entre aerolíneas es
basura.

El delator es `column_scale` en el cuadro de diagnóstico. Es el factor por el que
hubo que reescalar la marginal de aerolínea para cuadrar los totales; con una
semilla completa vale prácticamente 1. En la prueba con una semilla de tres rutas
vale **0.037**, y el resultado pone a Volaris por encima de Aeroméxico en
México–Cancún, cosa que no ocurre.

Regla de operación: si `column_scale` se aparta de 1 más de unos pocos puntos, la
semilla está incompleta y el resultado no se publica.
