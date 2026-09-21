# AeroDataBox para la red internacional · investigación y piloto preparado

Fecha: 21 de septiembre de 2026.
Alcance: inventario completo de la API, identificación del plan contratado,
factibilidad de cubrir las rutas internacionales sin Estados Unidos, presupuesto
de unidades y un sondeo acotado listo para despacho.
Estado: **no se consumió ninguna unidad de la API en esta sesión.** No hay clave
configurada en el entorno de nube; el sondeo queda preparado y requiere un
despacho humano explícito. No se activó evidencia, no se cambió el dashboard y
no se tocó el Analysis Agent.

## Veredicto en una página

1. **Sí existe la información en AeroDataBox**, con una precisión importante:
   la API no publica **ningún** dato de pasajeros. Lo que sí entrega, y lo
   entrega para la red internacional exactamente igual que para la nacional, es
   el **vuelo operado**: ruta, operador, matrícula y modelo de aeronave.
2. **Ya estábamos pagando por esos datos y tirándolos.** El adaptador nacional
   pide salidas en cada aeropuerto mexicano y descarta toda llegada que no sea
   nacional, contándola solo como `foreign_destinations`. Madrid, Tokio,
   Toronto y Bogotá estuvieron en esas respuestas de marzo a julio y se
   descartaron. Las respuestas crudas ya vencieron, así que recuperarlas exige
   volver a consultar.
3. **La dirección de vuelta cuesta cero unidades adicionales.** El parámetro
   `direction=Both` devuelve llegadas y salidas en la misma llamada de dos
   unidades. Un barrido de aeropuertos mexicanos así observa los dos sentidos
   de cada mercado internacional sin pagar un barrido en aeropuertos
   extranjeros.
4. **El plan contratado es RapidAPI Ultra**, no el Starter directo que asumía
   la documentación previa: 50,000 unidades, 4 solicitudes por segundo y
   **210 días** de histórico. La evidencia está abajo.
5. **La ventana histórica es lo urgente.** Con 210 días, la frontera de hoy es
   el **23 de febrero de 2026**, y **marzo empieza a salirse el 27 de
   septiembre**, dentro de seis días. Abril aguanta hasta el 28 de octubre.
6. **Los pasajeros no salen de esta API, salen de AFAC**, y las dos marginales
   internacionales existen: la hoja `REG INT` del libro origen–destino y el
   bloque internacional del resumen por empresa. El método es el mismo que ya
   está en producción para lo nacional, con una ventaja que lo nacional no
   tuvo: **T-100 permite medir el error del estimador internacional**, porque
   las rutas México–Estados Unidos entran al mismo cubo con su respuesta
   observada.

Lo que esto **no** resuelve: una celda internacional seguirá siendo
`passengers_estimated`, no pasajeros observados de Aeroméxico, salvo en las
rutas de operador único donde AFAC ya publica el total del mercado y la semilla
demuestra que no hay otro operador.

## 1. Estado del dashboard al iniciar

