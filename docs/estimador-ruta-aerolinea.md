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
| Pasajeros por ruta y mes (nacional regular) | `data/reference/afac_od_nacional_regular_2025q1.csv` | **Marginal de fila.** 527 pares dirigidos, 2025Q1 |
| Pasajeros por aerolínea y mes (nacional regular) | `data/reference/afac_carrier_domestic_2025q1.csv` | **Marginal de columna.** 8 permisionarias, 2025Q1 |
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
- Las dos marginales no suman igual (46 pasajeros de diferencia en 2025Q1); el
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

`route_key` debe usar el vocabulario de AFAC, que nombra **ciudades**, no
aeropuertos: `MEXICO-CANCUN`, `SANTA LUCÍA-TIJUANA`, `DEL BAJIO-MONTERREY`. Un
adaptador de semilla tiene que traducir de códigos IATA a ese vocabulario; es
trabajo pendiente y no trivial, porque `MEXICO` y `SANTA LUCÍA` son aeropuertos
distintos de la misma zona metropolitana.

`weight` puede ser vuelos o asientos; la unidad es indiferente por la
invariancia de escala. Itinerarios publicados sirven igual que vuelos operados:
las cancelaciones son escalado de fila y se cancelan.

### Candidatos a fuente de semilla

| Fuente | Costo | Nota |
|---|---|---|
| OpenSky Network | Gratis, uso no comercial | ADS-B histórico; callsign → aerolínea. Cobertura desigual en México, tolerable por la invariancia de fila |
| AviationStack / Aviation Edge | ~USD 50–200/mes | Itinerarios históricos; la vía de menor esfuerzo |
| Cirium Diio / OAG | Alto | Mejor calidad; incluye asientos reales por ruta, que bajan el error de 5.96 % a 4.21 % |
