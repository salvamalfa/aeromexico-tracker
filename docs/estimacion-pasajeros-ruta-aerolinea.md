# Estimación de pasajeros por ruta y aerolínea · método canónico

Fecha: 21 de septiembre de 2026 (revisado el mismo día con las verificaciones
de `REG INT`, T-100 celda a celda y el sondeo de 8 unidades).
Estado: documento canónico del método. Describe lo que **ya está en producción**
para el mercado nacional y fija las condiciones exactas que deben cumplirse
antes de extenderlo al mercado internacional. No autoriza por sí solo ninguna
publicación, activación de evidencia ni consumo de API.

**Veredicto sobre la extensión internacional: viable en su condición
bloqueante.** Las dos marginales internacionales de AFAC describen el mismo
universo —cero pasajeros de diferencia en los siete meses de 2026 leídos de la
misma edición (§9.3)— y la semilla existe y fue observada en vivo (§9.6). Lo
que falta no es evidencia de factibilidad sino construcción: el parser de
`REG INT`, dos crosswalks revisados a mano y una captura mensual. El riesgo
abierto y cuantificado es el 17.6 % de registros con estado de código
compartido desconocido (§9.6).

Este documento es la referencia que debe leer cualquier agente o persona antes
de tocar el estimador. Sustituye la reconstrucción del método a partir de
conversaciones o de reportes de etapa sueltos.

---

## 1. El problema estadístico

AFAC publica dos cortes de la misma microdata y nunca la celda conjunta:

- **Marginal de ruta**: pasajeros por par de ciudades, mes y dirección, sumando
  todas las aerolíneas. No identifica operador.
- **Marginal de aerolínea**: pasajeros por empresa y mes. No identifica ruta.

Lo que el dashboard necesita es la celda: *cuántos pasajeros llevó esta
aerolínea en esta ruta este mes*. Esa celda no está publicada y **no es
identificable** a partir de las dos marginales: infinitas matrices respetan los
mismos totales por fila y por columna.

Por eso el resultado del método es una **estimación**, no una observación, y
por eso ninguna propiedad aritmética del ajuste —ni siquiera reconciliar las
dos marginales al pasajero— puede convertirla en dato observado.

### Qué aporta AeroDataBox, y qué no

AeroDataBox **no publica pasajeros**. En toda la especificación OpenAPI
1.15.3.0 la palabra aparece una sola vez, en `numSeats` de la ficha de
aeronave. Lo que aporta es **estructura de oferta**: qué operador voló qué ruta,
cuántas veces, con qué aeronave. Esa estructura es la semilla del ajuste.

La semilla no observa demanda. Observa quién compite contra quién dentro de
cada ruta, que es precisamente lo que las dos marginales no dicen.

---

## 2. El ajuste: iterative proportional fitting

Sea `S` la matriz semilla de dimensión `R × C` (rutas × aerolíneas), con
`S[i][j] ≥ 0` igual al peso de oferta del operador `j` en la ruta `i`. Sean
`u[i]` los pasajeros publicados de la ruta `i` y `v[j]` los de la aerolínea `j`.

**Reescalamiento previo de la marginal de columna.** Las dos marginales rara vez
suman idéntico. El ajuste lleva las columnas al total de las filas y **registra
el factor**, no lo esconde:

```
column_scale = (Σ u[i]) / (Σ v[j])
v'[j] = v[j] · column_scale
```

**Iteración.** Partiendo de `M⁰ = S` (los ceros se preservan), se alternan:

```
M^(2k+1)[i][j] = M^(2k)[i][j] · u[i] / Σ_j M^(2k)[i][j]      (filas a su total)
M^(2k+2)[i][j] = M^(2k+1)[i][j] · v'[j] / Σ_i M^(2k+1)[i][j]  (columnas a su total)
```

Una línea cuyo total sea cero no se escala: el factor se fija en cero en lugar
de dividir entre cero.

**Criterio de paro.** Convergencia relativa al gran total:

```
max( max_i |Σ_j M[i][j] − u[i]| , max_j |Σ_i M[i][j] − v'[j]| ) / Σ u  ≤  tol
```

con `tol = 1e-8` y un máximo de 5,000 iteraciones
(`DEFAULT_TOLERANCE`, `DEFAULT_MAX_ITERATIONS` en
`src/analytics/route_carrier.py`). La tolerancia es relativa porque un umbral
absoluto en pasajeros queda por debajo de la resolución de `float64` sobre
marginales de decenas de millones: `1e-8` de un mercado de tres millones son
tres centésimas de pasajero.

### Por qué IPF y no otra cosa

La propiedad que importa es **qué ignora**. Escalar una fila completa o una
columna completa de la semilla deja el resultado ajustado idéntico. Por tanto:

- el **calibre medio** de una aerolínea (que vuele aviones grandes o chicos en
  toda su red) es un escalamiento de columna: se cancela;
- la **cobertura desigual** de la semilla en una ruta (que la muestra vea más o
  menos vuelos de esa ruta) es un escalamiento de fila: se cancela;
- lo único que **sobrevive** es la interacción *dentro* de la ruta: qué
  proporción de la oferta de esa ruta es de cada operador.

Eso es exactamente lo que la semilla puede observar y lo que las marginales no
pueden decir. El resultado es la estimación de máxima entropía consistente con
ambas marginales.

Esto está medido, no afirmado. Inyectando un sesgo conocido en el arnés T-100
(`tests/test_route_carrier_ipf.py` y la tabla en
`src/analytics/seed_acceptance.py`):

| Sesgo inyectado en la semilla | 1.30x | 2.00x | 2.80x |
|---|---:|---:|---:|
| Por aerolínea, en toda su red | 1.96 | 1.96 | 1.96 |
| Por ruta, en todos sus operadores | 1.96 | 1.96 | 1.96 |
| Por aerolínea **dentro** de cada ruta | 2.31 | 3.77 | 5.11 |

(error de participación ponderado, en puntos porcentuales, contra una base de
1.96 pp). Las dos primeras filas no se mueven: son escalamientos y el ajuste
los cancela exactamente.

---

