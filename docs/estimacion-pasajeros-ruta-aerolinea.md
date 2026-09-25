# Estimación de pasajeros por ruta y aerolínea · método canónico

Fecha: 21 de septiembre de 2026, ampliado el 22 de septiembre de 2026 con los
dos crosswalks, la puerta de aceptación internacional, el adaptador al
contrato del IPF y el plan de captura, y el 23 de septiembre de 2026 con la
primera captura internacional real (2026M04) y su ajuste.
Estado: documento canónico del método. Describe lo que **ya está en producción**
para el mercado nacional y el estimador internacional **ajustado sobre una
captura real, pendiente de revisión humana**. No autoriza por sí solo ninguna
publicación, activación de evidencia ni consumo de API.

**Veredicto sobre la extensión internacional: la primera captura mensual
(2026M04, 1,588 unidades) pasó la puerta con veredicto `review`, el ajuste
convergió y el contraste fuera de muestra contra T-100 da 6.3 % de error
ponderado por celda (6.9 % para Aerovías + Connect) (§9.11).** Mayo, junio y
julio se capturaron después (4,812 unidades) y los cuatro meses convergen
(§9.12). Nada se ha publicado: el resultado espera revisión humana antes de
tocar el dashboard.
Las dos marginales internacionales de AFAC describen el mismo universo —cero
pasajeros de diferencia en los siete meses de 2026 leídos de la misma edición
(§9.3)—. La captura real destapó y corrigió cuatro problemas que ningún ensayo
sin datos podía ver: aeropuertos principales mal mapeados, vuelos con escala
en México, aerolíneas regionales reportadas bajo la marca, y marginales
mayores que la capacidad visible de sus rutas (§9.11.2). El `codeshareStatus`
desconocido resultó ser 1.1 % en la captura mensual, no el 17.6 % del sondeo
de un día (§9.11.1).

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

### 9.5 Piezas nuevas — estado tras la ronda de construcción del 2026-09-22

| Pieza | Análogo nacional | Estado |
|---|---|---|
| Parser de `REG INT` | `read_route_workbook` en `src/ingest/afac/margins.py` | **hecho**: `src/ingest/afac/international_margins.py`, 14 pruebas. Produce `afac_od_internacional_regular.csv` (6,853 filas, 979 pares) y `afac_carrier_international.csv` (434 filas, 62 empresas), reconcilia en cada reconstrucción |
| Crosswalk ciudad AFAC internacional ↔ IATA | `afac_city_iata_crosswalk.csv` (58 aeropuertos) | **hecho**: `src/ingest/afac/international_crosswalks.py` + `afac_international_city_overrides.csv` (54 reglas revisadas a mano) → `afac_international_city_iata_crosswalk.csv`, **178 etiquetas de ciudad, 241 aeropuertos, 0 sin resolver, 100 % de pasajeros cubiertos** en los 7 meses. 10 pruebas |
| Crosswalk aerolínea AFAC internacional ↔ IATA/ICAO | `afac_carrier_crosswalk.csv` (2 filas) | **hecho**: `afac_international_carrier_crosswalk.csv`, 62 aerolíneas con tres niveles de confianza (`resolved`/`probable`/`unresolved`, ver §9.5.1), **99.7–99.9 % de pasajeros cubiertos** por mes |
| Puerta de aceptación internacional | `seed_acceptance_v3` | **hecho**: `src/analytics/international_route_carrier.py`, `international_seed_acceptance_v1`, 9 comprobaciones, 20 pruebas + ensayo sobre datos reales (§9.6.1) |
| Semilla internacional | `flights.py` | **existe y está probada en vivo**: `src/ingest/aerodatabox/international.py`, ahora con dos diagnósticos adicionales (`codeshare_unknown`, `status_incomplete`) que la puerta consume |
| Adaptador semilla → contrato IPF | — | **hecho**: `build_international_seed`, `build_international_margins`, mismo grano mensual y direccional que `src/analytics/route_carrier.py` |
| Agregación Grupo Aeroméxico post-ajuste | — | **hecho**: `group_aeromexico()`, suma solo después del ajuste, conserva el linaje de cada filial |
| Exclusión de doble conteo con T-100 | — | **hecho**: `observed_cells_to_exclude()`, marca `display_source` sin sumar nunca observado + estimado |
| Verificación offline de captura (`preflight`) | — | **hecho**: subcomando `preflight` en `international_cli.py`, 8 pruebas cubren credencial, reanudación, retención y tope duro |

#### 9.5.1 Los tres niveles de confianza del crosswalk de aerolínea

Ninguna aerolínea se mapea por parecido de nombre. Cada fila del crosswalk
declara su nivel:

- **`resolved`** (34 aerolíneas, cubren la inmensa mayoría de los pasajeros):
  el código IATA/ICAO está confirmado por un artefacto de este repositorio
  —`config/carrier_crosswalk.csv`, el crosswalk nacional, o el propio sondeo
  del 2026-09-10, que observó el código en vivo (`IATA:UA`, `IATA:AA`,
  `IATA:DL`, `IATA:CM`, `IATA:AV`, `IATA:AC`, `IATA:MQ`, `IATA:IB`, `IATA:AF`,
  `IATA:Q6`, `IATA:LA`)—.
- **`probable`** (23 aerolíneas): identidad documentada externamente (una sola
  aerolínea de ese nombre opera hacia México, denominación social inequívoca
  en la etiqueta de AFAC) pero **sin confirmar todavía dentro de este
  repositorio**. Cuentan para la cobertura porque negarles una identidad
  conocida sería peor que usarla con la etiqueta correcta; la primera captura
  real that muestre su código en el sondeo los sube a `resolved` o revela que
  el código supuesto no aparece.
