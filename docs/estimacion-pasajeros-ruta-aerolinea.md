# Estimación de pasajeros por ruta y aerolínea · método canónico

Fecha: 21 de septiembre de 2026.
Estado: documento canónico del método. Describe lo que **ya está en producción**
para el mercado nacional y fija las condiciones exactas que deben cumplirse
antes de extenderlo al mercado internacional. No autoriza por sí solo ninguna
publicación, activación de evidencia ni consumo de API.

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
`afac_carrier_domestic.csv` agrupados por `period_id`. Esa coincidencia es la
evidencia de que existe una tabla conjunta aguas arriba y de que **el conteo
O-D de AFAC es por tramo, no por itinerario**: si la tabla de pares de ciudades
contara itinerarios mientras la de empresa cuenta tramos, la diferencia sería
el tráfico de conexión del hub de México, que no es cero.

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

### 9.2 Marginal de ruta internacional — **disponible, sin parsear**

La hoja `REG INT` del mismo libro O-D. Estructura verificada a partir de la
evidencia versionada (`inspection.json`), **sin haber abierto el archivo en esta
sesión**:

| Propiedad | `REG NAC` | `REG INT` |
|---|---|---|
| Filas de datos | 609 | **979** |
| Columnas | 41 | **43** |
| Localizador del encabezado | `REG NAC!A5:AO6` | `REG INT!A5:AQ6` |
| Etiquetas de país | solo `Mexico` | **37**, incluido `Mexico` |
| Columna de operador | no | **no** |
| Columna de asientos | no | **no** |
| Meses válidos (edición julio 2026) | 1–7 | 1–7 |

Layout derivado de los localizadores de celda publicados en la evidencia
(vuelos abr–jun en `H:J`, pasajeros abr–jun en `U:W`), índices base cero:

```
0–3    claves: ciudad origen, país origen, ciudad destino, país destino
       (el orden exacto debe confirmarse contra el encabezado del archivo)
4–15   vuelos, enero a diciembre
16     total de vuelos
17–28  pasajeros, enero a diciembre
29     total de pasajeros
30–41  carga
42     total de carga
```

Las dos columnas extra respecto de `REG NAC` son las de país. El offset de
vuelos es 4 y el de pasajeros 17, contra 2 y 15 del parser nacional.

Filas de ejemplo verificadas (2026Q2, una dirección, todas las aerolíneas):

| Ruta | Pasajeros | Vuelos | Localizador |
|---|---:|---:|---|
| MEXICO → MADRID | 141,526 | 581 | `REG INT!U516:W516` |
| MEXICO → BOGOTA | 89,400 | 637 | `REG INT!U493:W493` |
| MEXICO → PARIS | 73,807 | 269 | `REG INT!U528:W528` |
| MEXICO → TORONTO | 45,409 | 313 | `REG INT!U550:W550` |
| MEXICO → SAO PAULO | 37,979 | 180 | `REG INT!U544:W544` |
| MEXICO → TOKYO | 29,013 | 181 | `REG INT!U549:W549` |

**Dónde está el archivo.** En el respaldo privado, bajo el nombre lógico del
proyecto, no con el nombre de gob.mx:

```
snapshot/data/bronze/afac_research/afac_research_city_pairs_2026M07_20260908T182059Z.xlsx
snapshot/data/bronze/afac_research/afac_research_city_pairs_historical_2025_20260908T182713Z.xlsx
snapshot/data/bronze/afac/routes_research/2026M02/afac_afac_city_pairs_archive_snapshot_2026M02_20260908T162422Z.xlsx
```

Se recuperan con Git LFS desde `salvamalfa/aeromexico-tracker-data`
(`git lfs pull --include=...`). Origen público del libro de julio de 2026:
`https://www.gob.mx/cms/uploads/attachment/file/1100280/sase-julio-2026-27082026.xlsx`.

No debe sustituirse por otra fuente. El boletín por país, Aerocivil, ANAC o CAA
describen universos distintos y mezclarlos cambiaría el significado de la
marginal sin avisar.

### 9.3 La prueba de universo que **todavía no pasa**

Para lo nacional la prueba fue concluyente (sección 3): las dos marginales
coinciden al pasajero. La prueba equivalente para internacional
—`Σ REG INT pasajeros` contra `Σ` marginal internacional por aerolínea, mes a
mes— **no se ha ejecutado** porque exige parsear `REG INT`. Es la primera
puerta y no cuesta ninguna unidad de API.

Mientras tanto, la comprobación agregada que sí se pudo hacer **no confirma**
equivalencia con T-100:

| Mes | AFAC internacional, todas las aerolíneas | T-100 México–EE. UU. | T-100 / AFAC |
|---|---:|---:|---:|
| 2026M01 | 5,796,013 | 3,692,167 | 63.7 % |
| 2026M02 | 5,028,616 | 3,160,192 | 62.8 % |
| 2026M03 | 5,449,478 | 3,461,494 | 63.5 % |
| 2026M04 | 4,827,573 | 3,077,528 | 63.7 % |
| 2026M05 | 4,268,203 | 2,944,985 | 69.0 % |