## 3. Grano y definiciones de las marginales

El ajuste se corre en el grano de las marginales, nunca en uno más grueso:

```
mes × ruta direccional × operador
```

Ajustar directamente sobre el trimestre da celdas distintas de sumar tres
ajustes mensuales. La agregación a trimestre para el dashboard ocurre **después**
del ajuste.

### Contratos de entrada (`src/analytics/route_carrier.py`)

| Objeto | Columnas exactas | Constante |
|---|---|---|
| `seed` | `period_id, route_key, carrier_key, weight` | `SEED_COLUMNS` |
| `route_totals` | `period_id, route_key, passengers` | — |
| `carrier_totals` | `period_id, carrier_key, passengers` | — |
| tabla del proveedor | `period_id, origin_iata, dest_iata, carrier_key, flights` | `FLIGHT_COLUMNS` |

`route_key` está en el **vocabulario de ciudades de AFAC**, no en códigos IATA:
`"MEXICO-MONTERREY"`, `"DEL BAJIO-TIJUANA"`. `build_seed_from_flights()` hace
la traducción con `data/reference/afac_city_iata_crosswalk.csv` y **lanza
`UnmappedSeedError`** ante cualquier aeropuerto ausente: nunca descarta en
silencio.

`estimate_route_carrier()` recorta ambas marginales a las rutas y aerolíneas
presentes en la semilla. Una ruta o una aerolínea que la semilla no vio no
recibe pasajeros; eso es correcto pero deja masa fuera, y por eso la puerta de
aceptación mide la cobertura antes.

### Marginales nacionales, verificadas

| Marginal | Archivo | Origen | Grano |
|---|---|---|---|
| Ruta | `data/reference/afac_od_nacional_regular.csv` | hoja `REG NAC` de los libros O-D (`sase-*.xlsx`) | `period_id, origen, destino, vuelos, pasajeros` |
| Aerolínea | `data/reference/afac_carrier_domestic.csv` | base larga DATATUR (`DB_AFAC.zip`, hoja `AFAC`, `Tipo=Nacional`, `Servicio=Regular`) | `period_id, carrier_name, pasajeros` |

Layout de `REG NAC` (índices base cero, `src/ingest/afac/margins.py`): encabezado
en la fila 5, claves en 0–1 (`ORIGEN`, `DESTINO`), vuelos en 2–13, total en 14,
pasajeros en 15–26. Localizador del encabezado: `REG NAC!A5:AO6`, 41 columnas,
609 filas de datos en la edición de julio de 2026.

**Prueba de universo compartido, ejecutada el 2026-09-21.** Las dos marginales
nacionales no solo se parecen: coinciden al pasajero.

| Meses comparados | Diferencia exacta 0 | Diferencia máxima | Error relativo máximo |
|---:|---:|---:|---:|
| 22 (2024M01–2026M07) | 19 de 22 | 36 pasajeros | 0.0007 % |

Reproducible comparando `afac_od_nacional_regular.csv` contra
`afac_carrier_domestic.csv` agrupados por `period_id`. Esa coincidencia
demuestra que existe una tabla conjunta aguas arriba y que ambas marginales
comparten universo.

### Qué mide realmente OFOD

El encabezado de las hojas dice *«ESTADISTICA OPERACIONAL ORIGEN-DESTINO /
AVIATION STATISTICS BY **OFOD**»*. **La coincidencia de las dos marginales no
demuestra, por sí sola, que OFOD cuente pasajeros por tramo**: dos tablas
construidas ambas por itinerario también coincidirían. Hacía falta evidencia
directa y se buscó.

El documento metodológico que AFAC enlaza
(`afac_research_methodology_2023_*.pdf`, 19 páginas) es un extracto del glosario
del *Manual sobre reglamentación del transporte aéreo internacional* de la OACI
y **no define OFOD ni la base de conteo de pasajeros**. Se revisaron las 19
páginas buscando «OFOD», «origen-destino», «etapa», «tramo», «escala»,
«embarque» y «desembarque»: no hay definición aplicable. En la terminología de
la OACI, OFOD es *on-flight origin and destination*: el par de embarque y
desembarque **dentro de un mismo número de vuelo**, que coincide con el tramo
salvo en servicios con escala intermedia bajo un solo número de vuelo. No es el
origen y destino final del itinerario del pasajero.

A falta de definición publicada, la base de conteo se estableció
empíricamente, con dos pruebas:

1. **Ninguna fila con pasajeros y sin vuelos.** De las 11,748 filas
   mes × par de `REG INT`, **cero** tienen `pasajeros > 0` con `vuelos = 0`.
   Una tabla de itinerarios verdaderos contendría pares que nadie vuela sin
   escala (por ejemplo Mérida–Madrid vía México); esta no los contiene.
2. **Coincidencia con una fuente estrictamente de tramo.** BTS T-100 cuenta
   segmentos sin escala. Comparando los pares México–Estados Unidos de
   `REG INT` contra T-100 agregado a ciudad, mes a mes (enero–mayo 2026):
   2,208 celdas emparejadas, razón de sumas **0.9999**, diferencia relativa
   **mediana de 0.53 %**, p90 de 5.69 %, y 75.7 % de las celdas dentro de ±2 %.

Conclusión: **para este mercado OFOD se comporta como tramo sin escala**. El
residuo de medio punto porcentual es donde vivirían los servicios con escala
intermedia bajo un mismo número de vuelo, que es exactamente la diferencia que
la definición de la OACI predice entre OFOD y tramo. No se afirma que OFOD
*sea* idéntico al tramo por definición; se afirma que, medido, la diferencia
es de ese orden.

---

## 4. Construcción y aceptación de la semilla

### Captura

El adaptador nacional (`src/ingest/aerodatabox/flights.py`) barre cada
aeropuerto mexicano pidiendo **salidas**, en ventanas de 12 horas (el plan
responde una ventana mayor con una lista vacía en lugar de un error), con
`withCodeshared=false`, `withCancelled=false`, `withCargo=false`,
`withPrivate=false` y `withLeg=true`. Sin `withLeg` el registro no trae
aeropuerto de llegada y la ruta es desconocida.