- **`unresolved`** (5 aerolíneas, ≤0.07 % de pasajeros cada una): identidad
  genuinamente incierta — `Aerus` opera sin código IATA publicado, `SKY
  Airline Perú` y `Volaris El Salvador` son filiales regionales sin código
  confirmado, `Breeze Airways` tiene un código que podría chocar con el
  prefijo histórico de Mexicana, `Orbest` no se verificó. **Nunca entran a la
  semilla**; sus pasajeros AFAC quedan fuera de la marginal de aerolínea y se
  reportan como brecha de cobertura, no se reparten entre vecinos.

Un código que dos aerolíneas `resolved`/`probable` reclamaran a la vez
—`ambiguous_operator_codes()`— tampoco se resuelve por preferencia: se
reporta y bloquea el ajuste hasta que la revisión humana lo deshaga.

**Corrección durante la construcción**: la primera pasada tenía la etiqueta
`United Airlines` en el crosswalk contra `United Airlines, Inc.` en la
marginal, un desajuste de escritura que descartaba en silencio el 9.5 % de los
pasajeros internacionales. El nuevo guardia `carriers_missing_from_crosswalk()`
compara los nombres del margen contra los del crosswalk y lo reporta como
fallo ruidoso en vez de dejarlo pasar como cobertura baja sin explicación; ya
tiene una prueba dedicada. También apareció y se corrigió `LIÈGE` (con acento
grave en la fuente AFAC) escrita sin acento en el override, que dejaba sin
resolver una etiqueta y bajaba la cobertura de rutas a 99.90 %; corregida,
la cobertura de rutas es **100 % en los 7 meses**.

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

### 9.7 El parser de las marginales internacionales

`src/ingest/afac/international_margins.py` construye las dos marginales desde
los libros de AFAC y **reconcilia en cada reconstrucción**. No estima nada.

```
uv run python -m src.ingest.afac.international_margins \
    --year 2026 --routes <libro O-D> --carriers <resumen por empresa> [--dry-run]
```

Salida sobre la edición de julio de 2026:

| Artefacto | Contenido |
|---|---|
| `data/reference/afac_od_internacional_regular.csv` | 6,853 filas mes × par, **979 pares direccionales**, con ciudad y país de ambos extremos, vuelos y pasajeros |
| `data/reference/afac_carrier_international.csv` | 434 filas mes × empresa, **62 empresas**: 5 nacionales y 57 extranjeras, etiquetadas con su bloque |

Las dos decisiones que el parser toma y que, de hacerse mal, producirían una
tabla completa de cifras equivocadas en vez de un error:

1. **Offsets propios.** `REG INT` tiene cuatro columnas clave, no dos, así que
   los bloques de vuelos y pasajeros empiezan en 4 y 17 en lugar de 2 y 15.
   Leerla con los offsets domésticos devuelve **kilogramos de carga** donde
   deberían ir pasajeros. El parser valida el encabezado y se niega a leer un
   libro con layout doméstico.
2. **Subtotales regionales excluidos.** El bloque de empresas extranjeras
   intercala `Total Estadounidenses`, `Total Europeas`, `Total Asiáticas`…
   entre las aerolíneas. Sumar el bloque sin quitarlos **duplica cada pasajero
   extranjero**. Se excluyen por forma, no por número de fila, porque los
   números de fila cambian con cada edición.

El total del bloque (`T     o     t     a     l`, con espaciado tipográfico) se
distingue de un subtotal regional quitando todos los espacios: solo el primero
colapsa exactamente a `TOTAL`. Las marcas de nota al pie (`Spirit Airlines**`)
se retiran del nombre para que una misma aerolínea no se bifurque en dos
identidades entre meses.

`--dry-run` parsea y reconcilia sin escribir. Si algún mes queda fuera de
tolerancia el comando termina con código 1 y avisa que hay que comprobar que
ambos libros sean de la **misma edición**: ese es el error que produce las
diferencias de §9.3, y el parser lo convierte en un fallo visible en vez de un
dato silenciosamente revisado.

Estos dos CSV alimentan ahora los crosswalks (§9.5) y la puerta de aceptación
(§9.8): dejaron de ser insumo huérfano.

### 9.8 La puerta de aceptación internacional

`src/analytics/international_route_carrier.py`, versión
`international_seed_acceptance_v1`, 20 pruebas. Recibe una captura cruda de
`src/ingest/aerodatabox/international.py`, la pasa por los dos crosswalks
(§9.5) y produce `(seed, rejected)` en el contrato exacto que
`src/analytics/route_carrier.py::estimate_route_carrier()` espera
(`period_id, route_key, carrier_key, weight`, con `route_key` en vocabulario
de ciudades AFAC, nunca IATA), más dos columnas de diagnóstico
(`codeshare_unknown`, `status_incomplete`) que solo la puerta consume.

Nueve comprobaciones, cada una reportada como un `Finding` con severidad
propia (`reject` bloquea el ajuste, `review` lo permite con aviso, `note` es
informativo) para que quede claro **cuál** propiedad falló:

| # | Comprobación | Qué detecta | Severidad |
|---|---|---|---|
| 1 | Duplicados | dos filas repiten periodo, ruta y operador | reject |
| 2 | Direcciones perdidas | un mercado capturado solo en un sentido (una ruta internacional se ve como salida en un extremo y como llegada en el otro; puede faltar uno) | review |
| 3 | Operadores ambiguos | un código IATA/ICAO reclamado por dos aerolíneas revisadas | reject |
| 3b | Aeroméxico sin separar | vuelos `AM` sin modelo de aeronave, no repartibles entre Aerovías/Connect | review, contado y excluido |
| 3c | Operadores sin revisar | código que no aparece en el crosswalk (§9.5) | review, contado y excluido |
| 4 | Codeshare sin resolver | proporción de la semilla con `codeshareStatus=Unknown`; >25 % rechaza, 5–25 % avisa (medido en vivo: 17.6 %, §9.6) | reject / review |
| 5 | Cobertura de rutas | % de pasajeros AFAC dentro de rutas que la semilla cubre; <95 % rechaza | reject / review |
| 5b | Cobertura de aerolíneas | igual, por aerolínea | reject / review |
| 6 | Márgenes incompatibles | `column_scale` fuera de ±5 % | reject |
| 7 | Soporte estructural inviable | una ruta o aerolínea con pasajeros AFAC y sin ninguna fila de oferta en la semilla (lo que el IPF lanzaría como `InfeasibleMarginsError`, detectado antes de ajustar) | reject |
| 8 | Vuelos por encima de AFAC | rutas donde la semilla ve más vuelos que los que `REG INT` publica: señal de programación en vez de operación | review |
| 8b | Razón semilla/AFAC | razón global de vuelos semilla ÷ AFAC, informativa | note |
| 9 | Estado no operado | % de la semilla sin un `status` que confirme vuelo completado | note |