Rama pública en `9e6ecbb` (PR #27 integrado). El payload embebido en
`prototypes/vuelos/vuelos_revision.html` es el estado vigente de la pestaña
Vuelos y contiene, para 2026Q2, **73 mercados internacionales, de los cuales 32
no tienen pasajeros**:

| Fuente | Mercados 2026Q2 | Con pasajeros | Sin pasajeros |
|---|---:|---:|---:|
| Estados Unidos · BTS T-100 | 40 | 40 | 0 |
| AICM · vuelos AM programados | 25 | 0 | 25 |
| Colombia · Aerocivil | 4 | 0 | 4 |
| OMA · rutas documentadas | 2 | 0 | 2 |
| Brasil · ANAC | 1 | 1 | 0 |
| Reino Unido · CAA | 1 | 0 | 1 |

Los 32 mercados sin pasajeros son exactamente los que el encargo describe:

- **Canadá**: `MEX<>YUL`, `MEX<>YVR`, `MEX<>YYZ`.
- **Sudamérica**: `BOG<>MEX`, `CLO<>MEX`, `CTG<>MEX`, `MDE<>MEX`, `EZE<>MEX`,
  `LIM<>MEX`, `MEX<>UIO`.
- **Europa**: `AMS<>MEX`, `BCN<>MEX`, `CDG<>MEX`, `CDG<>MTY`, `FCO<>MEX`,
  `LHR<>MEX`, `MAD<>MEX`, `MAD<>MTY`.
- **Asia**: `ICN<>MEX`, `MEX<>NRT`.
- **Centroamérica y Caribe**: `GUA<>MEX`, `HAV<>MEX`, `MEX<>MGA`, `MEX<>PTY`,
  `MEX<>PUJ`, `MEX<>SAL`, `MEX<>SAP`, `MEX<>SDQ`, `MEX<>SJO`, `MEX<>XPL`.
- **Estados Unidos, solo programados**: `MEX<>RDU`, `MEX<>SNA` (slots AICM sin
  observación T-100 en el trimestre).

Cuatro de ellos (los de Colombia) y el de Reino Unido sí tienen vuelos
observados y sin embargo muestran `N/D` en pasajeros: la regla de
`international_routes.py` exige ambos sentidos completos en todos los meses
antes de presentar un total bidireccional. No es un hueco de fuente sino de
completitud, y se resuelve distinto que los demás.

## 2. Inventario completo de la API

Especificación consultada: `https://doc.aerodatabox.com/docs/openapi-direct-v1.yaml`,
versión **1.15.3.0**, servidor `https://api.aerodatabox.com/`. Treinta endpoints.
Precio por tier, idéntico en los tres marketplaces: **TIER 1 = 1 unidad,
TIER 2 = 2 unidades, TIER 3 = 6 unidades**, tier gratuito = 0.

### Los que sirven para este encargo

| Endpoint | Tier | Unidades | Qué entrega | Uso |
|---|---|---:|---|---|
| `/flights/airports/{codeType}/{code}/{fromLocal}/{toLocal}` | 2 | 2 | FIDS: llegadas y salidas de un aeropuerto en una ventana ≤12 h, con operador, matrícula, modelo, estado de codeshare y aeropuerto opuesto (`withLeg=true`) | **Columna vertebral.** Es el mismo endpoint del barrido nacional, con `direction=Both` |
| `/airports/{codeType}/{code}/stats/routes/daily/{dateLocal}` | 3 | 6 | Todos los destinos de un aeropuerto con su promedio diario de vuelos y **la lista de aerolíneas que los operan**, con base en los 7 días previos a la fecha | **Censo barato.** Una llamada por aeropuerto enumera la red sin comprar el detalle |
| `/flights/{searchBy}/{searchParam}/{dateFromLocal}/{dateToLocal}` | 3 | 6 | Historial de un número de vuelo en un rango (máximo 14 días en Ultra) | Verificación puntual de una ruta específica |
| `/flights/{searchBy}/{searchParam}/dates/{fromLocal}/{toLocal}` | 2 | 2 | Solo las fechas en que operó un número de vuelo | Frecuencia de una ruta concreta, muy barato |
| `/aircrafts/{searchBy}/{searchParam}` | 1 | 1 | Ficha de aeronave por matrícula, **incluye `numSeats`** | Asientos reales por matrícula, no por modelo |
| `/airlines/{airlineCode}/aircrafts` | 3 | 6 | Flota completa de una aerolínea (BETA) | Toda la flota de AM en una llamada, para el cruce matrícula → asientos |
| `/health/services/airports/{icao}/feeds` | gratis | 0 | Nivel de cobertura de un aeropuerto | Distinguir cobertura real de solo itinerario, sin gastar |
| `/health/services/feeds/{service}/airports` | gratis | 0 | Lista de aeropuertos con cada nivel de cobertura | Igual, antes de comprar |

### Los que no sirven para este encargo

`/aircrafts/.../registrations`, `/aircrafts/.../all`, `/aircrafts/reg/{reg}/image`,
`/aircrafts/search/term`, `/airports/{codeType}/{code}`, `/airports/.../runways`,
`/airports/search/{location,ip,term}`, `/airports/.../time/{local,solar}`,
`/airports/.../distance-time/{codeTo}`, `/airports/.../delays` (tres variantes),
`/airports/delays` (dos variantes), `/flights/{number}/delays`,
`/flights/{searchBy}/{searchParam}` y su variante por fecha, `/flights/search/term`,
`/industry/faa-ladd/{id}/status`, `/subscriptions/*` (web-hooks),
`/airports/.../stats/routes/daily` sin fecha.

### El hallazgo que define el alcance

**Ningún endpoint devuelve pasajeros, factor de ocupación ni ingresos.** La
única aparición de la palabra en toda la especificación es `numSeats`, "number
of passenger seats", dentro de la ficha de aeronave. Es decir: la API puede
dar **capacidad** (asientos ofrecidos, vía matrícula o modelo) y **frecuencia**
(vuelos operados), nunca demanda. Cualquier cifra de pasajeros internacional
tendrá que venir de AFAC y ser declarada estimación, igual que la nacional.

## 3. Qué plan tenemos, y por qué importa

El tarifario vigente y la evidencia de nuestras propias corridas coinciden en
un solo plan: **RapidAPI Ultra, USD 40 al mes, 50,000 unidades, 4 solicitudes
por segundo, 210 días de histórico, rango de historial de vuelo de 14 días.**

La evidencia:

- `.env.example` y el workflow privado usan `RAPIDAPI_KEY`, no
  `AERODATABOX_API_KEY`, así que es un plan de marketplace RapidAPI.
- La cuota es de 50,000 unidades. En RapidAPI solo Ultra tiene esa cifra.
- El 20 de septiembre de 2026, marzo se capturó sin problema y **enero y
  febrero fueron rechazados con HTTP 400**. Con 180 días la frontera de ese día
  habría sido el 24 de marzo y marzo habría fallado. Con 210 días la frontera
  era el 22 de febrero: marzo pasa, el 1 de febrero no. Los dos rechazos y el
  éxito de marzo solo son compatibles simultáneamente con una ventana de 210
  días.
- Coincide con lo que se observa hoy: no se puede consultar antes de finales de
  febrero de 2026.

Tres consecuencias que corrigen supuestos documentados antes:

1. `docs/etapas/aerodatabox-ruta-aerolinea-revision-20260919.md` planeó sobre
   "Starter, 40,000 unidades, 180 días". El plan real da **30 días más de
   histórico** y 10,000 unidades más. La frontera real es el 23 de febrero de
   2026, no el 25 de marzo.
2. El adaptador espera 1.1 segundos entre llamadas para respetar "una solicitud
   por segundo" del tier Basic. Ultra permite cuatro. Un barrido puede correr
   casi cuatro veces más rápido sin cambiar su costo. No se modificó en esta
   entrega porque el límite conservador nunca ha sido el cuello de botella,
   pero queda anotado.
3. Ultra **no** está en la lista de planes con retención extendida (RapidAPI
   Mega, API.Market Ultra 2 y Mega, y el plan directo Growth). La retención
   estándar de siete días sigue siendo la política correcta: el crudo es Bronze
   transitorio, nunca entra a Git y vence.

## 4. Consumo y saldo

Del reporte del 19 de septiembre, el libro interno del cliente marca **10,212
unidades** gastadas en cinco corridas (el rango de 4 unidades por dos HTTP 400
no pudo confirmarse en el portal). Sobre 50,000, quedan **entre 39,788 y 39,792
unidades** en el ciclo vigente. La cuota es mensual y se renueva, así que el
presupuesto de abajo puede además repartirse entre ciclos si conviene.

## 5. Calendario: lo que caduca y cuándo

Con ventana de 210 días y fecha de hoy 2026-09-21:

| Mes | El día 1 sale de la ventana | Días restantes |
|---|---|---:|
| 2026M01 | 2026-07-30 | fuera desde hace 53 días |
| 2026M02 | 2026-08-30 | fuera desde hace 22 días |
| **2026M03** | **2026-09-27** | **6** |
| 2026M04 | 2026-10-28 | 37 |
| 2026M05 | 2026-11-27 | 67 |
| 2026M06 | 2026-12-28 | 98 |
| 2026M07 | 2027-01-27 | 128 |
| 2026M08 | 2027-02-27 | 159 |

Marzo completo todavía es capturable **hoy**; a partir del 27 de septiembre
empieza a perder días por el principio. 2025 entero es irrecuperable por esta
vía, y ninguna extensión de plan lo devuelve: Mega y Growth llegan a 365 días,
lo que alcanzaría hasta septiembre de 2025 si se contratara ahora, pero eso es
una decisión de gasto distinta y no recupera el primer semestre de 2025.

## 6. De vuelos a pasajeros: las marginales internacionales sí existen

El estimador nacional funciona porque AFAC publica dos cortes de la misma
microdata y nunca la celda. Para internacional existen los dos equivalentes, y
están documentados en `docs/etapas/afac-rutas-investigacion-20260908.md` a
partir de una inspección directa de los libros:

| Pieza | Fuente | Grano | Estado |
|---|---|---|---|
| Marginal de ruta | Hoja **`REG INT`** del libro origen–destino (`sase-*.xlsx`) | par de ciudades direccional × mes × país, con vuelos y pasajeros, **sin aerolínea**; 979 registros direccionales y 37 etiquetas de país en la edición de julio 2026 | Verificada por inspección; **no está en el respaldo de nube**, solo el CSV nacional está en `data/reference/` |
| Marginal de aerolínea | Bloque internacional del **resumen por empresa** (`resumen-*.xlsx`, PAXREG filas 24/25) y la base larga DATATUR (`DB_AFAC.zip`) | empresa × mes, servicio nacional/internacional, regular/fletamento, nacional/extranjera, **sin ruta** | Verificada; el parser ya distingue `market='international'` |
| Contexto por país | Boletín por país (`stats-por-pais-*.pdf`) | participación de cada aerolínea en el mercado México–país | Verificado: julio 2026 da AM 39.3% en España, 45.2% en Brasil, 11.1% en Canadá, 57.4% en Japón |
| Verdad observada parcial | **BTS T-100**, ya en Gold | ruta × operador × mes, pasajeros observados México–EE. UU. | En producción |

Eso habilita un diseño que lo nacional no pudo tener:

**Descomposición con residual T-100.** El cubo internacional completo incluye
las rutas México–Estados Unidos, donde T-100 publica la celda observada. Por lo
tanto:

- filas = pares `REG INT` **menos** los pares hacia Estados Unidos, cuyos
  pasajeros por operador ya están observados;
- columnas = pasajeros internacionales por aerolínea **menos** lo que T-100 ya
  le atribuye a esa aerolínea en México–EE. UU.;
- semilla = vuelos por ruta × operador de AeroDataBox en las rutas no
  estadounidenses;
- y el subcubo estadounidense sirve de **backtest real del estimador
  internacional**, no de referencia prestada: se esconde el split observado, se
  reconstruye desde las dos marginales y se mide el error por aerolínea, ruta y
  región. El 1.98 pp del backtest nacional es una referencia transfronteriza;
  esto sería medición directa sobre el mismo cubo que se va a publicar.

### La condición que hay que probar antes de gastar nada

AFAC llama **OFOD** a sus tablas y usa pares de **ciudades**, no de aeropuertos.
No está demostrado que un par OFOD equivalga a un segmento sin escala de T-100:
`MEXICO → TOKYO` puede o no incluir conexiones, y `MEXICO` no es
automáticamente `MMMX`. La resta del párrafo anterior solo es válida si ambos
universos coinciden.

**Esa validación no cuesta una sola unidad de API**: los pares México–Estados
Unidos aparecen en las dos fuentes, `REG INT` y T-100, que ya están en el
repositorio. Comparar mes a mes los dos totales es la primera puerta y se puede
ejecutar hoy, sin clave. Si concuerdan dentro de un margen estrecho, la
descomposición es sólida; si no, se aprende el tamaño del desajuste
OFOD/segmento antes de comprar nada.

### Lo que no necesita estimador

En una ruta donde la semilla demuestra que **solo Aeroméxico opera**, el total
publicado por AFAC para ese par de ciudades es el tráfico de Aeroméxico, sin
IPF de por medio. `AGENTS.md` ya fija la condición: solo puede llamarse exacta
si la cobertura de la semilla demuestra que no falta otro operador y ambas
marginales usan el mismo universo. Varias rutas de Centroamérica y del Caribe
son candidatas naturales; Madrid, París y Ámsterdam no lo son, porque Iberia,
Air France y KLM están ahí.

## 7. Presupuesto propuesto

El costo de una llamada FIDS no cambia por pedir los dos sentidos, así que el
precio por aeropuerto-día es el mismo del barrido nacional: 2 ventanas × 2
unidades = **4 unidades por aeropuerto y día**.

| Fase | Qué compra | Unidades |
|---|---|---:|
| **0. Validación OFOD vs T-100** | Nada de API; compara `REG INT` contra T-100 en los pares de EE. UU. | **0** |
| **1. Sondeo** | Un día en MEX y MTY, ambos sentidos: ¿aparecen Madrid, Tokio, Toronto, Bogotá, con operador y matrícula? ¿cuánto codeshare llega como `Unknown`? | **8** |
| **1b. Sondeo ampliado (opcional)** | Una llamada `stats/routes/daily` en MEX: enumera toda la red del hub con sus operadores | **6** |
| **2. Censo de red** | `stats/routes/daily` en los 58 aeropuertos del crosswalk: qué aeropuertos mexicanos tienen servicio internacional no estadounidense y qué operadores | **348** |
| **3. Captura mensual** | FIDS de mes completo en los aeropuertos que el censo seleccione. Con ~20 aeropuertos: 20 × 30 × 4 | **2,400 por mes** |
| **3'. Alternativa muestreada** | Semana ponderada en los 58 aeropuertos, como el barrido nacional | **1,624 por mes** |

Recomendación: fases 0 → 1 → 2 → 3, con **abril a julio en mes completo**
(≈9,600 unidades) y marzo solo si se decide en los próximos seis días
(≈2,400 más). Total ≈ **12,400 unidades**, alrededor del 31% del saldo,
dejando ~27,000 de reserva.

El mes completo se prefiere al muestreo de siete días por una razón concreta:
una ruta internacional de dos o tres frecuencias semanales tiene una varianza
de muestreo mucho mayor que una ruta troncal nacional, y la ponderación por día
de la semana corrige la composición pero no la dispersión. Donde la ventana
histórica ya no permita el mes completo, el muestreo ponderado sigue siendo
válido y es lo que el código hace por omisión.

Un detalle que conviene explotar: el IPF es invariante a escalamientos por fila
y por columna, así que basta con que **todos los operadores de una misma ruta**
se hayan medido en la misma ventana. Mezclar rutas medidas en mes completo con
rutas medidas por muestreo es admisible; mezclar operadores de una misma ruta
medidos en ventanas distintas no lo es.

## 8. Lo que se implementó en esta entrega

Código nuevo, sin tocar la ruta nacional en producción:

- `src/ingest/aerodatabox/international.py`: adaptador internacional. Pide
  `direction=Both`, conserva un tramo cuando exactamente un extremo es
  mexicano, descarta el tramo nacional que se ve en los dos extremos en vez de
  deduplicarlo, y **conserva a los operadores extranjeros bajo su identidad
  publicada** en lugar de descartarlos. La nacionalidad del aeropuerto se
  decide con `dim_airport.country`, no con el crosswalk de 58 ciudades, para
  que una llegada desde un aeropuerto mexicano fuera de ese crosswalk no se lea
  como internacional.
- `src/ingest/aerodatabox/international_cli.py`: `plan`, `probe` y `sweep`.
  `plan` no gasta nada; `probe` exige un tope de unidades explícito y se niega
  a correr si el plan lo excede; `sweep` escribe la semilla a Silver local.
- `tests/test_aerodatabox_international.py`: 19 pruebas. Las que importan son
  las que fijan las diferencias con el adaptador nacional: que un operador
  extranjero se conserve, que un tramo nacional se descarte en ambos extremos,
  que un vuelo AM sin modelo de aeronave quede como `AEROMEXICO_UNSPLIT` en vez
  de desaparecer, y que la caché de dos sentidos no pueda colisionar con la
  caché de un sentido del adaptador nacional.

Decisiones que quedan explícitas en el código:

- Un vuelo `AM` sin modelo de aeronave no se puede repartir entre Aerovías de
  México y Aeroméxico Connect. El adaptador nacional lo descarta, porque
  dejarlo acreditaría a Aerovías un tramo de Connect. Aquí descartarlo borraría
  un vuelo internacional real de una ruta, así que se conserva bajo
  `AEROMEXICO_UNSPLIT` y se cuenta aparte.
- Un operador sin ninguna identidad publicada (ni IATA, ni ICAO, ni nombre) es
  lo único que se descarta, y queda contado.
- La semilla se guarda en dos granos: `ruta × operador × modelo`, que es lo que
  permitirá derivar asientos después con
  `data/reference/aeromexico_aircraft_seat_capacity.csv`, y `ruta × operador`,
  que es el grano del estimador.

## 9. El sondeo, listo para despacho

No hay `RAPIDAPI_KEY` en este entorno de nube, así que **esta sesión no gastó
unidades**. El mecanismo de las corridas anteriores es un workflow manual en el
repositorio privado, donde vive el secreto. Se preparó ahí
`aerodatabox-international-probe.yml`:

- consulta **un solo día** en **MEX y MTY**, ambos sentidos: 4 llamadas, **8
  unidades**, con `--budget 20` como tope duro adicional;
- imprime únicamente el resumen agregado: número de mercados, operadores,
  tramos, mercados de Aeroméxico y conteos de descarte;
- borra el contenido del proveedor del runner al terminar y **no** sube
  respuestas crudas a ningún artefacto;
- queda deshabilitado salvo durante el despacho explícito.

Lo que el sondeo tiene que contestar, y que no se puede contestar sin gastar:

1. ¿El feed de MEX trae los vuelos intercontinentales de Aeroméxico con
   aeropuerto opuesto, operador y matrícula?
2. ¿Cuánto del codeshare llega como `CodeshareStatus=Unknown`? La
   especificación advierte que en esos aeropuertos aplica un filtrado heurístico
   con "false results are possible". En internacional la densidad de codeshare
   es mucho mayor que en nacional (la empresa conjunta con Delta, Air France y
   KLM comparte código en varias de estas rutas), así que este es el riesgo
   metodológico más serio del plan y hay que medirlo antes de escalar.
3. ¿Aparecen los operadores extranjeros de cada ruta, que son los que el IPF
   necesita para repartir dentro de la ruta?
4. ¿MTY confirma Madrid y París, las dos rutas que hoy solo conocemos por el
   comunicado de OMA?

## 10. Límites que permanecen

- Ninguna cifra de pasajeros internacional producida por esta vía será
  observada. Serán `passengers_estimated` con versión, cobertura de semilla,
  diagnósticos y rango de sensibilidad, salvo el caso de operador único con
  cobertura demostrada.
- El contenido crudo sigue siendo del proveedor, con retención de siete días.
  Los conteos agregados mensuales de ruta × operador **podrían** calificar como
  obra derivada, pero eso no está confirmado con AeroDataBox y no deben
  publicarse como dataset hasta que lo esté.
- La hoja `REG INT` no está en el respaldo privado. Un agente de nube puede
  preparar el parser y las pruebas, pero la captura del libro origen–destino
  ocurre donde estén los archivos o hay que volver a descargarlos de gob.mx.
- La equivalencia ciudad ↔ aeropuerto es más frágil en internacional que en
  nacional: hay ciudades con varios aeropuertos en los dos extremos. Ninguna
  conversión automática debe entrar sin revisión humana.
- Nada de esto cambia la elegibilidad histórica al corte del 13 de julio de
  2026, no activa `flight_evidence_v1` y no toca el Analysis Agent.

## 11. Siguiente incremento sugerido

1. **Hoy, sin API**: validar `REG INT` contra T-100 en los pares México–Estados
   Unidos. Es la puerta que decide si la descomposición por residual es válida.
2. **Hoy, 8 unidades**: despachar el sondeo y leer su resumen, sobre todo el
   porcentaje de codeshare `Unknown`.
3. **Esta semana**: decidir marzo antes del 27 de septiembre; después ya no se
   puede.
4. **Después del sondeo**: censo de 348 unidades, selección de aeropuertos y
   captura mensual de abril a julio.
5. **Solo entonces**: parser de `REG INT`, crosswalk revisado de aerolíneas
   extranjeras AFAC ↔ IATA/ICAO, puerta de aceptación internacional, backtest
   contra T-100 y, si pasa, una vista de revisión separada antes de tocar el
   mapa principal.

## Fuentes revisadas

- AeroDataBox, especificación OpenAPI directa, versión 1.15.3.0:
  <https://doc.aerodatabox.com/docs/openapi-direct-v1.yaml>
- AeroDataBox, tarifario: <https://aerodatabox.com/pricing/>
- AeroDataBox, términos de uso: <https://aerodatabox.com/terms>
- `docs/etapas/aerodatabox-ruta-aerolinea-revision-20260919.md`
- `docs/etapas/afac-rutas-investigacion-20260908.md`
- `docs/pasajeros-por-ruta-y-aerolinea.md`
- `docs/cloud-development.md`
- `prototypes/vuelos/vuelos_revision.html` (payload `#flight-dashboard-data`)