### Normalización y exclusiones

Cada exclusión corresponde a una forma concreta de corromper la semilla:

| Se descarta | Por qué |
|---|---|
| `codeshareStatus = IsCodeshared` | un vuelo contado bajo dos aerolíneas mueve las proporciones **dentro** de la ruta, que es el único contenido de la semilla |
| `isCargo` | infla una ruta que no lleva pasajeros |
| cancelaciones | no son oferta realizada |
| sin aeropuerto de llegada | no pertenece a ninguna ruta |
| operadores no regulares (`NON_SCHEDULED_ICAO`) | fuera del universo AFAC de servicio regular |
| destino no nacional | pertenece al cubo internacional, no al nacional |
| `AM` sin modelo de aeronave | no se puede separar Aerovías de Connect; acreditarlo a Aerovías sería inventar |

Todo lo descartado queda **contado** en `PullStats`, nunca silenciado.

### Muestreo y ponderación

Un mes completo cuesta el doble que una semana. La muestra de siete días se
elige con un paso coprimo con 7 para recorrer todos los días de la semana, y
cada día muestreado se pondera por cuántas veces aparece su día de semana en el
mes (`day_weights` en `src/ingest/aerodatabox/__main__.py`). Julio de 2026 tiene
cinco miércoles y cuatro domingos: contarlos una vez cada uno leería el mercado
a través de los días que tocó la muestra, y el mix de aerolíneas se mueve con
el calendario semanal.

La ponderación corrige la **composición**, no la **dispersión**. Es adecuada
para rutas troncales con frecuencia diaria; es un instrumento grueso para una
ruta de dos o tres frecuencias semanales.

### Puerta de aceptación (`seed_acceptance_v3`)

Tres estados, con umbrales fijos en `src/analytics/seed_acceptance.py`:

| Veredicto | Condición |
|---|---|
| `accept` | cobertura de pasajeros 100 %, sin operadores ausentes, sin notas |
| `review` | cobertura ≥ 95 %, operadores ausentes ≤ 5 % de pasajeros AFAC, `column_scale` dentro de ±5 % |
| `reject` | cualquiera de esos tres límites incumplido |

Solo `accept` y `review` pueden ajustarse, y ambos siguen marcados como
estimación. `column_scale` fuera de ±5 % es fatal porque significa que la
semilla cubre solo parte de la red de alguna aerolínea: el ajuste le exigiría a
esa aerolínea más pasajeros de los que sus rutas observadas pueden sostener, y
el error entra en celdas que se ven sanas.

La cobertura **por aerolínea** se reporta como diagnóstico, no como veredicto:
es un escalamiento de columna y el ajuste la cancela. Leerla como veredicto fue
un error que este módulo ya cometió y corrigió.

---

## 5. Ceros, infactibilidad, no convergencia y soporte temporal

### Ceros estructurales

Un cero en la semilla significa "este operador no ofreció nada en esta ruta" y
se preserva: el ajuste nunca le entrega pasajeros. Esa es la diferencia entre
un cero y un faltante, y es la razón por la que la semilla no puede rellenarse
con ceros por comodidad.

### Infactibilidad

`_assert_feasible` rechaza antes de iterar dos situaciones:

- una **ruta** con pasajeros publicados y ningún operador en la semilla;
- una **aerolínea** con pasajeros publicados y ninguna ruta en la semilla.

Ambas lanzan `InfeasibleMarginsError`. No se fabrica soporte para salvar el
ajuste.

### No convergencia

Si el ajuste no converge, el resultado **no se lee como número**. El bloqueo
suele ser estructural, no de tolerancia ni de cómputo: en marzo, junio y julio
de 2026 se probó hasta 200,000 iteraciones antes de descartarlo. La causa real
fue que la muestra mensual no contenía ciertas combinaciones ruta × operador
necesarias para satisfacer simultáneamente ambas marginales.

### Soporte temporal (`route_carrier_temporal_ipf_v1`)

La reparación, y sus límites:

1. La semilla observada del mes **manda** siempre que converja. Solo si falla se
   intenta reparar.
2. Se incorpora únicamente una combinación ruta × operador **observada en otro
   mes retenido**, tomando primero el mes más cercano y ampliando hasta dos
   meses (`max_month_gap = 2`) solo si hace falta.
3. La celda prestada se marca con `support_observed_in_period = False`,
   `support_source_periods` y `support_month_gap`. **Nunca se llama vuelo
   observado del mes objetivo.**
4. El peso base prestado es `0.1` del observado; el ajuste se recalcula con
   `0.01` y `1.0` para formar `passengers_estimated_low/high`.

Ese rango mide **la dependencia del resultado respecto al peso del soporte
añadido**. No es un intervalo estadístico de confianza y no debe presentarse
como tal.

Resultado nacional vigente:

| Periodo | Reparación | Celdas prestadas | Iteraciones | Mercados AM/Connect |
|---|---|---:|---:|---:|
| 2026M03 | mes contiguo | 36 | 29 | 55 |
| 2026M04 | no requerida | 0 | 25 | 55 |
| 2026M05 | no requerida | 0 | 33 | 55 |
| 2026M06 | mes contiguo | 40 | 43 | 56 |
| 2026M07 | hasta dos meses | 51 | 75 | 55 |

---

## 6. Reconciliación, sensibilidad y marcas

Cada corrida debe persistir, además de la celda:

- `is_estimated = True` y `is_exact = False`, **siempre**;
- `estimator_version` (`route_carrier_ipf_v1` o `route_carrier_temporal_ipf_v1`);
- `seed_acceptance_verdict`, `seed_passenger_coverage`, `seed_missing_carriers`,
  `seed_missing_carrier_passenger_share`;
- `column_scale`, `iterations`, `converged`, `max_row_deviation`,
  `max_col_deviation`;
- `is_single_operator_seed`, `support_repair_applied`, `support_month_gap`,
  `passengers_estimated_low/high`;
- `historically_eligible_at_2026_07_13 = False` y `agent_eligible = False` para
  todo lo retrospectivo.