Umbrales calcados de `seed_acceptance_v3` (nacional) para que ambos veredictos
signifiquen lo mismo: cobertura ≥95 %, `column_scale` ±5 %.

#### 9.8.1 Ensayo con datos reales, sin capturar nada

`python -m src.analytics.international_route_carrier --periods <meses>`
sustituye la semilla real (todavía inexistente) por T-100 reconstruido con la
misma forma —vuelos por ruta y operador— para ejercitar todo el tubo sobre
datos reales sin gastar una unidad: crosswalks, grano, contratos, hallazgos.
T-100 solo cubre México–Estados Unidos, así que **se espera que la puerta lo
rechace por cobertura**; eso es lo que se verifica, no una simulación de la
captura completa:

```
$ uv run python -m src.analytics.international_route_carrier --periods 2026M04,2026M05

2026M04  veredicto: REJECT  (international_seed_acceptance_v1)
  cobertura rutas       62.92%
  cobertura aerolineas  84.16%
  column_scale          0.7489
  REJECT cobertura_rutas: 62.92% ... umbral 95%
  REJECT cobertura_aerolineas: 84.16% ... umbral 95%
  REJECT margenes_incompatibles: column_scale 0.7489 fuera de ±5%
  NOTE   razon_vuelos_semilla_afac: la semilla contiene 0.99 veces los
         vuelos que AFAC publica en las rutas comparables
```

El `REJECT` es el resultado correcto — confirma que la puerta distingue una
semilla parcial de una completa — y la razón semilla/AFAC de 0.99 confirma que
el adaptador reproduce fielmente el volumen de vuelos donde sí tiene datos.
Esto **no sustituye una captura real** de AeroDataBox: mide la plomería, no la
semilla.

### 9.9 Agregación Grupo Aeroméxico y exclusión de doble conteo con T-100

Dos funciones, aplicadas **después** del ajuste, nunca antes:

- `group_aeromexico(estimate)`: suma `AEROMEXICO` + `AEROMEXICO_CONNECT` en una
  fila `AEROMEXICO_GROUP` / *Grupo Aeroméxico*, conservando las dos filas
  originales para que el linaje interno no se pierda. Cada filial ya fue
  ajustada por separado contra su propio total publicado por AFAC (§8); sumar
  antes de ajustar les regalaría pasajeros de otras aerolíneas.
- `observed_cells_to_exclude(estimate, observed)`: marca cada celda ajustada
  con `display_source = "observed_t100"` o `"estimated"`. T-100 nunca entra al
  ajuste como fila, columna ni peso (§9.4); esta función es la única vía por
  la que puede tocar el resultado, y solo para decidir **qué se muestra**, no
  para modificar la cifra ajustada. Una celda con `display_source
  = observed_t100` se publica desde T-100; su valor ajustado se conserva como
  diagnóstico y su diferencia contra T-100 es la métrica de calidad del
  estimador en esa celda. Las dos fuentes nunca se suman en el mismo total.

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
| `src/ingest/aerodatabox/international.py` | adaptador internacional de la semilla, con diagnósticos `codeshare_unknown`/`status_incomplete` |
| `src/ingest/aerodatabox/international_cli.py` | `plan`, `probe`, `sweep` (con `--tag`), `preflight` |
| `src/ingest/afac/international_margins.py` | parser de `REG INT` y del resumen internacional por empresa, con conciliación |
| `src/ingest/afac/international_crosswalks.py` | los dos crosswalks internacionales, cobertura por mes, casos sin resolver |
| `src/analytics/international_route_carrier.py` | puerta de aceptación internacional, adaptador al contrato IPF, `group_aeromexico`, `observed_cells_to_exclude` |
| `src/dashboard/international_routes.py` | composición de la red internacional del dashboard |

### Datos

