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
| Pasajeros por ruta y mes (nacional regular) | `data/reference/afac_od_nacional_regular.csv` | **Marginal de fila.** 13,224 filas, 22 meses (2024M01–2025M03, 2026M01–2026M07) |
| Pasajeros por aerolínea y mes (nacional regular) | `data/reference/afac_carrier_domestic.csv` | **Marginal de columna.** Los mismos 22 meses, de la base larga de DATATUR |
| Vuelos por aerolínea y mes (nacional regular) | `data/reference/afac_carrier_flights_domestic.csv` | Contraste exacto para la prueba de aceptación. 19 meses, de la hoja `VLOSREG` del resumen operacional |
| Ciudad AFAC ↔ código IATA | `data/reference/afac_city_iata_crosswalk.csv` | Traduce la semilla al vocabulario de las marginales. 58 ciudades, verificadas contra `dim_airport` |
| Nombre AFAC ↔ `carrier_key` | `data/reference/afac_carrier_crosswalk.csv` | Alinea las aerolíneas de la semilla con las de la marginal |
| Vuelos por ruta y mes | mismo CSV de rutas, columna `vuelos` | Control de calidad de la semilla, no insumo del ajuste |
| T-100 por ruta, aerolínea y mes | `data/gold/fact_route_traffic.parquet` | **Arnés de validación.** Verdad publicada para medir el error |
| Identidades de aerolínea | `data/gold/dim_carrier.parquet`, `config/carrier_crosswalk.csv` | Resolución de entidades |

Los vuelos por aerolínea no entran al ajuste —son una marginal de la tabla de
vuelos, no de la de pasajeros— pero convierten la prueba de aceptación en
aritmética. Un detalle que confunde si no se anticipa: los vuelos por ruta
superan a los vuelos por aerolínea en un 1.1 % constante, y ese hueco son las
cargueras, que vuelan regular nacional y llevan cero pasajeros. Por eso los
pasajeros cuadran exacto y los vuelos no.

Falta **una sola cosa**: la semilla, es decir vuelos o asientos por aerolínea ×
ruta × mes en el mercado nacional. Es el único insumo que no es público en
México y hay que traerlo de fuera (ADS-B, itinerarios comerciales o un
proveedor). Todo lo demás ya está en el repositorio.

### El hueco que queda: abril a diciembre de 2025

Las marginales cubren 22 meses, pero **faltan 2025M04 a 2025M12** en el lado de
rutas. La marginal de aerolínea sí los tiene: la base larga de DATATUR
(`DB_AFAC.xlsx`) llega hasta julio de 2026 y no pasa por el bloqueo de gob.mx.

El lado de rutas depende de los workbooks `sase-*.xlsx`, que son acumulados
anuales: la edición de diciembre de un año trae los doce meses. El de 2024 y el
de julio de 2026 se consiguieron; el de diciembre de 2025 no.

Por qué no: gob.mx sirve un reto antiautomatización de F5 para todo `.xlsx` —
devuelve 200 con 1,936 bytes de HTML para cualquier URL, válida o inventada, así
que ni siquiera se puede confirmar la ruta del archivo probándola. El Internet
Archive resolvió los otros dos, pero no tiene copia de este y Save Page Now
ahora exige una cuenta.

**Cómo cerrarlo en un minuto, desde un navegador normal:** entrar a la
[página de estadísticas de AFAC](https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404)
y bajar el acumulado de diciembre de 2025. Un navegador real resuelve el reto
solo. Con ese archivo en disco:

```python
from src.ingest.afac.margins import build
routes, carriers, rec = build(
    {2024: Path("sase2024.xlsx"),
     2025: Path("sase-diciembre-2025.xlsx"),   # el que falta
     2026: Path("sase-julio-2026.xlsx")},
    Path("DB_AFAC.xlsx"),
)
```

El módulo reescribe las dos marginales y devuelve la reconciliación mes a mes.
No hay que tocar nada más.

Nota sobre prioridad: el archivo de AeroDataBox solo llega 365 días atrás, así
que los meses estimables hoy son de septiembre de 2025 en adelante. De ese
rango ya están los siete de 2026; el hueco de 2025 pesa sobre cuatro meses
(septiembre a diciembre), no sobre nueve.

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
- Las dos marginales casi siempre suman igual —20 de 22 meses cuadran exacto—
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