### `is_single_operator_seed` no significa exacto

Que la semilla haya visto un solo operador en una ruta es **soporte útil**, no
prueba de que ningún otro operador voló esa ruta ese mes. El código fija
`is_exact = False` incluso en ese caso. Solo puede llamarse exacta si la
cobertura de la semilla demuestra que no falta otro operador **y** ambas
marginales usan exactamente el mismo universo.

---

## 7. Observado, programado y estimado

Tres poblaciones que nunca se suman entre sí:

| Categoría | Qué es | Ejemplo vigente |
|---|---|---|
| **Observado** | la fuente publica la celda | BTS T-100 en México–EE. UU.; ANAC Brasil |
| **Programado** | itinerario o slot asignado; ejecución no verificada | 25 mercados AICM `assigned_slot_not_flown` en 2026Q2 |
| **Estimado** | resultado del ajuste | los 713 pares direccionales nacionales de abril |

También se mantienen separados: vuelos realizados de programación; pasajeros por
tramo de pasajeros de itinerario; operador de comercializador/codeshare;
Aerovías de México de Aeroméxico Connect cuando la fuente los distinga; y cifras
de Aeroméxico de totales de todas las aerolíneas.

---

## 8. Aerovías, Connect y Grupo Aeroméxico

AFAC separa `Aeroméxico (Aerovías de México)` de
`Aeroméxico Connect (Aerolitoral)` en su marginal de aerolínea. El orden es:

1. **Ajustar por separado.** Cada razón social entra al IPF como su propia
   columna, contra su propio total publicado.
2. **Validar la celda** con los diagnósticos de la sección 6.
3. **Sumar después** para la interfaz, bajo la etiqueta `Grupo Aeroméxico`,
   conservando el linaje interno de cada filial.

Lo prohibido es ajustar **solo** esas dos columnas contra un total de ruta que
incluye a todas las aerolíneas: eso le entregaría a Aeroméxico el tráfico de
Volaris y Viva. El total de ruta es del mercado; las columnas deben cubrir el
mercado entero.

En la red internacional la evidencia retenida es exclusivamente de **Aerovías de
México como operador reportante**: las 350 filas de
`fact_international_route_observations` son 100 % `AMX`, ninguna `SLI`. Por eso
la vista internacional nunca debe rotularse "Grupo Aeroméxico".

---

## 9. Qué se necesita para extenderlo a internacional

El método no cambia. Lo que cambia es que cada pieza tiene que volver a
demostrarse en el universo internacional.

### 9.1 Marginal de aerolínea internacional — **disponible y verificada**

Está parseada en Silver (`data/silver/afac_monthly_stats.parquet`, respaldo
privado) con `market='international'`, `service_type='scheduled'`:

| Familia de fuente | Periodos | Aerolíneas distintas |
|---|---|---:|
| `datatur_monthly_bulletin_pdf` | 2026M01–2026M06 | 66 |
| `xlsx_modern_2017_2025` | 2017M01–2025M12 | 103 |
| `xlsx_wide_2012_2016` | 2015M01–2016M12 | 64 |

Incluye mexicanas y extranjeras (`is_domestic_carrier`). Totales de servicio
regular internacional, todas las aerolíneas:

| Mes | Pasajeros |
|---|---:|
| 2026M01 | 5,796,013 |
| 2026M02 | 5,028,616 |
| 2026M03 | 5,449,478 |
| 2026M04 | 4,827,573 |
| 2026M05 | 4,268,203 |
| 2026M06 | 4,433,781 |

Comprobación cruzada: el valor de Aeroméxico en 2026M05 es 648,414, idéntico al
de `PAXREG!A24:H24` del resumen por empresa de julio de 2026 registrado en
`docs/etapas/afac-rutas-evidencia-20260908/inspection.json`. Las dos vías de
publicación coinciden.

### 9.2 Marginal de ruta internacional — **disponible y verificada en el archivo**

La hoja `REG INT` del mismo libro O-D, abierta y parseada el 2026-09-21 desde
`snapshot/data/bronze/afac_research/afac_research_city_pairs_2026M07_20260908T182059Z.xlsx`
del respaldo privado.

Encabezado real, filas 4 y 5 (índices base cero):

```
fila 1: ESTADISTICA OPERACIONAL ORIGEN-DESTINO / AVIATION STATISTICS BY OFOD
fila 2: EN SERVICIO REGULAR INTERNACIONAL, 2026 / SCHEDULED INTERNATIONAL SERVICE, 2026
fila 4: PAR DE CIUDADES / CITY PAIR | VUELOS / FLIGHTS | PASAJEROS / PASSENGERS | CARGA (kg)
fila 5: ORIGEN / FROM | PAÍS ORIGEN | DESTINO / TO | PAÍS DESTINO | Ene..Dic + Total (x3)
pie   : FUENTE: SICT, AFAC, DREE. Información proporcionada por las aerolíneas.
```

Layout confirmado, índices base cero:

```
0–3    ORIGEN, PAÍS ORIGEN, DESTINO, PAÍS DESTINO
4–15   vuelos, enero a diciembre        16  total de vuelos
17–28  pasajeros, enero a diciembre     29  total de pasajeros
30–41  carga (kg)                       42  total de carga
```

Contra `REG NAC`, que tiene 41 columnas y offsets 2 y 15: las dos columnas
extra son las de país y desplazan ambos offsets en dos. Datos desde la fila 6.

| Propiedad | `REG NAC` | `REG INT` |
|---|---|---|
| Filas de datos | 609 | **979 pares direccionales** |
| Filas mes × par parseadas | — | **11,748** |
| Columnas | 41 | **43** |
| Países | solo `Mexico` | **37 etiquetas** (36 destino, 37 origen) |
| Columna de operador | no | **no** |
| Columna de asientos | no | **no** |
| Meses con datos (edición julio 2026) | 1–7 | 1–7 |

### 9.3 La prueba de universo compartido — **ejecutada y superada**