| Ruta | Contenido |
|---|---|
| `data/reference/afac_od_nacional_regular.csv` | marginal de ruta nacional |
| `data/reference/afac_carrier_domestic.csv` | marginal de aerolínea nacional |
| `data/reference/afac_city_iata_crosswalk.csv` | 58 aeropuertos nacionales ↔ ciudad AFAC |
| `data/reference/afac_carrier_crosswalk.csv` | nombre AFAC ↔ `carrier_key` |
| `data/reference/aeromexico_aircraft_seat_capacity.csv` | modelo ↔ asientos, con rango |
| `data/reference/afac_od_internacional_regular.csv` | marginal de ruta internacional (`REG INT`), 6,853 filas |
| `data/reference/afac_carrier_international.csv` | marginal de aerolínea internacional, 434 filas, 62 empresas |
| `data/reference/afac_international_city_overrides.csv` | 54 reglas de crosswalk de ciudad revisadas a mano, con motivo |
| `data/reference/afac_international_city_iata_crosswalk.csv` | 178 etiquetas de ciudad → 241 aeropuertos, generado |
| `data/reference/afac_international_carrier_crosswalk.csv` | 62 aerolíneas → IATA/ICAO/`carrier_key`, tres niveles de confianza |
| `data/reference/afac_international_carrier_families.csv` | Familias revisadas que se ajustan como una columna (`US_NETWORK`, `AVIANCA_GROUP`, `LATAM_GROUP`), con motivo por fila (§9.11.2) |
| `data/gold/fact_route_traffic.parquet` + `dim_route.parquet` | T-100 |
| `data/gold/fact_international_route_observations.parquet` | observaciones internacionales retenidas |
| `data/silver/afac_monthly_stats.parquet` (respaldo privado) | marginal de aerolínea, nacional e internacional |
| `snapshot/data/bronze/afac_research/afac_research_city_pairs_*.xlsx` (respaldo privado) | libros O-D con `REG INT` |
| `snapshot/data/bronze/afac_research/afac_research_airline_summary_*.xlsx` (respaldo privado) | resumen por empresa, bloques internacionales |

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
| 5 | Parser productivo de `REG INT` con pruebas | **hecho**, sin API (§9.7) |
| 6 | Crosswalks de ciudad y de aerolínea, revisados a mano | **hecho**, sin API (§9.5, §9.5.1): 100 % de rutas, 99.7–99.9 % de aerolíneas por pasajeros |
| 7 | Puerta de aceptación internacional, usando `vuelos` de `REG INT` como contraste | **hecho**, sin API (§9.8): ensayado sobre T-100 real (§9.8.1) |
| 7b | Adaptador semilla → contrato IPF, agregación Grupo Aeroméxico y exclusión de doble conteo con T-100 | **hecho**, sin API (§9.9) |
| 7c | Verificación offline de la captura (credencial, reanudación, retención, tope duro) | **hecho**, sin API (§9.10.2) |
| 8 | Captura mensual de la semilla en los meses que la ventana permita | **hecho para 2026M04** (§9.11): 1,588 unidades |
| 9 | Ajuste, y backtest del subcubo estadounidense con la semilla real | **hecho para 2026M04** (§9.11): convergió; 6.3 % de error ponderado contra T-100 |
| 10 | Vista separada de revisión humana antes de tocar el mapa principal | **hecho**: vistas generadas (§9.11.5) y aprobación del operador para integrar (2026-09-25) |
| 12 | Integración a Vuelos (generador y vista de revisión) | **hecho** (§9.13); el dashboard integrado publicado requiere su propia autorización |
| 11 | Más meses (mayo–julio) para estabilidad y soporte temporal | **hecho** (§9.12): 4,812 unidades; los cuatro meses convergen |

Las etapas 1 a 9 están cerradas para abril. Ninguna activa nada en el
dashboard ni en el Analysis Agent: la etapa 10 requiere una instrucción
explícita separada.

### 9.10 Plan de captura, listo para ejecutar

#### 9.10.1 Qué aeropuertos y meses

`data/reference/afac_international_city_iata_crosswalk.csv` da 37 aeropuertos
mexicanos con tráfico internacional. Priorizados por pasajeros internacionales
AFAC acumulados (ene–jul 2026), **6 aeropuertos concentran el 88.6 %**:

| Grupo | Aeropuertos | Pasajeros internacionales | Acumulado |
|---|---|---:|---:|
| **Núcleo** | CUN, MEX, GDL, SJD, PVR, MTY | 30.9 M | 88.6 % |
| Resto (31) | ACA, AGU, BJX, CUL, CUU, CZM, DGO, HMO, HUX, LAP, LTO, MID, MLM, MZT, NLU, OAX, PBC, PXM, QRO, SLP, TAM, TIJ, TLC, TPQ, TQO, TRC, UPN, VER, ZCL, ZIH, ZLO | 4.0 M | 11.4 % |

Diseño híbrido: **núcleo en mes completo** (concentra casi 9 de cada 10
pasajeros y justifica el gasto por ruta) y **resto en muestra ponderada de
siete días** (mismo mecanismo de ponderación por día de semana que el barrido
nacional, §3 del documento nacional). Todas las aerolíneas de una misma ruta
quedan medidas en la misma ventana porque cada ruta internacional tiene
exactamente un extremo mexicano — la condición que el IPF necesita (§9.10 nota
al pie de §7).

Meses candidatos y su margen en la ventana histórica (hipótesis de 210 días,
**no confirmada**, hoy 2026-09-22):

| Mes | Costo núcleo (mes completo) | Costo resto (7 días) | Total | Margen en la ventana |
|---|---:|---:|---:|---|
| 2026M03 | 744 | 868 | **1,612** | **5 días** — se sale el 27-sep-2026 |
| 2026M04 | 720 | 868 | **1,588** | 36 días |
| 2026M05 | 744 | 868 | **1,612** | 67 días |
| 2026M06 | 720 | 868 | **1,588** | 98 días |
| 2026M07 | 744 | 868 | **1,612** | 128 días |

**Recomendación: 2026M04**, no marzo. Marzo tiene solo 5 días de margen bajo
una hipótesis de ventana **no verificada** contra el panel de la suscripción;
si la ventana real fuera más corta, marzo podría fallar a mitad de captura. Un
mes con margen amplio permite reintentar sin presión si la puerta lo rechaza
y hay que ampliar la muestra.

#### 9.10.2 Verificación offline, ejecutada

`uv run python -m src.ingest.aerodatabox.international_cli preflight` — nuevo
subcomando, 8 pruebas — comprueba cuatro propiedades sin emitir una sola
solicitud HTTP:

```
$ uv run python -m src.ingest.aerodatabox.international_cli preflight
credencial     OK   proveedor RapidAPI, cabeceras ['x-rapidapi-host', 'x-rapidapi-key']
reanudacion    OK   una ventana en cache no se vuelve a comprar
retencion      OK   contenido del proveedor de mas de 7 dias eliminado (1 archivo(s))
tope duro      OK   un plan de 24 unidades con tope 8 se rechaza

Todo listo. Ninguna unidad consumida en esta comprobacion.
```