El boletín por país de AFAC implica, para julio de 2026, que Estados Unidos es
≈ 71.6 % del total internacional (Norteamérica 76.77 % del total; dentro de
Norteamérica, Estados Unidos 93.28 %). El promedio calculado aquí para
enero–mayo es 64.4 %. La brecha de entre 3 y 8 puntos **no está explicada**:
puede ser estacionalidad, cobertura incompleta de T-100, o una diferencia real
de universo. No debe asumirse resuelta.

Hay además una discrepancia de entidad documentada: T-100 no tiene **ninguna**
fila `AEROMEXICO_CONNECT` en el tráfico transfronterizo de 2026, mientras AFAC
le atribuye a Connect entre 36,239 y 49,198 pasajeros internacionales al mes.
Y la participación de Aeroméxico difiere según la fuente: 11.6 % en el boletín
(julio 2026) contra 9.24 % en T-100 (enero–mayo 2026).

**Consecuencia de diseño.** El plan de restar el subcubo estadounidense de ambas
marginales —propuesto en el reporte del 2026-09-21— **queda descartado como
diseño primario**. Restar exige demostrar igualdad de definiciones, cobertura,
meses y universos, y la comprobación disponible la contradice.

### 9.4 Diseño recomendado: cubo internacional completo, T-100 solo como validación

```
filas     = todos los pares de ciudades de REG INT, incluidos los de EE. UU.
columnas  = todas las aerolíneas de la marginal internacional de AFAC
semilla   = vuelos por ruta direccional × operador de AeroDataBox
```

T-100 **no entra como insumo**. Entra después, como contraste: donde T-100
publica la celda observada, se compara contra la celda ajustada y se reporta el
error. Así:

- no hay doble conteo, porque T-100 nunca se suma ni se resta;
- no hace falta demostrar igualdad de universos para producir la estimación,
  solo para interpretar el contraste;
- donde T-100 observa la celda, **el dashboard publica T-100**, no el ajuste. La
  estimación es para las rutas donde no hay observación.

### 9.5 Piezas nuevas que hay que construir, y que no existen

| Pieza | Análogo nacional | Estado |
|---|---|---|
| Parser de `REG INT` | `read_route_workbook` en `src/ingest/afac/margins.py` | **no existe** |
| Crosswalk ciudad AFAC internacional ↔ IATA | `afac_city_iata_crosswalk.csv` (58 aeropuertos) | **no existe**; 37 países, ciudades con varios aeropuertos en ambos extremos |
| Crosswalk aerolínea AFAC internacional ↔ IATA/ICAO | `afac_carrier_crosswalk.csv` (2 filas) | **no existe**; 66–103 nombres |
| Puerta de aceptación internacional | `seed_acceptance_v3` | reutilizable, umbrales por revalidar |
| Semilla internacional | `flights.py` | **existe**: `src/ingest/aerodatabox/international.py` |

Los dos crosswalks son artefactos de revisión humana. La equivalencia
ciudad ↔ aeropuerto es más frágil que en el caso nacional: `MEXICO` no es
automáticamente `MMMX`, `LONDRES` no es automáticamente `LHR`, y una ciudad con
varios aeropuertos en el extremo extranjero no puede resolverse por
proximidad.

---

## 10. Qué tan bueno es el estimador, medido

`src/analytics/route_carrier_backtest.py` esconde el split publicado por T-100,
lo reconstruye desde las dos marginales y reporta el error por varios cortes.
Rutas de un solo operador excluidas: el ajuste las recupera por construcción y
aplanarían todos los promedios.

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

1. **Sin API.** Parsear `REG INT` y ejecutar la prueba de universo compartido
   contra la marginal internacional por aerolínea, mes a mes, como se hizo en la
   sección 3 para lo nacional. Si no coinciden al pasajero, documentar la brecha
   antes de seguir.
2. **Sin API.** Construir y revisar a mano los dos crosswalks de la
   sección 9.5, con conteo explícito de rutas, pasajeros y aerolíneas sin
   correspondencia.
3. **API mínima.** Sondeo acotado para medir el riesgo de clasificación de
   codeshare y confirmar que el feed trae la red internacional con operador y
   aeropuerto opuesto.
4. **API.** Captura de la semilla en los meses que la ventana histórica todavía
   permita.
5. **Sin API.** Puerta de aceptación internacional, ajuste, backtest contra el
   subcubo observado de T-100 con los cortes de la sección 10.
6. **Revisión humana.** Vista separada de revisión antes de tocar el mapa
   principal, con las tres capas distinguibles sin depender de un tooltip.