## El día que haya cuota: un solo comando

Todo lo anterior está cableado detrás de una orden. Pega la llave en `.env` como
`RAPIDAPI_KEY` y corre:

```bash
uv run python -m src.ingest.aerodatabox 2026M07 --dry-run   # cuánto va a costar
uv run python -m src.ingest.aerodatabox 2026M07             # el mes completo
```

Lo que hace, en orden, y por qué ese orden:

1. Barre los 58 aeropuertos en ventanas de 12 horas y **cachea cada respuesta en
   disco**, así que una corrida interrumpida se reanuda sin volver a gastar
   unidades.
2. Arma la semilla y corre la **prueba de aceptación**.
3. Solo entonces ajusta. Si la prueba rechaza la semilla, **no ajusta**: sale con
   código 2 y explica por qué. Hay que pedir `--fit-rejected-seed` a propósito
   para forzarlo, y eso es para diagnóstico, nunca para publicar.

Banderas útiles: `--budget N` frena antes de pasarse de N unidades, y `--days N`
muestrea N días en vez del mes entero. El muestreo no toma días seguidos ni los
espacia a ojo: avanza con un paso coprimo con siete, de modo que recorre todos
los días de la semana. Importa porque la mezcla de aerolíneas se mueve con el
itinerario semanal, y sobrerrepresentar un día sesga la semilla.

| Alcance | Unidades |
|---|---:|
| Mes completo (31 días) | 7,192 |
| Muestra de una semana | 1,624 |

Cada día muestreado se pondera por cuántas veces cae su día de la semana en el
mes. Julio de 2026 tiene cinco miércoles y cuatro domingos; una semana que los
cuente igual lee el mercado a través de los días que le tocaron, y como la mezcla
de aerolíneas se mueve con el itinerario semanal, eso sesga a todas. Con la
ponderación los pesos suman exactamente los días del mes, así que la semana
**escala** al mes en vez de solo parecerse. Un mes completo da peso uno a cada
día, que es la identidad.

### Qué plan comprar

| Plan | Precio | Unidades | USD por 1,000 | ¿Alcanza? |
|---|---:|---:|---:|---|
| Pro (RapidAPI) | 7.50 | 5,000 | 1.50 | No: ni un mes completo |
| **Starter (directo)** | **19** | **40,000** | **0.47** | Sí, con holgura |
| Ultra (RapidAPI) | 37.50 | 50,000 | 0.75 | Sí |

El plan de trabajo son 16,936 unidades: un mes completo para validar el muestreo
semanal, más seis semanas. Starter es la opción obvia —la mitad de costo por
unidad que Ultra— y el adaptador habla con las dos APIs, así que la elección no
obliga a tocar código. Se configura con `AERODATABOX_API_KEY` para los planes
directos o `RAPIDAPI_KEY` para los revendidos.

Una salvedad: las 2 unidades por llamada están medidas en RapidAPI, no en el plan
directo. Aunque allá costara el doble, 40,000 unidades siguen sobrando.

La salida queda en `data/silver/`: los vuelos crudos normalizados y, si la
prueba pasó, la estimación con `is_estimated = True`.

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

La medición descarta las opciones gratuitas basadas en mapas de rutas, porque la
semilla **tiene que traer frecuencias**. Y un piloto con datos reales descartó
también la opción gratuita que parecía más prometedora.

Hay que separar dos familias, porque fallan por razones distintas. Los
**itinerarios publicados** son lo que la aerolínea programó: no dependen de que
haya un receptor en tierra, y las cancelaciones son escalado de fila, que el
ajuste cancela. Los **vuelos rastreados** (ADS-B) dependen de la densidad de
receptores, que en el centro y sureste de México es el problema.