- **Credencial**: `RAPIDAPI_KEY` presente, `AERODATABOX_API_KEY` ausente (si
  ambas existieran, la directa tendría prioridad y elegiría el host
  equivocado); el adaptador resuelve a RapidAPI. Ningún valor se imprime,
  registra ni compara — solo el nombre del proveedor elegido.
- **Reanudación**: una ventana ya en caché no se vuelve a comprar
  (`test_a_resumed_sweep_buys_nothing_it_already_has`).
- **Retención**: contenido de más de 7 días se elimina y no se reutiliza
  (`test_expired_provider_content_is_deleted_and_not_reused`).
- **Tope duro**: un plan que excede el presupuesto se rechaza antes de la
  primera llamada, código de salida 2
  (`test_the_budget_refuses_before_the_first_call_not_after`).
- **Deduplicación**: no es una propiedad de arranque — se verifica por
  construcción del `groupby` en `normalise()`/`routes_by_operator()`
  (`src/ingest/aerodatabox/international.py`) y por la comprobación 1
  (`duplicados`) de la puerta (§9.8), que rechaza cualquier fila repetida que
  se hubiera colado.
- **Dos capturas del mismo mes no se pisan**: `--tag` en el subcomando
  `sweep` escribe `aerodatabox_international_seed_<mes>_<tag>.parquet`, para
  que la captura del núcleo y la del resto convivan
  (`test_two_sweeps_of_one_month_do_not_overwrite_each_other`).

#### 9.10.3 Comandos preparados, no ejecutados

Dos pasadas para el mes recomendado, cada una con su propio tope duro y su
propia etiqueta de Silver:

```
uv run python -m src.ingest.aerodatabox.international_cli sweep 2026M04 \
    --airports CUN,GDL,MEX,MTY,PVR,SJD \
    --budget 720 --tag nucleo

uv run python -m src.ingest.aerodatabox.international_cli sweep 2026M04 --days 7 \
    --airports ACA,AGU,BJX,CUL,CUU,CZM,DGO,HMO,HUX,LAP,LTO,MID,MLM,MZT,NLU,OAX,PBC,PXM,QRO,SLP,TAM,TIJ,TLC,TPQ,TQO,TRC,UPN,VER,ZCL,ZIH,ZLO \
    --budget 868 --tag resto
```

Costo máximo combinado: **1,588 unidades** para 2026M04. El workflow
equivalente y auditable en el repositorio privado es
`.github/workflows/aerodatabox-international-sweep.yml`
(`salvamalfa/aeromexico-tracker-data`), que ejecuta el mismo `preflight` y las
mismas dos pasadas por despacho manual, con el `ref` del commit revisado
escrito en el resumen de la corrida y el contenido crudo borrado al terminar
en un paso `if: always()`.

**Ejecutados el 22–23 de septiembre de 2026 desde la sesión**, con
autorización explícita del operador, tras un canario de 4 unidades (MEX, 1 de
abril) que confirmó que abril sigue dentro de la ventana histórica: 716 + 868
unidades, **1,588 en total incluido el canario**, exactamente lo presupuestado.
Resultados en §9.11. Para repetirlos sin gastar, ambos comandos aceptan
`--offline`, que reconstruye Silver desde la caché y se niega a comprar
cualquier ventana ausente.

#### 9.10.4 Qué hace el pipeline automáticamente después de capturar

Sin intervención adicional una vez que exista la semilla real:

1. **`build_international_seed()`** mapea la captura a `(seed, rejected)` con
   los dos crosswalks (§9.5), contando cada fila que no pudo colocar.
2. **`build_international_margins()`** construye `route_totals` y
   `carrier_totals` desde los CSV de §9.7, al mismo grano mensual y
   direccional.
3. **`assess_international_seed()`** corre las nueve comprobaciones de §9.8 y
   devuelve un veredicto `accept`/`review`/`reject` con hallazgos explícitos.
   Solo `accept` o `review` continúan.
4. **`fit_international()`** usa el mismo `fit_ipf()` en producción (§2) y
   ajusta cada aerolínea contra su propio total publicado — Aerovías y Connect
   por separado, nunca como un bloque contra un total de ruta que pertenece a
   todas las aerolíneas (§8) —, con tres diferencias explícitas frente al
   ajuste nacional, cada una reportada por mes (§9.11.3): familias revisadas
   de aerolíneas que la semilla no separa, tope de una marginal a la
   capacidad visible de sus rutas, y una columna explícita `SIN_ASIGNAR`.
5. **`group_aeromexico()`** suma Aerovías + Connect en Grupo Aeroméxico
   **después** del ajuste, conservando el linaje de cada filial (§9.9).
6. **`observed_cells_to_exclude()`** marca cada celda con
   `display_source = observed_t100` o `estimated` contra el subcubo
   México–Estados Unidos de T-100, sin sumarlos nunca (§9.9).
7. **Reconciliación y sensibilidad**: los mismos diagnósticos que ya produce
   el ajuste nacional — `column_scale`, `max_row_deviation`,
   `max_col_deviation`, `iterations`, `converged` — y, si hace falta soporte
   temporal entre meses capturados, el mismo mecanismo de
   `augment_seed_with_temporal_support()` con `passengers_estimated_low/high`
   (§5).
8. **Backtest** del subcubo estadounidense con la semilla real (no la
   sustituta de §9.8.1), que da la primera medición del error del estimador
   **con** el ruido real de captura incluido — muestreo, codeshare ambiguo,
   crosswalk — en vez de la cota inferior de §10.

Lo que el pipeline **no** hace solo: la revisión humana. Ningún resultado toca
`prototypes/vuelos/` ni el generador integrado (`stage18.py`), no se activa
`flight_evidence_v1`, no cambia `historically_eligible_at_2026_07_13` y el
Analysis Agent permanece inactivo, hasta una instrucción explícita separada de
la captura misma.

