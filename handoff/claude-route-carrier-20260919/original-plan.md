# Pasajeros por ruta y aerolínea en el mercado nacional mexicano

## Contexto

El dashboard muestra, para cada ruta que toca Estados Unidos, cuántos pasajeros
llevó cada aerolínea, cuántos asientos ofreció y con qué ocupación voló. Eso
viene de BTS T-100, que la autoridad estadounidense publica con ese cruce hecho.

Para México no existe nada equivalente. AFAC publica **dos cortes del mismo
universo y nunca la celda**: pasajeros por par de ciudades sumando todas las
aerolíneas, y pasajeros por aerolínea sumando toda su red. Ninguno dice cuántos
de los 258,813 pasajeros de México–Cancún de julio de 2026 fueron de Volaris.

Que el cubo conjunto existe está demostrado: sobre 22 meses, **20 reconcilian
exactamente al pasajero** entre las dos publicaciones, y las otras dos difieren
en 10 y 36 sobre totales cercanos a cinco millones. Dos agregados publicados por
áreas distintas no caen en el mismo entero veinte veces por casualidad.

**Resultado buscado:** que la tabla de una ciudad mexicana se lea igual que la de
Salt Lake City, con lo estimado marcado como tal y con su barra de error medida.

## Advertencia sobre el alcance de esta revisión

Este plan se escribió desde un contenedor con un clon limpio del repositorio.
**Partes sustanciales del proyecto viven fuera del control de versiones** y no
pude inspeccionarlas:

| Qué | Dónde está | Por qué importa aquí |
|---|---|---|
| Generador de `static/aeromexico_tracker.html` | Local, sin versionar | La Fase 2 depende de él |
| Ingestas de ANAC, Aerocivil, CAA y slots del AICM | Local, sin versionar | Son el molde para registrar AeroDataBox |
| `data/silver/`, `data/bronze/*`, el warehouse DuckDB | Excluidos por `.gitignore` | No pude correr la tubería ni validar de extremo a extremo |

Todo juicio de este plan sobre esos tres bloques es **inferencia desde el código
versionado**, no verificación. Donde el código local contradiga al plan, manda el
código local.

Consecuencia directa: el dashboard público, cuatro fuentes de datos y el
generador dependen hoy de **una sola máquina**. Eso no es un problema de estilo;
determina quién puede ejecutar qué, y es la razón por la que la Fase 2 empieza
por inventariar en vez de construir.

## Enfoque

Ajuste iterativo proporcional. Se parte de una **semilla** que aporta la
*estructura* de la oferta —cuántos vuelos hizo cada aerolínea en cada ruta— y se
escala hasta satisfacer ambas marginales publicadas a la vez. La semilla nunca
aporta pasajeros; los pasajeros son de AFAC.

Tres hechos medidos sostienen el diseño:

1. **Los vuelos bastan como semilla.** El ajuste es invariante a escalar una fila
   o columna completa, así que el calibre medio de cada aerolínea se cancela.
   Medido contra T-100: asientos 1.40 pp, conteo de vuelos 1.98 pp.
2. **La marginal por aerolínea salva el reparto.** Repartir solo por vuelos
   sobreasigna a quien vuela aviones chicos; esa marginal absorbe la diferencia
   sistemática de ocupación entre bajo costo y servicio completo.
3. **Un sesgo de cobertura por aerolínea, parejo en su red, cuesta cero.**
   Inyectando 1.30x, 2.00x y 2.80x el error se queda en 1.96 pp. Solo daña la
   interacción ruta×aerolínea, que no es identificable desde las marginales; por
   eso la aceptación juzga **completitud**, no dispersión.

## Lo ya construido y mergeado

| Módulo | Qué hace | Pruebas |
|---|---|---:|
| `src/analytics/route_carrier.py` | Estimador y arnés contra T-100 | 29 |
| `src/analytics/seed_acceptance.py` | Acepta o rechaza una fuente candidata | 15 |
| `src/ingest/afac/margins.py` | Reconstruye las dos marginales | 8 |
| `src/ingest/aerodatabox/flights.py` + `__main__.py` | Adaptador y comando único | 25 |

`data/reference/` tiene las tres marginales (22 meses de rutas, 19 de vuelos por
aerolínea) y los crosswalks. **El único insumo pendiente es la semilla.**

---

## La fuente de la semilla: qué se compra exactamente

**AeroDataBox**, proveedor independiente de datos de aviación operando desde 2019.
Vende itinerarios, estado de vuelos y datos de aeronaves. Se accede de dos formas
—directo o vía revendedores como RapidAPI y API.Market— que son la misma API con
precios distintos.