| Fuente | Familia | Costo real | Prueba gratis | Veredicto |
|---|---|---|---|---|
| **AeroDataBox** | Itinerarios | **USD 7.50/mes** (plan Pro, 5,000 unidades) | **Sí: 400 unidades/mes, con histórico de ±365 días** | **Con esta se prueba.** Es la única cuyo tramo gratuito incluye lo que hace falta |
| Aviation Edge | Itinerarios | USD 7 el primer mes (30,000 llamadas), luego tarifa normal | Prueba de pago, no gratuita | Suplente si la calidad de AeroDataBox decepciona |
| AviationStack | Itinerarios | USD 49.99/mes el plan Basic | Sí, 100 llamadas/mes — **pero el plan gratuito excluye vuelos históricos, itinerarios y rutas de aerolínea** | Descartado para la prueba: lo gratuito no cubre nada de lo que se necesita |
| Cirium Diio / OAG | Itinerarios | Alto | No | Si hay presupuesto. Trae asientos reales, que bajan el error de 5.96 % a 4.21 % |
| adsb.lol, airplanes.live, ADSB Exchange | Rastreo | Gratis o bajo | Sí | Apuesta a que sus receptores cubran donde OpenSky no. Someterla a la prueba de aceptación antes de invertirle tiempo |
| OpenSky Network | Rastreo | Gratis | Sí | **Descartado por medición.** Ver abajo |
| Mapas de rutas, Wikipedia, OpenFlights, tableros de aeropuerto | Presencia | Gratis | — | **Descartado.** Dan presencia, no frecuencia: 13 pp de error |
| Boletines de AFAC y de AICM | — | Gratis | — | **Descartado por inspección.** AICM desagrega por terminal, no por aerolínea; la base de DATATUR es aerolínea × mes × región, sin ruta |

El costo real, medido contra la API y no leído del tarifario: **una llamada FIDS
cuesta 2 unidades, no 1**, y la ventana máxima es de **12 horas** hasta el plan
Ultra inclusive. El mercado nacional son 58 aeropuertos, y basta pedir
**salidas**, porque todo vuelo doméstico sale de un aeropuerto mexicano:

    58 aeropuertos × 30 días × 2 ventanas × 2 unidades = 6,960 unidades/mes

Eso descarta el plan Pro de USD 7.50 (5,000 unidades). El plan que cubre el
trabajo con holgura es el **Starter directo, USD 19/mes por 40,000 unidades**;
en RapidAPI el equivalente es Ultra a USD 37.50.

Una trampa que cuesta cuota: pedir una ventana de 24 horas **no devuelve error,
devuelve cero vuelos**. Y `withLeg=true` es obligatorio: sin él el registro de
salida no trae aeropuerto de llegada, así que la ruta es indeterminable y el
barrido completo se desperdicia. Ambas quedan fijadas en el adaptador.

Al contratar, conviene pedir el extracto **por aerolínea** cuando el proveedor lo
permita: garantiza que la red completa de cada operador entre a la semilla, que
es justo lo que evita la trampa de `column_scale` descrita más abajo.

#### Resultado del piloto con AeroDataBox

Probado con llave real sobre el martes 3 de febrero de 2026, los 40 aeropuertos
que concentran el 97.7 % de las salidas, dentro del tramo gratuito.

| | AeroDataBox | OpenSky |
|---|---:|---:|
| **Dispersión de cobertura entre aerolíneas** | **1.12x** | 2.8x |
| Vuelos con aerolínea identificada | 100 % | 57 % |
| Vuelos con aeropuerto de llegada | 99 % | 57 % |

La primera fila es la que decide, y AeroDataBox pasa el umbral de 1.15x. Los
cuatro operadores que mueven el mercado quedan dentro de un 12 % entre sí:

| Aerolínea | Factor de cobertura |
|---|---:|
| Volaris | 0.95 |
| Vivaaerobus | 0.99 |
| Aeroméxico Connect | 1.04 |
| Aeroméxico | 1.07 |

El día de muestra trajo 1,011 vuelos nacionales sobre 321 pares origen-destino,
el 3.0 % del mes según AFAC, contra un 3.5 % esperado para un día de veintiocho
cubriendo el 97.7 % de las salidas.

**Lo que el piloto no resuelve.** El veredicto automático sale `REJECT`, y por
buenas razones que son del alcance de la prueba, no de la fuente: faltan
Mexicana, TAR y Magnicharters —juntas el 1.2 % de los pasajeros—, la cobertura
llega al 93.3 % de los pasajeros y `column_scale` queda en 0.944. Las tres cosas
son consistentes con haber muestreado 40 de 58 aeropuertos en un solo martes.
Un mes completo las resuelve o las confirma; con el tramo gratuito agotado no se
puede decidir aquí. **No se publica nada hasta que un mes completo dé
`ACCEPT`.**