### 9.11 Primera captura real: 2026M04

Derivados sin contenido del proveedor, retenidos en el repositorio privado
bajo `derived/aerodatabox_international/2026M04/` (semilla ruta × operador,
descartes agregados, estimación, diagnósticos, contraste y sensibilidad, con
manifiesto SHA-256 y linaje). Para regenerarlos desde la caché, sin gastar:

```
uv run python -m src.ingest.aerodatabox.international_cli sweep 2026M04 \
    --airports CUN,GDL,MEX,MTY,PVR,SJD --tag nucleo --offline
uv run python -m src.ingest.aerodatabox.international_cli sweep 2026M04 --days 7 \
    --airports ACA,AGU,...,ZLO --tag resto --offline
uv run python -m src.analytics.international_route_carrier --capture \
    data/silver/aerodatabox_international_seed_2026M04_nucleo.parquet \
    data/silver/aerodatabox_international_seed_2026M04_resto.parquet
```

(La caché cruda solo existe siete días; después, los derivados privados son la
fuente.)

#### 9.11.1 Puerta: `review`, sin rechazos

| Medida | Valor |
|---|---:|
| Cobertura de rutas (pasajeros AFAC) | 99.38 % |
| Cobertura de aerolíneas (pasajeros AFAC) | 98.74 % |
| `column_scale` entre las dos marginales cubiertas | 1.0070 |
| `codeshareStatus = Unknown` | **1.09 %** |
| Vuelos semilla / vuelos AFAC en rutas comparables | 0.977 |
| Semilla | 840 rutas × 52 operadores |

Hallazgos de revisión (ninguno de rechazo): 14 rutas con un solo sentido en
la semilla (12 antes de corregir la inversión de etiquetas con guion, como
`DALLAS-FORT WORTH`, que la comprobación partía en el primer guion); 693 vuelos de operadores sin entrada revisada, casi todos
aviación ejecutiva (Flexjet, VistaJet), carga (AeroUnion 6R, MasAir M7) o
aerolíneas sin marginal regular en abril (Aer Lingus, Virgin Atlantic,
Allegiant), que AFAC tampoco cuenta; 32 vuelos de aerolíneas revisadas
(0.09 %) en aeropuertos sin etiqueta AFAC; 64 rutas con más vuelos en la
semilla que en AFAC (programación contra operación).

El 17.6 % de codeshare desconocido del sondeo era un artefacto de un solo día
en dos aeropuertos: en el mes completo es 1.1 %, y la sensibilidad sin esos
registros mueve el total de Grupo Aeroméxico en 0.00 %.

#### 9.11.2 Lo que la captura real destapó y cómo se corrigió

1. **Aeropuertos principales mal mapeados.** La coincidencia exacta por
   nombre de ciudad había tomado Le Bourget (LBG) por PARIS, Ilopango (ILS)
   por SAN SALVADOR, solo DCA por WASHINGTON, solo AEP por BUENOS AIRES y
   solo HND por TOKYO, porque `dim_airport` registra CDG como Roissy, SAL como
   San Luis Talpa, IAD como Dulles, EZE como Ezeiza y NRT como Narita. El
   "100 % de cobertura" de §9.5 medía que cada etiqueta tuviera *algún*
   aeropuerto, no el correcto. Corregido con once reglas revisadas basadas
   en los códigos IATA de área metropolitana (PAR, SAL, WAS, BUE, TYO, DFW),
   y con una comprobación nueva en la puerta, `aeropuertos_sin_ciudad`, que
   mide los vuelos de aerolíneas revisadas en aeropuertos que el crosswalk no
   coloca y rechaza por encima del 1 %.
2. **Vuelos con escala en México.** El vuelo de Aeroméxico a Tokio opera
   MEX→MTY→NRT con el mismo número; el tablero de MEX solo muestra el tramo
   nacional, pero AFAC cuenta el vuelo en MEXICO-TOKYO. Lo mismo ocurre con
   Turkish (MEX–CUN–IST), Hainan y China Southern (vía PVR y SJD) y Viva
   (vía MTY). El adaptador reconstruye ahora esos pares en el aeropuerto de
   la escala, emparejando llegada nacional y salida internacional con el
   mismo número dentro de 8 horas (`THROUGH_CONNECTION_HOURS`), y los omite
   cuando el tablero del primer aeropuerto ya lista el vuelo hasta su
   destino final (el proveedor a veces muestra el destino final y no la
   siguiente escala). 297 vuelos reconstruidos, 9 omitidos por ya estar
   directos. Columna nueva `via_iata` en el detalle y `through_flights` en la
   semilla; la comprobación de duplicados admite que un mismo par llegue de
   dos pasadas solo cuando una de ellas es puramente de escala.
3. **Regionales reportadas bajo la marca.** AFAC atribuye los pasajeros al
   operador; el proveedor reporta a SkyWest, Envoy, Mesa y CommutAir bajo
   United, American, Delta o Alaska, a Lacsa y Taca bajo Avianca, y a las
   filiales de LATAM bajo LA. SkyWest pedía 789 pasajeros por vuelo visible
   y Lacsa 4,750, y el IPF no convergía. Esas aerolíneas se ajustan ahora
   como **familias revisadas** (`data/reference/afac_international_carrier_families.csv`,
   con motivo por fila): `US_NETWORK`, `AVIANCA_GROUP` y `LATAM_GROUP`, y se
   publican como la familia. Aerovías y Connect nunca se agrupan (el
   cargador lo rechaza).