Comparando `REG INT` contra la marginal por aerolínea de la **misma edición**
del resumen por empresa (`PAXREG`, bloque «EMPRESAS NACIONALES · SERVICIO
REGULAR INTERNACIONAL» fila 28 más el total de «EMPRESAS EXTRANJERAS» fila 96,
excluyendo los subtotales regionales para no contar doble):

| Mes | `REG INT` (ruta) | Marginal por aerolínea | Diferencia |
|---|---:|---:|---:|
| 2026M01 | 5,796,018 | 5,796,018 | **0** |
| 2026M02 | 5,028,616 | 5,028,616 | **0** |
| 2026M03 | 5,449,478 | 5,449,478 | **0** |
| 2026M04 | 4,828,119 | 4,828,119 | **0** |
| 2026M05 | 4,304,645 | 4,304,645 | **0** |
| 2026M06 | 4,438,858 | 4,438,858 | **0** |
| 2026M07 | 5,014,324 | 5,014,324 | **0** |

**Cero pasajeros de diferencia en los siete meses.** La marginal internacional
se descompone además en nacionales (1.29–1.88 M/mes) y extranjeras
(2.81–4.12 M/mes), ambas dentro del mismo total.

**La comparación debe hacerse por edición.** Contrastar `REG INT` de la edición
de julio contra la marginal por aerolínea capturada de boletines DATATUR
anteriores (`is_preliminary = True` en Silver) produce diferencias que crecen
hacia los meses recientes —0 en enero–marzo, 546 en abril, 36,442 en mayo,
5,077 en junio—, que son **revisiones**, no una brecha de universo. Mezclar
ediciones es el error que hay que evitar, no la fuente.

**Corrección explícita.** Una versión anterior de este documento decía que el
IPF internacional «no hace falta demostrar igualdad de universos para producir
la estimación». Eso era incorrecto: el IPF **sí requiere** que ambas marginales
describan el mismo universo, porque ajusta una matriz a las dos simultáneamente
y `column_scale` solo absorbe una diferencia de escala global, no una
diferencia de cobertura. La condición se exige y, para internacional, está
probada arriba.

### 9.4 Cómo se usa T-100: subconjunto observado, no insumo del ajuste

**Corrección de una evaluación previa.** Este documento afirmaba que la
comprobación agregada «no confirma» que T-100 comparta universo con AFAC. Esa
comparación estaba mal planteada: contrastaba T-100 México–Estados Unidos
contra el total internacional de AFAC **de todos los países**, y luego contra un
porcentaje regional de un mes distinto. Que T-100 represente ~64 % del
internacional de AFAC no es una discrepancia: es que el resto son Canadá,
Europa, Asia y Latinoamérica.

La comparación correcta es celda a celda, restringida a los pares
México–Estados Unidos, agregando T-100 a **ciudad** porque AFAC publica
ciudades y no aeropuertos. Ejecutada para enero–mayo de 2026:

| Métrica | Resultado |
|---|---:|
| Pasajeros AFAC en pares México–EE. UU. | 16,289,260 |
| Pasajeros T-100 transfronterizo | 16,336,366 |
| Celdas mes × par emparejadas automáticamente | 2,208 |
| Cobertura de la comparación | 93.99 % del lado AFAC, 93.73 % del lado T-100 |
| **Razón de sumas en celdas emparejadas** | **0.9999** |
| Diferencia relativa mediana por celda | **0.53 %** |
| p90 de la diferencia relativa | 5.69 % |
| Celdas dentro de ±2 % / ±5 % | 75.7 % / 87.4 % |

El 6 % sin emparejar **no es cobertura faltante**: es nomenclatura de ciudad.
`DEL BAJIO` es `Silao` (15,411 contra 15,229 pasajeros), `SAN JOSE, CALIFORNIA`
es `San Jose` (14,352 contra 14,293), `WASHINGTON` es `Dulles` (11,909 contra
11,910). Un crosswalk de ciudades revisado a mano cierra esa brecha.

**T-100 es, por lo tanto, un subconjunto observado y comparable del universo
internacional de AFAC.** Eso le da tres papeles legítimos y uno prohibido.

| Papel | Cómo |
|---|---|
| **Verdad publicable** | Donde T-100 observa la celda ruta × operador, el dashboard publica T-100 y marca la celda `observado`. El ajuste no la sustituye |
| **Validación del estimador** | Con una semilla real de AeroDataBox, el subcubo estadounidense da el error medido del estimador internacional sobre el cubo que se va a publicar, no sobre un panel sintético |
| **Control de cobertura de la semilla** | `REG INT` publica `vuelos` por par y mes; la semilla capturada debe reproducir ese conteo dentro de tolerancia, igual que `seed_acceptance` hace en nacional |
| **Prohibido: insumo del ajuste** | T-100 no entra como fila, columna ni peso. Sumarlo o restarlo de las marginales de AFAC introduce doble conteo y rompe la reconciliación |

**Cómo se evita la contradicción con los totales del IPF.** El ajuste se corre
sobre el cubo internacional completo —todas las filas de `REG INT`, incluidas
las de Estados Unidos, y todas las columnas de la marginal por aerolínea— y
reconcilia ambas marginales exactamente. La celda ajustada de una ruta
estadounidense **diferirá** de la celda observada de T-100, y esa diferencia es
el error medido del estimador, no un conflicto de datos. La regla de
presentación es explícita:

1. se publica T-100 donde existe, etiquetado `observado`;
2. la celda ajustada de esa misma ruta se conserva solo como diagnóstico, con
   su diferencia contra T-100 como métrica de calidad;
3. **nunca se suman** una celda observada y una estimada en el mismo total;
4. los totales por ruta y por aerolínea que se muestren junto a celdas mixtas
   declaran qué parte es observada y qué parte estimada.

**La resta del subcubo estadounidense** —restar T-100 de ambas marginales y
ajustar solo el residuo no estadounidense— ya no está descartada por el
universo: la comparación celda a celda la respalda. Sigue bloqueada por la
**identidad del operador**: T-100 no tiene ninguna fila `AEROMEXICO_CONNECT` en
el tráfico transfronterizo de 2026, mientras AFAC le atribuye a Connect entre
36,239 y 49,198 pasajeros internacionales al mes, y el sondeo del 2026-09-10
observó 14 tramos internacionales operados por Connect. Restar sin resolver esa
correspondencia dejaría tráfico de Connect dentro del residuo no estadounidense
donde no pertenece. Es una optimización, no un requisito: el cubo completo no
la necesita.