**Plan a contratar: Starter directo, USD 19/mes, 40,000 unidades.** Es el más
barato por unidad de los tres que sirven.

| Plan | Precio | Unidades | USD por 1,000 | ¿Alcanza? |
|---|---:|---:|---:|---|
| Pro (RapidAPI) | 7.50 | 5,000 | 1.50 | No: ni un mes completo |
| **Starter (directo)** | **19** | **40,000** | **0.47** | Sí |
| Ultra (RapidAPI) | 37.50 | 50,000 | 0.75 | Sí, más caro |

### Contrato técnico

Tomado de la especificación oficial
([`doc.aerodatabox.com/docs/openapi-direct-v1.yaml`](https://doc.aerodatabox.com/docs/openapi-direct-v1.yaml)),
no de la documentación comercial:

| | |
|---|---|
| Servidor | `https://api.aerodatabox.com/` (bloque `servers`) |
| Autenticación | Cabecera `X-Api-Key` (`securitySchemes`) |
| Endpoint | `/flights/airports/{codeType}/{code}/{fromLocal}/{toLocal}` |
| Costo | **TIER 2 = 2 unidades por llamada**, confirmado también por medición |
| Ventana máxima | 12 horas en Starter |
| Histórico | 180 días documentados — **en disputa**, ver abajo |

Dos trampas medidas contra la API en vivo, ya fijadas en el adaptador:

- Pedir una ventana mayor a 12 horas **no devuelve error, devuelve cero vuelos**.
- Sin `withLeg=true`, el registro de salida **no trae aeropuerto de llegada**, así
  que la ruta es indeterminable y el barrido se desperdicia.

### Qué devuelve, medido sobre un día real

Piloto del 3 de febrero de 2026, 40 aeropuertos, 1,011 vuelos nacionales:

| Campo | Cobertura |
|---|---|
| Aerolínea (IATA, ICAO, nombre) | **100 %** |
| Aeropuerto de llegada | **99 %** |
| Modelo de avión | 100 % en vuelos de Aeroméxico |
| `codeshareStatus`, `isCargo` | presentes, evitan doble conteo |

Para contraste, OpenSky traía aerolínea en el 57 % y llegada en el 57 %.

### Qué NO devuelve

**Ni pasajeros, ni asientos, ni factor de ocupación.** Ninguna API de seguimiento
de vuelos los trae; el ADS-B tampoco los transmite.

Eso no es una limitación del plan: es el diseño. **Los pasajeros son de AFAC.**
AeroDataBox aporta únicamente la *estructura de la oferta* —cuántos vuelos hizo
cada aerolínea en cada ruta—, que es el único dato faltante para cruzar las dos
marginales que AFAC ya publica. La API nunca necesita saber de un solo pasajero.

### Por qué esta fuente y no otra

| Alternativa | Veredicto |
|---|---|
| **OpenSky Network** (gratis) | **Descartada por medición**, 540 créditos gastados. Cobertura bimodal por destino: Monterrey 92 %, Guadalajara y Mérida 0 %. Consultar llegadas ahí devuelve cero, o sea que no hay receptores, no es un fallo de estimación |
| Mapas de rutas, Wikipedia, OpenFlights | **Descartadas.** Dan presencia, no frecuencia: 13 pp de error medido |
| Boletines de AFAC y AICM | **Descartados por inspección.** AICM desagrega por terminal, no por aerolínea; DATATUR es aerolínea × mes × región, sin ruta |
| **OAG / Cirium** | Para México doméstico **también estiman**. Su documentación describe "lógica de escalado para alinear a totales de control validados externamente" — la misma arquitectura. Su semilla es MIDT (reservas de GDS), y **Volaris no estuvo en GDS hasta octubre de 2025**; Viva vende directo. MIDT es ciego al **71 % del mercado doméstico mexicano**. Precio empresarial, no público. Siguen siendo la única vía para historia profunda |

### La contradicción abierta sobre el histórico

El tarifario dice **180 días** para Starter. Pero una consulta a **224 días
funcionó en el tramo gratuito, documentado con el mismo límite**, y una a 379
devolvió cero. La medición solo acota la ventana entre 225 y 378 días.

Esto decide si el alcance son cuatro meses o siete, y se resuelve con **8
unidades** antes de gastar el resto. Es el primer paso de la Fase 0.

---

## Fase 0.5 — Antes de comprar, con el reloj parado

Nada de esto depende del mes comprado. Si algo se rompe, conviene enterarse sin
la suscripción corriendo.

**Fijar la línea base de pruebas.** Correr la suite completa en la máquina local
y anotar si las cuatro pruebas de `stage9` pasan. En el contenedor fallan por
ausencia de `data/silver/`, pero eso es artefacto del entorno. Sin saber cuál es
la señal válida, no se puede distinguir después una regresión de un ruido.

**Extender `dim_route` con las rutas domésticas.** Hoy tiene **0 de 3,407**,
porque `src/transform/stage6_dimensions.py:238 build_dim_route()` se construye
exclusivamente desde `silver/bts_t100_segment.parquet`. Sin esto, cualquier clave
foránea de la tabla nueva deja ~600 huérfanos y revienta
`foreign_keys_zero_orphans` (`validate_stage9.py:370`). Los 58 códigos IATA del
crosswalk están todos en `dim_airport` con lat/lon, así que `distance_km` sale
por haversine.

**Resolver el vocabulario de claves.** El estimador no habla IATA:
`load_afac_domestic_margins` arma `route_key` como `"ACAPULCO-CANCUN"` —nombre de
ciudad AFAC— y `build_seed_from_flights` traduce IATA→ciudad, no al revés. El
crosswalk es 1:1 y por tanto invertible. La tabla gold se publica en `IATA-IATA`
para empatar con `dim_route`; el vocabulario de ciudad queda confinado dentro del
estimador.

**Inventariar el código local** que la Fase 2 necesita: el generador del HTML y
las cuatro ingestas sin versionar. Decidir qué se sube al repo. Como mínimo el
generador, porque de él depende publicar.

## Fase 0 — Validar la fuente (el día de la compra)

Es una **puerta**. Córrase el día 1, no el día 25: si la semilla se rechaza tarde
no hay margen dentro del ciclo de suscripción.

**El presupuesto no alcanza para todo.** Siete meses completos son **49,184
unidades** contra 40,000 del plan. Cinco caben; siete no. Por eso el orden:

1. **Probar la frontera histórica** (~8 unidades). Hay una contradicción sin
   resolver: el tarifario dice 180 días para Starter, pero **una consulta a 224
   días funcionó en el tramo gratuito, documentado igual**. La medición solo
   acota la ventana entre 225 y 378 días.
2. **Bajar un mes completo** (6,960–7,192 unidades) y correr `assess_seed`.
   Completo, no muestreado: es lo único que separa la cobertura real del efecto
   de día de la semana.
3. **Medir semana contra mes con ese mismo mes ya en caché, sin gastar nada
   más.** Si la diferencia queda bajo 1.98 pp, los seis meses restantes cuestan
   9,744 unidades y **caben los siete**. Si no, hay que elegir cinco de siete o
   comprar un segundo mes. Esa elección es la decisión de esta fase.

**Criterio de paso:** `assess_seed` devuelve `accept` — ninguna aerolínea
ausente, cobertura ≥99 % de pasajeros, `column_scale` dentro de ±5 %.

## Fase 1 — Materializar el hecho

Tabla gold nueva `fact_route_carrier_domestic`, grano
`[period_id, route_key, carrier_key]`, del orden de 4,800 filas para cuatro meses.

**Por qué tabla nueva y no extender `fact_route_traffic`:** el argumento que
cierra la discusión es que `route_carrier.py:400 load_t100_panel()` lee esa tabla
como arnés de validación del propio estimador. Meter estimaciones ahí contamina
el backtest que produce el 1.98 pp — se rompería la única medida de error que
existe. Además su contrato declara **todas** las columnas `nullable: false`
(`config/gold_schema_contracts.yaml:259-294`).

Cuatro correcciones que la implementación debe incluir:

- **`is_estimated` está mal hoy.** `src/ingest/aerodatabox/__main__.py:176` lo
  pone `True` en todas las filas, pero `route_carrier.py:236` ya emite
  `is_exact`: verdadero cuando la ruta tiene un solo operador, es decir cuando el
  total de AFAC **es** la cifra de esa aerolínea y no hay estimación alguna. Debe
  ser `is_estimated = ~is_exact`.
- **Un booleano pelado no cumple la norma de la casa.**
  `src/parse/afac/validate.py:43` ya marca como issue toda fila con
  `is_estimated` y nota nula. El contrato necesita `estimator_version`,
  `seed_period_id` y `seed_source` por fila.
- **`departures` no existe en la salida del estimador.** Vuelos por ruta ×
  aerolínea requieren un **segundo ajuste** contra otras dos marginales que **no
  suman igual**: los vuelos por ruta superan a los por aerolínea en 1.1 %
  constante porque las cargueras vuelan regular nacional con cero pasajeros. Un
  IPF sobre marginales inconsistentes no respeta exactamente ninguna. Dejarlo
  fuera del contrato de esta fase, o `nullable: true`.
- **Los diagnósticos se imprimen y se tiran.** `converged`, `column_scale` y
  `max_row_deviation` deben persistirse, junto con una reconciliación publicada:
  suma por aerolínea contra AFAC, suma por ruta contra AFAC, y pasajeros de AFAC
  no representados. `column_scale` detecta el sesgo global, no la fuga por ruta
  que ocurre cuando el ajuste descarta rutas que la semilla no ve
  (`route_carrier.py:196`).

**Registrar la fuente siguiendo el molde local.** Las ingestas de ANAC, Aerocivil,
CAA y AICM ya resolvieron el problema de declarar una fuente que no deja artefacto
bronze verificable. Revisar cómo lo hicieron antes de inventar un patrón nuevo.
Si no quedaron registradas en `config/source_catalog.yaml`, ese es el molde a no
repetir.

**Decisión de linaje que hay que tomar explícitamente.** Los padres naturales de
esta tabla son las marginales de AFAC, que hoy viven en `data/reference/*.csv` y
no son tablas gold con `record_id`. Sin resolverlo, el linaje de la tabla más
delicada del proyecto queda como declaración genérica. La alternativa es **subir
primero las marginales de AFAC a gold como hechos**, y entonces `_parent_maps()`
(`stage9.py:593`) tiene padres de verdad. Recomiendo la segunda.

## Fase 2 — Publicar

**Streamlit interno: vista propia, sin tocar el mapa existente.** Crear
`v_dashboard_route_carrier_domestic` y una sección nueva. La razón es concreta:
`src/dashboard/prepare.py:19 build_route_summary()` hace `SUM` sobre toda
`fact_route_traffic` **sin filtrar fuente**, así que cualquier fila doméstica
entraría sola al resumen, a `v_dashboard_route_latest12` y al mapa de
`red_rutas.py`, cuyo título dice *"Principales rutas México–Estados Unidos…
Últimos 12 meses T-100"*. Sería silencioso y falso. Además T-100 llega a 2026M05
y las estimaciones a 2026M07: mezclarlas correría la ventana de "últimos 12
meses" y cruzaría dominios.

**HTML público: extender el generador local, no escribir uno nuevo.** Existe y
está en la máquina de Salvador. El plan original proponía escribir un
serializador desde cero; era una propuesta equivocada por desconocimiento.

Tres condiciones que la extensión debe respetar, verificadas sobre el archivo:

1. **El payload ya tiene `domestic_networks["2026Q2"]`** con 56 rutas, derivadas
   de slots del AICM y una heurística de monopolio, para **exactamente el
   trimestre que este plan estimaría**. Hay que decidir si el IPF las sustituye,
   convive con ellas bajo un `source_label` distinto, o las corrige. Dos cifras
   para la misma celda en un diff de 6 MB no se detectan a ojo.
2. **`tests/test_public_html_entrypoint.py` fija el contrato con aserciones
   literales sobre DOM y CSS** (incluido `font-size: 10.9px`). El generador
   extendido tiene que seguir produciendo eso, o el test se actualiza a
   conciencia.
3. **El payload lleva `approved_evidence_fingerprint` y `review_status`.** Hay una
   noción de aprobación humana; conviene decidir qué la invalida.

Queda una decisión documentable: el payload es **trimestral y bidireccional**,
las estimaciones son **mensuales y direccionales**. Agregar mes→trimestre de una
estimación IPF **no es** la estimación IPF del trimestre; el ajuste no es aditivo
en el tiempo.

**Coordinación:** hay una sesión hermana editando ese archivo. Un solo dueño a la
vez del bloque `flight-dashboard-data`.

## Fase 3 — Asientos y ocupación

No hay referencia de aeronave→asientos, y `src/parse/bts/t100.py:49` **descarta
activamente** el lookup `L_AIRCRAFT_TYPE` de BTS. Pero se deriva de datos propios:
T-100 trae asientos y salidas observados por aerolínea y tipo. Comprobado sobre
47,043 filas de aerolíneas mexicanas — Aeroméxico tipo 614 = 164 asientos/vuelo
sobre 151,137 vuelos; Volaris tipo 722 = 182 sobre 177,058. Es la misma flota que
vuela doméstico.

Requiere persistir el modelo de avión en el adaptador, que hoy lo lee y no lo
guarda (`flights.py:221` lo usa solo para separar Aeroméxico Connect).

**Esta fase bloquea cualquier integración futura con el mapa**: `red_rutas.py`
pondera el grosor de línea por `seats` y la vista calcula `load_factor`.

## Fuera de alcance

- **2024 y primer semestre de 2025.** Fuera de la ventana del proveedor; no se
  recupera pagando después. Solo un extracto de OAG o Cirium lo alcanzaría.
- **Rutas internacionales no estadounidenses.** AFAC publica origen-destino
  internacional en la hoja `REG INT` del mismo workbook y el método aplica igual.

## Constantes que hay que mover a mano

Son un contador manual disfrazado de prueba. **No convertirlas en dinámicas en el
mismo PR**: eso destruye la señal. Que el diff las muestre.

- `validate_stage9.py:352` **y** `:365` — el conteo de tablas gold aparece dos
  veces; mover solo una deja el check verde con un mensaje falso.
- `validate_stage9.py:387-388` — `len(sources) == 23`, `len(artifacts) == 752`.
- `validate_stage9.py:744` — `expected_domains` compara por **igualdad**.
- `validate_stage9.py:753-769` — `expected_health_datasets`, que debe moverse en
  el **mismo commit** que `sql/gold/08_dashboard_views.sql:18` y `:89`.
- `validate_stage9.py:811-822` — `len(PIPELINE_STEPS) == 32` y
  `expected_phase_counts`.
- `tests/test_dashboard.py:35` — `assert len(routes) == 66_770`.

Registrar `aerodatabox` como fuente nueva y subir el contador 23→24, con
`artifact_expected: false` y `artifact_link_policy: not_applicable`. Reutilizar un
alias existente ahorraría el incremento pero **ocultaría que hubo un proveedor
pagado**, y la transparencia es el activo del proyecto.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Parte del proyecto vive en una sola máquina | Fase 0.5 inventaría y sube al menos el generador |
| La ventana resulta 180 días duros | 8 unidades lo miden antes de gastar; el alcance baja a 2026T2 + julio |
| El presupuesto no cubre siete meses completos | La medición semana-contra-mes de Fase 0 decide |
| `UnmappedSeedError` mata la corrida **después** de gastar | `build_seed_from_flights` revienta si un solo destino queda fuera del crosswalk. Política de descarte contabilizada, no un crash |
| Una aerolínea fuera del crosswalk se cae en silencio | `stats.unmapped_carriers` se imprime y se olvida; el fallo llega después como `InfeasibleMarginsError` con índices, no nombres |
| El artefacto pagado vive en directorio ignorado | `data/silver/` está en `.gitignore` y `data/cache/` ni existe. Definir la copia durable **antes** de comprar |
| Dos cifras para la misma celda en el HTML | Decidir en Fase 2 si el IPF sustituye o convive con las 56 rutas existentes |
| El error de 1.98 pp está medido en rutas transfronterizas | Es un **supuesto** para el doméstico, marcado como tal. Solo un trimestre de verdad doméstica lo convierte en medición |

Confirmar antes de comprar: si la suscripción renueva o expira, y si las 40,000
unidades se reinician.

## Verificación

1. `uv run pytest tests/test_route_carrier_ipf.py tests/test_seed_acceptance.py`
   — 44 pruebas, incluida la que fija que un sesgo por aerolínea no mueve el ajuste.
2. `uv run pytest tests/test_aerodatabox_flights.py tests/test_aerodatabox_cli.py tests/test_afac_margins.py`
   — 33 pruebas.
3. `uv run python -m src.ingest.aerodatabox 2026M07 --dry-run` — plan de llamadas
   sin gastar.
4. `assess_seed` sobre el mes completo: debe decir `accept` con cobertura ≥99 %.
5. `uv run python -m src.analytics.route_carrier` — el arnés contra T-100 debe
   seguir en ~1.98 pp. Si se mueve, algo cambió en el estimador.
6. `just transform` y `just test` **contra la línea base anotada en Fase 0.5**.
7. `just dashboard-validate`, y `just dashboard` para ver la sección nueva.
8. **Reconciliación de sanidad**: la suma de `passengers_estimated` por ruta debe
   dar el total de AFAC para esa ruta, y por aerolínea el total nacional. Si no
   cuadra al pasajero, el ajuste no convergió y la fila no se publica.