4. **Crosswalk de aerolínea confirmado con la captura.** Breeze (IATA MX,
   red CUN–Charleston/Nueva Orleans/Norfolk/Providence), Volaris El Salvador
   (IATA N3, rutas con San Salvador) y Aerus (sin código IATA, identificada
   por nombre exacto en el adaptador nacional revisado, observada en
   MTY–BRO) pasan a `resolved` con esa evidencia. Quedan sin resolver SKY
   Airline Perú y Orbest (0.11 % de pasajeros). Además, una clave de
   aerolínea `unresolved` asignada por el adaptador ya no entra a la semilla,
   y la comprobación de soporte estructural simula ahora la matriz real del
   ajuste (antes comparaba la semilla consigo misma y no veía una ruta
   servida solo por una aerolínea sin marginal).

#### 9.11.3 Ajuste: convergió, con tres compromisos visibles

`fit_international()` (`src/analytics/international_route_carrier.py`):

| Medida | 2026M04 |
|---|---:|
| Rutas × columnas ajustadas | 792 × 44 |
| Rutas competidas | 269 |
| Iteraciones / convergencia | 652 / **sí** |
| Desviación máxima de fila | 4.8 pasajeros |
| Equilibrio global de las marginales de aerolínea | 0.9944 |
| Pasajeros topados por factibilidad conjunta | 7,333 (0.15 %) — TUI Airways 6,997, Aerus 336 |
| Pasajeros `SIN_ASIGNAR` | 7,333 (0.15 %) |

El orden importa y es este:

1. **Equilibrio global.** Las marginales de aerolínea incluyen pasajeros en
   rutas que la semilla no cubre, así que suman un poco más que las rutas
   cubiertas (0.57 % en abril). Ese excedente se retira primero,
   proporcionalmente a todas las aerolíneas (`global_balance`).
2. **Factibilidad conjunta.** Un flujo máximo aerolínea → ruta sobre el
   soporte de la semilla (`joint_feasible_targets()`) encuentra el grupo de
   aerolíneas cuya demanda no cabe en las rutas en que se les ve y lo
   reduce proporcionalmente, repitiendo hasta que todo cabe. El tope
   individual por capacidad es el caso de un grupo de una sola aerolínea;
   el conjunto hace falta porque julio tuvo un conflicto entre World2Fly,
   Air Europa y Evelop en Madrid–Cancún que ningún tope individual veía
   (§9.12). Las aerolíneas reducidas quedan al 99.5 % de su valor factible
   para que la solución no quede en la frontera, y ese 0.5 % se reserva.
3. **`SIN_ASIGNAR`.** Lo que las aerolíneas reducidas dejan en sus rutas va a
   una columna explícita con soporte en todas las rutas, en vez de inflar a
   las demás aerolíneas. Es igual a lo topado: nada se reparte en silencio.
4. **Tolerancia.** `INTERNATIONAL_TOLERANCE = 1e-6` del total mensual
   (≈ 5 pasajeros) en vez del 1e-8 nacional: el cubo internacional tiene
   muchas rutas de un solo operador cerca de su frontera.

TUI Airways domina los topes todos los meses: el proveedor ve una fracción
de sus vuelos (8 en abril), un límite de cobertura de la fuente, no del
crosswalk.

#### 9.11.4 Contraste fuera de muestra contra T-100

T-100 nunca entra al ajuste; se compara después, al grano del ajuste (las
familias contra su familia), sobre las celdas México–Estados Unidos:

| Conjunto | Celdas | Suma estimada / observada | Error absoluto ponderado | Mediana del error por celda |
|---|---:|---:|---:|---:|
| Todas | 785 | 0.995 | **6.3 %** | 3.8 % |
| Aerovías + Connect | 79 | 1.020 | **6.9 %** | 5.7 % |

62 celdas observadas por T-100 no reciben estimación (10 de ellas de
Aerovías o Connect): celdas que la semilla no ve y que la marca
`display_source = observed_t100` cubre con la observación. Es la primera
medición del error **con** el ruido real de captura; la cota de §10 era sin
él.

Grupo Aeroméxico: 682,823 pasajeros estimados en 136 rutas dirigidas
(AFAC publica 686,694 para Aerovías + Connect en abril; la diferencia es la
parte en rutas no cubiertas y el equilibrio global).

#### 9.11.5 Qué falta antes de publicar

- Revisión humana de la vista separada (etapa 10 de §14). La vista existe:
  `uv run python -m src.analytics.international_review 2026M04 --out <ruta>`
  genera una página HTML autocontenida con los indicadores de la puerta y
  del ajuste, las 136 rutas de Grupo Aeroméxico con sus banderas (un solo
  operador, sentido opuesto sin semilla, aerolínea topada, sin asignar,
  competencia con una familia agrupada; 99 rutas con al menos una), las
  rutas vistas en un solo sentido, los topes, las familias, las celdas de
  Aerovías/Connect que más fallan contra T-100 y una lista de verificación.
  Se guarda en el repositorio privado junto a los derivados
  (`international_review_2026M04.html`), no en este.
- Más meses para estabilidad: un mes deja a las rutas de baja frecuencia
  con semilla de una sola semana en el resto; mayo–julio siguen en la
  ventana, a ≈ 1,600 unidades cada uno con el mismo workflow.
- Nada de esto toca `prototypes/vuelos/`, `stage18.py`, `flight_evidence_v1`
  ni el Analysis Agent.

### 9.12 Mayo a julio de 2026

Capturados el 23 de septiembre de 2026 con autorización explícita, con el
mismo diseño que abril: mayo 1,612, junio 1,588 y julio 1,612 unidades,
**4,812 en total**, exactamente lo presupuestado. La pasada del resto de
julio se cortó por un 502 del proveedor en su penúltima ventana y se
reanudó desde la caché con un tope de 76 unidades, las 38 ventanas que
faltaban, sin recomprar ninguna.