Aeroméxico y Aerolitoral se presentan bajo el mismo código `AM`, que AFAC sí
separa. El adaptador los divide por flota: los Embraer son Connect. En la
muestra el modelo de avión venía en el 100 % de los vuelos de AM.

#### Por qué OpenSky no sirve

Se probó con credenciales reales sobre febrero de 2026, gastando 540 de los
4,000 créditos diarios. Hallazgos:

- **Costo**: 30 créditos por llamada, y una ventana de dos días cuesta lo mismo
  que una de un día. Un mes de los 58 aeropuertos saldría en ~24,000 créditos,
  es decir seis días de cuota por cada mes de datos.
- **Cobertura**: de 9,448 salidas de México en el mes, solo 2,117 resuelven a un
  destino nacional reconocido. El 43 % no trae aeropuerto de llegada estimado.
- **La cobertura es bimodal por destino**, no degradada de forma pareja:
  Monterrey 92 %, Tijuana 95 %, Veracruz 92 %, Hermosillo 94 %; pero Guadalajara,
  Mérida, Puerto Vallarta, Oaxaca y la mayoría de los destinos quedan en **0 %**.
  Consultar *llegadas* en Guadalajara y Mérida devuelve cero, así que no es un
  fallo al estimar el destino: no hay receptores ADS-B con cobertura ahí.
- **Y la cobertura difiere por aerolínea**: Aeroméxico Connect resuelve 13 % de
  sus vuelos, Viva 37 %, Aeroméxico 26 %, Volaris 29 %.

Esa última línea es la que mata la opción. El ajuste absorbe que a una ruta le
falten vuelos de forma pareja, pero **no** absorbe que le falten más a una
aerolínea que a otra dentro de la misma ruta. Un factor de casi tres entre
operadores es exactamente el sesgo irreducible.

#### Prueba de aceptación antes de pagar

El ajuste tolera mucho más de lo que parece, y eso está **medido**, no supuesto.
Inyectando un sesgo conocido en el arnés de T-100, donde la verdad sí es pública:

| Sesgo inyectado en la semilla | 1.30x | 2.00x | 2.80x |
|---|---:|---:|---:|
| Por aerolínea, parejo en toda su red | 1.96 pp | 1.96 pp | 1.96 pp |
| Por ruta, parejo entre sus operadores | 1.96 pp | 1.96 pp | 1.96 pp |
| Por aerolínea **dentro** de cada ruta | 2.31 pp | 3.77 pp | 5.11 pp |

Los dos primeros son escalados de fila y columna, y el ajuste los cancela
exactamente: una fuente puede ver a una aerolínea tres veces mejor que a otra en
todo el mapa y el reparto no se mueve un pasajero. Solo sobrevive la
interacción, y esa **no es identificable desde las marginales**, porque es la
misma no identificabilidad que el estimador existe para rodear.

Así que la prueba no finge medir la interacción. Juzga lo que sí rompe un ajuste
en la práctica, que es la completitud:

- **Una aerolínea ausente**: su total nacional no tiene a dónde ir, y el ajuste
  o se niega o empuja esos pasajeros a las rutas que queden.
- **Una ruta ausente**: quien la vuela recibe un cero estructural y sus
  pasajeros se van a otra parte.
- **Una red parcial**, que delata `column_scale`.

El factor de cobertura por aerolínea se sigue reportando porque dice algo útil
de una fuente, pero está marcado como **diagnóstico, no veredicto**. Leerlo como
veredicto fue un error que este módulo cometía: sobre el piloto marcaba 1.30x y
concluía que no pasaba, cuando un sesgo de esa forma cuesta exactamente cero.

Se corre así:

```python
from src.analytics.seed_acceptance import assess_seed, format_report
print(format_report(assess_seed(flights, "2026M07")))
```

Umbrales del veredicto: se rechaza si falta alguna aerolínea, si la semilla no
alcanza al 95 % de los pasajeros, o si `column_scale` se aparta de 1 más de
cinco puntos. Entre 95 % y 99 % de cobertura queda en revisión.

Cualquiera de las fuentes de itinerarios entrega una tabla
`period_id, origin_iata, dest_iata, carrier_key, flights`, que es justo lo que
`build_seed_from_flights` consume. El adaptador de cada proveedor es lo único
específico; el resto de la tubería no cambia.