### 9.5 Piezas nuevas que hay que construir

| Pieza | Análogo nacional | Estado |
|---|---|---|
| Parser de `REG INT` | `read_route_workbook` en `src/ingest/afac/margins.py` | layout verificado (offsets 4 y 17); **falta el parser productivo y sus pruebas** |
| Crosswalk ciudad AFAC internacional ↔ IATA | `afac_city_iata_crosswalk.csv` (58 aeropuertos) | **no existe**; 37 países y ciudades con varios aeropuertos en ambos extremos. El emparejamiento automático contra T-100 alcanzó 94 % y el 6 % restante es nomenclatura resoluble a mano |
| Crosswalk aerolínea AFAC internacional ↔ IATA/ICAO | `afac_carrier_crosswalk.csv` (2 filas) | **no existe**; el resumen por empresa lista 5 nacionales y ~45 extranjeras con subtotales regionales que **no deben contarse** |
| Puerta de aceptación internacional | `seed_acceptance_v3` | reutilizable **y con mejor insumo**: `REG INT` publica `vuelos` por par y mes, así que la cobertura de la semilla se mide por división directa y no por inferencia |
| Semilla internacional | `flights.py` | **existe y está probada en vivo**: `src/ingest/aerodatabox/international.py` |

### 9.6 El sondeo del 2026-09-10: qué se compró y qué se aprendió

Un día local en MEX y MTY, ambos sentidos. **4 llamadas, 8 unidades**, cero en
caché, ninguna ventana vacía. El contenido crudo del proveedor se eliminó al
extraer los diagnósticos.

| Métrica | Resultado |
|---|---:|
| Registros devueltos | 1,081 (545 salidas, 536 llegadas) |
| Tramos nacionales descartados en ambos extremos | 672 |
| Tramos internacionales conservados | 366 |
| Mercados internacionales distintos | 79 |
| Operadores distintos | 26 |
| **Mercados de Grupo Aeroméxico** | **54** |
| Registros sin aeropuerto opuesto | 43 (4.0 %) |
| Vuelos `AM` sin modelo de aeronave | 0 |

Los 54 mercados de Grupo Aeroméxico incluyen **30 de los 32 que hoy muestran
`N/D`** en el dashboard: MAD, CDG, AMS, FCO, BCN, LHR, ICN, NRT, YYZ, YUL, YVR,
BOG, MDE, CLO, CTG, LIM, UIO, EZE, GUA, SAL, SAP, SJO, PTY, SDQ, PUJ, HAV, XPL,
RDU, y los dos de Monterrey (MAD y CDG) que hoy solo conocemos por un
comunicado de OMA. Faltaron `MEX<>MGA` y `MEX<>SNA`, que no operaron ese día.
Apareció además `ICN<>MTY`, que no está en la red del dashboard.

**El riesgo medido, y es el hallazgo importante.** De los 1,081 registros,
**190 (17.6 %) llegan con `codeshareStatus = Unknown`**; entre los de AM y
Connect, 92 de 476 (**19.3 %**). La especificación advierte que en aeropuertos
sin información de código compartido se aplica «complex filtering … caution:
false results are possible». Como la consulta pide `withCodeshared=false`, esos
190 registros sobrevivieron por una **heurística del proveedor**, no por un
estado declarado. Casi una quinta parte de la semilla descansa en una
clasificación no verificada, y la clasificación de codeshare afecta
precisamente las proporciones dentro de la ruta, que son el único contenido de
la semilla.

Eso no invalida el método, pero obliga a tres cosas: medir y publicar este
porcentaje en **cada** captura; contrastar el conteo de vuelos de la semilla
contra la columna `vuelos` de `REG INT`, que es una verificación independiente
y gratuita; y tratar una ruta con alta proporción de `Unknown` como candidata a
`N/D` aunque el ajuste converja.

## 10. Qué tan bueno es el estimador, medido

`src/analytics/route_carrier_backtest.py` esconde el split publicado por T-100,
lo reconstruye desde las dos marginales y reporta el error por varios cortes.
Rutas de un solo operador excluidas: el ajuste las recupera por construcción y
aplanarían todos los promedios.

> **Qué es y qué no es este experimento.** La semilla sale del **mismo panel
> observado** que produce las marginales: son los vuelos o asientos que T-100
> publica para esas mismas celdas. Es decir, la semilla tiene cobertura
> perfecta, sin muestreo, sin error de clasificación de codeshare, sin
> operadores ausentes y sin desajuste de crosswalk. Por eso el resultado es
> **una prueba favorable del método bajo condiciones ideales**: mide cuánto
> error queda por la no identificabilidad del IPF cuando todo lo demás está
> bien.
>
> **No es** la precisión esperable de una captura real de AeroDataBox, que
> añade muestreo de siete días, ~18 % de registros con `codeshareStatus`
> desconocido (medido en el sondeo), operadores sin mapear y equivalencias
> ciudad ↔ aeropuerto. **Tampoco es** la precisión esperable en MAD, BOG o NRT:
> son mercados fuera del panel, con frecuencias semanales bajas y estructuras
> de competencia distintas. Las cifras de abajo son una **cota inferior del
> error**, no una predicción.

### Resultado global (rutas competidas)

| Año | Semilla | Ponderado | Sin ponderar | p90 | Máximo | Error en pasajeros | Rutas |
|---|---|---:|---:|---:|---:|---:|---:|
| 2025 | vuelos | **1.96 pp** | 2.68 pp | 6.08 pp | 32.52 pp | 5.92 % | 357 |
| 2026 (ene–may) | vuelos | 1.90 pp | 2.56 pp | 5.67 pp | 23.90 pp | 5.71 % | 314 |
| 2026 (ene–may) | asientos | **1.37 pp** | 1.99 pp | 4.39 pp | 20.88 pp | 4.13 % | 314 |