| Mes | Puerta | Cobertura rutas / aerolíneas | Codeshare desconocido | Sentidos faltantes | Iteraciones | Topados = `SIN_ASIGNAR` | Grupo Aeroméxico (rutas) | AFAC Aerovías + Connect | T-100 todas / Aerovías + Connect |
|---|---|---|---:|---:|---:|---|---:|---:|---|
| 2026M04 | `review` | 99.38 % / 98.74 % | 1.09 % | 14 | 652 | 7,333 (0.15 %) | 682,823 (136) | 686,694 | 6.3 % / 6.9 % |
| 2026M05 | `review` | 99.36 % / 98.64 % | 1.22 % | 13 | 500 | 12,975 (0.30 %) | 684,480 (131) | 688,307 | 5.7 % / 6.3 % |
| 2026M06 | `review` | 99.45 % / 98.75 % | 1.14 % | 7 | 628 | 9,558 (0.22 %) | 679,144 (133) | 681,986 | sin T-100 |
| 2026M07 | `review` | 99.41 % / 97.90 % | 1.14 % | 11 | 641 | 11,570 (0.23 %) | 815,888 (133) | 819,374 | sin T-100 |

Los cuatro meses convergen, con desviación máxima de fila entre 4.3 y 5.0
pasajeros. T-100 llega hasta mayo, así que junio y julio no tienen contraste
fuera de muestra todavía. En mayo, el contraste mejora frente a abril: 5.7 %
de error ponderado y mediana de 2.4 %; Aerovías + Connect 6.3 %, con
mediana de 4.7 %.

**Julio y la factibilidad conjunta.** Con el tope individual, julio no
convergía: World2Fly solo aparece en el sentido Madrid→Cancún y su marginal
AFAC es grande, así que el tope por aerolínea la dejaba tomar 22,058 de los
22,169 pasajeros de la ruta, sin lugar para Air Europa ni Evelop. Es un
conflicto de grupo, no individual; el flujo máximo de §9.11.3 lo resuelve y
los cuatro meses se reajustaron con él.

Derivados: `derived/aerodatabox_international/2026M05/`, `2026M06/` y
`2026M07/` en el repositorio privado, cada uno con su vista de revisión
(`international_review_<mes>.html`: 94, 89 y 84 rutas de Grupo Aeroméxico
con al menos una bandera, respectivamente). Ninguno se integra al
dashboard.

### 9.13 Integración al mapa de Vuelos

Con aprobación del operador (2026-09-25), la estimación entra al generador de
Vuelos por el mismo camino que la nacional:

1. `python -m src.analytics.international_gold 2026M04,2026M05,2026M06,2026M07`
   construye `fact_route_carrier_international_estimate` (Gold, ignorado en
   este repositorio; el cubo completo vive en el repositorio privado bajo
   `derived/aerodatabox_international/`). Traduce cada ruta AFAC por ciudad
   al par de aeropuertos donde la captura vio volar a esa aerolínea
   (`MADRID-MEXICO` → `MAD<>MEX`; `MEXICO-TOKYO` → `MEX<>NRT` aunque el
   vuelo haga escala en MTY), y agrega un rango de sensibilidad de ±16 %:
   el 80 % de las 136 celdas de Aerovías/Connect contrastadas contra T-100
   en abril–mayo quedó dentro de ese error.
2. `build_warehouse` la carga como extensión opcional de ruta.
3. `src/dashboard/international_routes.py::extend_networks` la aplica a cada
   trimestre **completo** (hoy 2T26; julio solo no completa 3T26), con esta
   precedencia:
   - un mercado con pasajeros observados (T-100, ANAC) conserva su
     observación y no recibe estimación;
   - todo mercado con extremo en Estados Unidos se deja a T-100, incluso si
     la estimación lo cubre;
   - un mercado con vuelos pero sin pasajeros (slots AICM, Aerocivil, CAA,
     OMA) recibe pasajeros estimados **solo para los meses que su propia
     fuente cubre** (CAA reporta junio: solo junio), por sentido, de modo
     que los sentidos suman el total;
   - un mercado que ninguna fuente cuantificó se agrega con la etiqueta
     `AFAC + AeroDataBox · Grupo Aeroméxico estimado` y los vuelos de la
     semilla de AeroDataBox, que no entran al conteo de vuelos operados de
     Aerovías.
4. El frontal muestra esas rutas con el rango, el desglose mensual y una
   línea aparte en el resumen: "pasajeros estimados de Aerovías de México y
   Aeroméxico Connect en N rutas sin pasajeros observados". Nunca se suman a
   los vuelos ni a los pasajeros observados.

Resultado en 2T26: 34 rutas internacionales con pasajeros estimados
(912,954 pasajeros), de las cuales 30 mostraban `N/D` (23 slots AICM, 4
Aerocivil, 2 OMA, 1 CAA) y 4 no aparecían en el mapa (Guadalajara–Madrid,
Monterrey–Seúl, Monterrey–Tokio y Ciudad de México–Santiago, esta con 2 de
3 meses).

Emirates (Dubái–Barcelona–México) se acredita también a DUBAI-MEXICO con
una regla revisada de escala extranjera
(`data/reference/afac_international_foreign_through_flights.csv`), porque el
tablero de MEX solo muestra Barcelona y AFAC cuenta el vuelo en
DUBAI-MEXICO con exactamente los mismos vuelos.

Cifras vigentes tras esa regla: cobertura de rutas 99.45 % (abr), 99.46 %
(may), 99.54 % (jun), 99.52 % (jul); contraste contra T-100 de 6.3 % (abr) y
5.7 % (may), y para Aerovías + Connect de 6.8 % y 6.0 %.

`prototypes/vuelos/vuelos_revision.html` se regeneró con todo lo anterior.
El dashboard integrado publicado (`prototypes/etapa-11/resumen_ejecutivo.html`,
`static/aeromexico_tracker.html`) **no** se tocó: su publicación requiere una
autorización explícita propia y su reconstrucción completa sigue bloqueada
por la falla conocida de `evidence.validate` del Analysis Agent.