## No es una suscripción mensual: es una vez al año

La regla medida es que la semilla debe ser **del mismo mes que las marginales**,
no que haya que pagar todos los meses. Son cosas distintas, y la diferencia
vale dinero.

Dos hechos, ambos verificados contra las fuentes y no leídos de un tarifario:

- **El archivo histórico de AeroDataBox llega a 365 días.** Una consulta a 379
  días devolvió cero vuelos. Dentro de esa ventana, cada mes pasado se puede
  bajar con su propia semilla contemporánea.
- **AFAC publica con cerca de un mes de retraso.** El Boletín Mensual de julio
  de 2026 ya reporta julio de 2026. Así que un mes recién publicado cae muy
  dentro de la ventana de 365 días; el margen es de unos diez meses.

De ahí sale la operación: **se contrata un mes, se baja todo el rezago, se
cancela.** Y se repite una vez al año, antes de que los meses más viejos se
caigan de la ventana.

| Qué se baja | Unidades | Costo |
|---|---:|---:|
| Un mes de semilla, muestreando los 30 días | 6,960 | — |
| Un mes de semilla, muestreando una semana completa | 1,624 | — |
| **Respaldo de 12 meses, 30 días** | 83,520 | 3 meses de Starter = **USD 57** |
| **Respaldo de 12 meses, una semana por mes** | 19,488 | 1 mes de Starter = **USD 19** |

Contra los USD 19 al mes de una suscripción permanente, el ciclo anual cuesta
entre **USD 19 y 57 al año**.

### Lo que sí se pierde para siempre

La ventana de 365 días es un plazo, no un inconveniente. Hoy el archivo llega
hasta septiembre de 2025 hacia atrás; **todo 2024 y el primer semestre de 2025
ya están fuera y no se recuperan de esta fuente**, por más que se pague después.
Justo son los meses que cubren las marginales de AFAC que ya tenemos
(2024M01–2025M03).

Para esos meses las opciones son un proveedor con archivo profundo —Cirium y OAG
guardan décadas— o quedarse sin estimación. Es el único punto donde el proveedor
caro se gana su precio, y es solo para el respaldo, no para la operación.

Cada mes que pasa, otro mes se cae de la ventana. El rezago recuperable se
encoge solo.

### Una optimización que falta medir

La tabla de arriba asume que **una semana completa basta** para fijar la mezcla
de aerolíneas de un mes. Es plausible —los itinerarios son semanales, y una
semana entera cubre los siete días de la semana una vez— pero **no está medido**,
y de eso depende que el ciclo anual cueste 19 o 57 dólares.

Se mide dentro del primer mes pagado, gratis: se baja un mes completo, se arma
la semilla con la primera semana y con los treinta días, y se comparan las
participaciones resultantes. Si la diferencia queda debajo del error propio del
estimador (1.98 pp), el muestreo semanal es legítimo.

## La semilla tiene que ser del mismo mes

Antes de elegir proveedor conviene saber si la semilla se compra una vez o se
paga cada mes. Es una pregunta medible: se corre el mismo arnés, pero
estimando el mes *t* con la oferta observada en el mes *t−k*.

| Antigüedad de la semilla | Error en participación | Error en pasajeros | Meses estimables |
|---|---:|---:|---:|
| Mismo mes | 1.96 pp | 5.92 % | 12 de 12 |
| Un mes | 4.04 pp | 11.99 % | 3 de 11 |
| Dos meses | 6.49 pp | 19.01 % | 2 de 10 |
| Seis meses | 7.35 pp | 20.38 % | 1 de 6 |

Dos cosas se rompen a la vez. El error **se duplica** con un solo mes de
desfase, porque la participación dentro de una ruta se mueve 4.60 pp de un mes
al siguiente en promedio —más que el error propio del estimador, así que una
semilla vieja domina el presupuesto de error. Y en 8 de 11 meses el ajuste ni
siquiera corre: levanta `InfeasibleMarginsError` porque aparecen rutas y
aerolíneas que la semilla del mes anterior no conoce. La mediana es de 25 rutas
competidas nuevas por mes sobre unas 198.

Conclusión operativa: **la semilla es una suscripción, no una compra**. Hay que
refrescarla todos los meses, contra el mes que se va a estimar.

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