El 1.96 pp reproduce el 1.98 pp citado en los reportes previos. Pero es un
promedio **ponderado por pasajeros**: la ruta típica tiene 2.68 pp de error, una
de cada diez supera 6 pp y el máximo del panel llega a 32 pp.

Una semilla de **asientos** es sensiblemente mejor que una de vuelos (1.37 pp
contra 1.90 pp). AeroDataBox puede producirla: el FIDS trae matrícula y modelo,
y `numSeats` está en la ficha de aeronave.

### Por tamaño de mercado (2025, ponderado)

| Cuartil | Error ponderado | Sin ponderar | p90 | Rutas |
|---|---:|---:|---:|---:|
| Q4 más grandes | 1.59 pp | 1.70 pp | 4.02 pp | 83 |
| Q3 | 2.20 pp | 2.26 pp | 4.96 pp | 106 |
| Q2 | 3.16 pp | 3.26 pp | 7.51 pp | 151 |
| **Q1 más pequeñas** | **3.84 pp** | 4.13 pp | **10.40 pp** | 199 |

El error se **duplica largo** entre el cuartil más grande y el más pequeño.

### Por competencia (2025, ponderado)

| Operadores en la ruta | Error ponderado | Rutas |
|---|---:|---:|
| 2 | 2.63 pp | 321 |
| 3 | 1.94 pp | 122 |
| 4 o más | 1.57 pp | 64 |

### Por distancia (2025, ponderado)

| Banda | Error ponderado | Rutas | Observaciones |
|---|---:|---:|---:|
| < 1,500 km | 2.00 pp | 107 | 1,923 |
| 1,500–2,500 km | 1.87 pp | 152 | 2,577 |
| 2,500–3,500 km | 2.03 pp | 86 | 1,520 |
| > 3,500 km | 1.68 pp | 9 | 85 |

**Esta tabla no autoriza extrapolar.** La banda más larga tiene nueve rutas.
MEX–MAD son ≈ 9,050 km y MEX–NRT ≈ 11,300 km: ninguna ruta de T-100 se
aproxima. La distancia no está midiendo lo que importaría en Europa o Asia
—frecuencia semanal baja, un solo operador dominante, estacionalidad marcada—.

**La medición que sí valdría** es el mismo experimento con una semilla real de
AeroDataBox sobre el cubo internacional: ahí el subcubo estadounidense da el
error del estimador **con** el ruido de captura incluido, sobre las mismas
celdas que se van a publicar. Esa medición requiere una captura y todavía no
existe.

### Aeroméxico en particular

| Año | Ponderado | Sin ponderar | p90 | Máximo | Error en pasajeros |
|---|---:|---:|---:|---:|---:|
| 2025 | 1.97 pp | 2.71 pp | 5.84 pp | 18.89 pp | 5.96 % |
| 2026 (ene–may) | 2.05 pp | 2.55 pp | 5.13 pp | 13.50 pp | 6.64 % |

### Dónde caerían los mercados internacionales

Cuantiles de pasajeros por ruta y mes en el panel competido de T-100 2026:
p25 = 3,378; mediana = 8,855; p75 = 15,282; p90 = 26,341; máximo = 57,563.

Contra los mercados internacionales sin pasajeros (2026Q2, una dirección,
dividido entre tres meses):

| Mercado | Pasajeros/mes aprox. | Estrato T-100 equivalente |
|---|---:|---|
| MEXICO → MADRID | 47,175 | por encima del p90 |
| MEXICO → BOGOTA | 29,800 | ≈ p90 |
| MEXICO → PARIS | 24,602 | Q4 |
| MEXICO → TORONTO | 15,136 | frontera Q3/Q4 |
| MEXICO → SAO PAULO | 12,660 | Q3 |
| MEXICO → TOKYO | 9,671 | ≈ mediana |

Los mercados grandes caen en estratos con 1.6–2.2 pp de error. Los mercados
delgados de Centroamérica y el Caribe caerán en Q1/Q2: **3.0–3.8 pp ponderado,
p90 hasta 10 pp**. Esa es la expectativa honesta, y sigue siendo una
extrapolación desde un mercado transfronterizo corto.

---

## 11. Estado del inventario internacional, reverificado

Payload vigente `prototypes/vuelos/vuelos_revision.html`
(SHA-256 `3175c6aa0c560278…`, generado en el commit `fe0b548`), trimestre
2026Q2: **73 mercados internacionales, 32 sin pasajeros.**

| Estado de operación | Mercados | Qué significa |
|---|---:|---|
| `assigned_slot_not_flown` | 25 | slots AICM de vuelos AM: **programación**, no operación verificada |
| `operated_observed` | 5 | vuelos observados, pero la fuente retenida **no trae pasajeros** |
| `scheduled_from_dated_release` | 1 | `CDG<>MTY`, comunicado OMA |
| `documented_operating_route_count_unavailable` | 1 | `MAD<>MTY`, ruta documentada sin conteo |

**Corrección a un reporte previo.** Los cinco `operated_observed` sin pasajeros
—`BOG<>MEX`, `CLO<>MEX`, `CTG<>MEX`, `MDE<>MEX` (Aerocivil) y `LHR<>MEX`
(CAA)— no son un artefacto de la regla de completitud bidireccional de
`src/dashboard/international_routes.py`. Son un hueco de fuente: en
`data/gold/fact_international_route_observations.parquet`, **las 147 filas de
Aerocivil y las 2 de CAA tienen `passengers` nulo**; solo traen `departures`.
ANAC sí trae pasajeros (148 de 149 filas). El reporte del 2026-09-21 afirmaba
lo contrario y queda corregido aquí.

---

## 12. Límites de validez y criterio para publicar `N/D`

Se publica `N/D`, no un número, cuando:

- la puerta de aceptación devuelve `reject`;
- el ajuste no converge ni con soporte temporal hasta dos meses;
- la ruta o el operador no están en el soporte observado del mes ni en el
  prestado;
- las marginales no son compatibles (`InfeasibleMarginsError`);
- la fuente observada existe pero no publica la métrica, como Aerocivil y CAA
  con pasajeros;
- el registro es programación (`assigned_slot_not_flown`) y se pretendería
  presentarlo como operación.

Nunca se convierte un faltante en cero, ni se reparte un agregado entre rutas o
aerolíneas sin evidencia.

Límites que permanecen aunque todo lo demás salga bien:

- la celda es estimación, no observación, salvo donde exista fuente observada;
- el error medido es de un mercado transfronterizo corto y **no es garantía**
  para Europa, Asia o Latinoamérica;
- el rango `low/high` mide sensibilidad al peso del soporte prestado, no
  incertidumbre estadística;
- una activación retrospectiva en el dashboard **no** cambia
  `historically_eligible_at_2026_07_13` ni activa `flight_evidence_v1` ni el
  Analysis Agent;
- el contenido crudo del proveedor está sujeto a la retención de su plan, no
  entra a Git y no se republica.

---

## 13. Archivos y fuentes exactas

### Código

| Ruta | Papel |
|---|---|
| `src/analytics/route_carrier.py` | `fit_ipf`, `estimate_route_carrier`, soporte temporal, `build_seed_from_flights`, marginales nacionales, `backtest_against_t100` |
| `src/analytics/seed_acceptance.py` | puerta `seed_acceptance_v3` |
| `src/analytics/route_carrier_backtest.py` | backtest estratificado por operador, competencia, tamaño y distancia |
| `src/ingest/afac/margins.py` | parser de `REG NAC` y de la base larga DATATUR |
| `src/ingest/aerodatabox/flights.py` | adaptador nacional de la semilla |
| `src/ingest/aerodatabox/international.py` | adaptador internacional de la semilla |
| `src/ingest/aerodatabox/international_cli.py` | `plan`, `probe`, `sweep` |
| `src/dashboard/international_routes.py` | composición de la red internacional del dashboard |

### Datos

| Ruta | Contenido |
|---|---|
| `data/reference/afac_od_nacional_regular.csv` | marginal de ruta nacional |
| `data/reference/afac_carrier_domestic.csv` | marginal de aerolínea nacional |
| `data/reference/afac_city_iata_crosswalk.csv` | 58 aeropuertos nacionales ↔ ciudad AFAC |
| `data/reference/afac_carrier_crosswalk.csv` | nombre AFAC ↔ `carrier_key` |
| `data/reference/aeromexico_aircraft_seat_capacity.csv` | modelo ↔ asientos, con rango |
| `data/gold/fact_route_traffic.parquet` + `dim_route.parquet` | T-100 |
| `data/gold/fact_international_route_observations.parquet` | observaciones internacionales retenidas |
| `data/silver/afac_monthly_stats.parquet` (respaldo privado) | marginal de aerolínea, nacional e internacional |
| `snapshot/data/bronze/afac_research/afac_research_city_pairs_*.xlsx` (respaldo privado) | libros O-D con `REG INT` |

### Reportes de etapa relacionados

- `docs/etapas/aerodatabox-ruta-aerolinea-revision-20260919.md`
- `docs/etapas/vuelos-capacidad-ocupacion-estimada-20260920.md`
- `docs/etapas/afac-rutas-investigacion-20260908.md`
- `docs/etapas/aerodatabox-internacional-investigacion-20260921.md`
- `docs/pasajeros-por-ruta-y-aerolinea.md`
- `docs/estimador-ruta-aerolinea.md`
- `docs/cloud-development.md` (frontera de licencia del proveedor)

### Evidencia externa

- AFAC, estadística operacional origen–destino:
  <https://www.gob.mx/afac/acciones-y-programas/estadistica-mensual-operativa-monthly-traffic-statistics>
- AFAC, libro O-D julio 2026:
  <https://www.gob.mx/cms/uploads/attachment/file/1100280/sase-julio-2026-27082026.xlsx>
- AFAC, resumen por empresa julio 2026:
  <https://www.gob.mx/cms/uploads/attachment/file/1100279/resumen-julio-2026-27082026.xlsx>
- AFAC, boletín por país julio 2026:
  <https://www.gob.mx/cms/uploads/attachment/file/1100282/stats-por-pais-es-jul2026-27082026.pdf>
- AeroDataBox, especificación OpenAPI 1.15.3.0:
  <https://doc.aerodatabox.com/docs/openapi-direct-v1.yaml>
- AeroDataBox, tarifario y términos: <https://aerodatabox.com/pricing/> ·
  <https://aerodatabox.com/terms>

---

## 14. Secuencia para extender a internacional

En este orden. Ninguna etapa autoriza la siguiente por sí sola.

| # | Etapa | Estado |
|---|---|---|
| 1 | Probar universo compartido de las dos marginales internacionales | **hecho** (§9.3, cero diferencia en 7 meses) |
| 2 | Establecer la base de conteo de OFOD con evidencia | **hecho** (§3: sin definición publicada; evidencia empírica de comportamiento por tramo) |
| 3 | Evaluar T-100 celda a celda y fijar su papel | **hecho** (§9.4: subconjunto observado comparable, 0.9999, mediana 0.53 %) |
| 4 | Confirmar que el proveedor trae la red internacional | **hecho** (§9.6: 54 mercados de Grupo Aeroméxico por 8 unidades) |
| 5 | Parser productivo de `REG INT` con pruebas | pendiente, sin API |
| 6 | Crosswalks de ciudad y de aerolínea, revisados a mano, con conteo de no mapeados por rutas, pasajeros y aerolíneas | pendiente, sin API |
| 7 | Puerta de aceptación internacional, usando `vuelos` de `REG INT` como contraste | pendiente, sin API |
| 8 | Captura mensual de la semilla en los meses que la ventana permita | pendiente, **con API** |
| 9 | Ajuste, y backtest del subcubo estadounidense con la semilla real | pendiente |
| 10 | Vista separada de revisión humana antes de tocar el mapa principal | pendiente |

Las etapas 5 a 7 no consumen unidades y son las que faltan para que la etapa 8
tenga sentido: capturar una semilla sin crosswalk ni puerta produce filas que no
se pueden fitear.
