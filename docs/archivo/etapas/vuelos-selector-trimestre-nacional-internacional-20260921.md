# Selector global de trimestre, meses nacionales y Nacional/Internacional · 21 sep 2026

## Alcance

Tres correcciones relacionadas en la pestaña Vuelos:

1. El selector de meses nacionales ahora responde al selector global de
   trimestre (selección múltiple automática + manual, con reinicio al
   cambiar de trimestre) y el mapa/tabla nacional muestran un agregado real
   del trimestre en vez de un solo mes.
2. Se reprodujo y corrigió el error que dejaba la vista atascada en
   Internacional sin poder volver a Nacional.
3. Se auditó y corrigió el uso de **Grupo Aeroméxico** en Nacional e
   Internacional, incluyendo documentar que la vista internacional retiene
   evidencia únicamente de Aerovías de México (nunca de Aeroméxico Connect).

## Acceso a datos usado en esta sesión

Esta sesión reconstruyó `data/warehouse.duckdb` localmente (no versionado,
regenerado por `src/transform/stage6_warehouse.py::build_warehouse`) a
partir de:

- Los 20 Parquet core de `data/gold/` ya públicos y versionados.
- Los dos Parquet derivados de capacidad nacional que el repositorio público
  ignora a propósito (`data/gold/fact_route_carrier_domestic_estimate.parquet`,
  `data/gold/fact_aeromexico_domestic_capacity_estimate.parquet`), copiados
  —solo localmente, nunca a git— desde el respaldo privado
  `salvamalfa/aeromexico-tracker-data`, generados el 2026-09-20 (posteriores
  al PR #21) y ya verificados por hash contra su manifiesto en la auditoría
  previa de esta misma sesión de trabajo.

Con ese warehouse local, `build_flight_payload()` funciona con datos reales y
vigentes, lo que permitió regenerar `prototypes/vuelos/vuelos_revision.html`
(la vista autónoma de revisión, sin puerta de aprobación) y ejecutar toda la
suite de pruebas de Vuelos contra datos de producción en vez de fixtures
sintéticos. `data/warehouse.duckdb`, los dos Parquet copiados y el candidato
de evidencia generado en `analysis_runs/flight_evidence/` permanecen locales
e ignorados por git; nada de esto se subió al repositorio público.

Se detectó, sin relación con esta tarea, que `dim_source_artifact.parquet`
(público, `data/gold/`) no está en la lista de tablas que
`build_warehouse()` carga (ni en `table_definitions()` ni en su tupla
`route_extensions`); se cargó manualmente para esta sesión de pruebas. No se
tocó el código de `stage6_warehouse.py` para esto — queda como hallazgo
menor a revisar aparte.

## 1. Selector global de trimestre ↔ meses nacionales

### Causa raíz de lo que había antes

`src/dashboard/assets/flights.js` mantenía `selectedDomesticMonth` como un
**string único** (selección simple), calculado una sola vez al cargar la
página a partir del trimestre inicial, y nunca se recalculaba cuando el
usuario movía el selector global de trimestre (`periodIndex` /
`renderQuarter()`). Cambiar de trimestre re-renderizaba el mapa nacional con
el mismo mes que estuviera seleccionado antes, sin importar a qué trimestre
perteneciera. Tampoco existía ninguna agregación entre meses: el mapa y la
tabla nacionales siempre mostraban exactamente un mes.

### Corrección

- `selectedDomesticMonths` es ahora un `Set` de meses. `domesticMonthsQuarterId`
  registra a qué trimestre pertenece la selección actual.
- `renderQuarter()` compara el trimestre entrante contra
  `domesticMonthsQuarterId`; solo si cambió, reemplaza la selección por
  `monthsInQuarter(nuevoTrimestre)` (los meses de calendario de ese
  trimestre que sí existen en `domestic_monthly_networks`) y actualiza
  `domesticMonthsQuarterId`. Una edición manual de meses (clic en un botón
  del selector) nunca toca `periodIndex` ni `domesticMonthsQuarterId`, así
  que sobrevive mientras el trimestre global no cambie — y se descarta
  automáticamente en cuanto sí cambia.
- El selector de meses (`#network-month-switch`) ahora es de selección
  múltiple: cada botón alterna su propio mes con `aria-pressed`, sin poder
  quedar en cero meses seleccionados.
- `aggregateDomesticMonths(meses)` combina los `domestic_monthly_networks`
  de los meses seleccionados en un solo objeto de red: por mercado, suma
  pasajeros (y sus mínimos/máximos), vuelos y asientos únicamente sobre los
  meses donde esa ruta sí tiene datos; nunca convierte un mes faltante en
  cero. La ocupación se calcula como pasajeros totales ÷ asientos totales
  (nunca promediando los porcentajes mensuales), y solo se muestra cuando la
  cobertura de pasajeros y de capacidad coincide exactamente en los mismos
  meses — si no coincide, se evita mezclar pasajeros de tres meses contra
  asientos de uno o dos.
- Cada ruta agregada expone `months_covered`/`months_selected`; el punto de
  cobertura ya usado por otras fuentes (`coverageDotHtml`) ahora también
  lo interpreta para el caso multi-mes, y el detalle expandido por mes
  (`estimateDetails`) añade la etiqueta del mes cuando hay más de uno para
  no confundir dos filas idénticas salvo por la cifra.
- El texto de contexto (`network.period_label`, ya reutilizado por la franja
  de volumen y por el detalle de aeropuerto) ahora describe el periodo
  mostrado: `"abril–junio 2026 · 3 meses seleccionados"`,
  `"marzo 2026 · 1 mes seleccionado"`, y agrega
  `"· cobertura parcial: N de 3 meses"` cuando el trimestre tiene menos
  meses de calendario disponibles que 3 (ver el ejemplo real más abajo). No
  se agregó un segundo selector de trimestre: todo esto se deriva del estado
  del selector global de trimestre que ya existía (`periodIndex`).

### Hallazgo adicional: cobertura parcial *por ruta* dentro de un trimestre "completo"

Al escribir la prueba de regresión que suma los tres pagos mensuales y los
compara contra el agregado trimestral que el servidor ya calculaba
(`load_domestic_networks` con `expected_months` de 3 meses), apareció un
caso real: **CLQ↔MEX** solo tiene fila de estimación en junio de 2026 (no en
abril ni mayo), pero el agregado trimestral existente la marcaba como
`capacity_complete = true` sin ninguna señal de que en realidad son datos de
un solo mes, no de los tres. Esto no es un error de unión ni de doble
conteo — es, literalmente, "presentar el total como trimestre completo"
cuando no lo es, justo lo que el encargo pide evitar.

Se corrigió en `src/dashboard/domestic_routes.py::estimated_network`: cada
ruta ahora expone `months_covered`/`months_selected` (mismos nombres que usa
la agregación cliente) y, cuando `months_covered < months_selected`, el
`coverage_note` del servidor también dice
`"· cobertura parcial: N de 3 meses"`. No se cambió el criterio de
`capacity_complete` en sí (que ya era correcto: exige que los meses con
capacidad coincidan exactamente con los meses con pasajeros, sin importar si
son 1, 2 o 3) — solo se agregó la señal de cobertura que faltaba. Verificado
con datos reales:

```
2026Q2 CLQ<>MEX: months_covered=1, months_selected=3, capacity_complete=True
coverage_note: "Meses: 04, 05, 06 · pasajeros, vuelos y capacidad estimados
                · cobertura parcial: 1 de 3 meses"
```

## 2. Nacional ↔ Internacional: reproducción y corrección del error

### Reproducción

Con datos reales, `#network-mode-domestic` deja de responder después de
hacer clic en `#network-mode-international`. Causa raíz en
`flights.js`: el manejador de clic de "Nacional" comprobaba
`domesticPeriods[quarters[periodIndex].period_id]`, donde `domesticPeriods`
viene de `payload.domestic_networks`. Pero
`flights_html.py::integration_flight_payload` **siempre vacía
`domestic_networks` a `{}`** en el payload que llega al cliente en cuanto
`domestic_monthly_networks` no está vacío (línea: `"domestic_networks": {...}
if not monthly_domestic else {}`) — y `domestic_monthly_networks` está
poblado en producción desde el PR #19 (estimaciones AeroDataBox). El
resultado: `domesticPeriods` es `{}` en el cliente para *cualquier*
trimestre con datos mensuales, así que la condición del botón "Nacional"
nunca se cumple y el clic no hace nada, mientras que "Internacional" no
tiene ninguna guarda y siempre funciona. De ahí el síntoma exacto reportado:
se puede ir a Internacional pero no se puede volver.

### Corrección

Ambos manejadores de clic, y el cálculo interno `domesticAvailable` que ya
usaba `renderNetworkPeriod`, ahora usan la misma función
`domesticAvailableForQuarter(trimestre)` =
`monthsInQuarter(trimestre).length > 0 || Boolean(domesticPeriods[trimestre])`
— es decir, disponible si hay meses nacionales para ese trimestre (el caso
real desde el PR #19) o si existe el objeto trimestral heredado (el caso de
trimestres anteriores a las estimaciones AeroDataBox, que siguen usando
`domestic_networks` sin selector de meses). No se tocó
`integration_flight_payload`: seguía siendo correcto vaciar
`domestic_networks` en el cliente porque ya no se usa para renderizar
—la agregación ahora sale de `domestic_monthly_networks`—, solo hacía falta
dejar de usarlo para decidir si el botón "Nacional" responde.

Los controles ya eran dos `<button>` independientes (no checkboxes), así
que no hacía falta convertirlos a otro tipo de control para lograr
exclusión mutua; se les agregó `role="radio"` dentro de un
`role="radiogroup"` y `aria-checked` (además del `aria-pressed` que ya
manejaba el estilo visual) para declarar explícitamente la semántica de
elección excluyente ante lectores de pantalla.

## 3. Grupo Aeroméxico: auditoría y alcance por fuente

### Nacional

Ya estaba consolidado correctamente desde el PR #21: `carrier_key` se fija a
`"AEROMEXICO_GROUP"` / `carrier_label` a `"Grupo Aeroméxico"` en cada
entrada del detalle mensual, y la agregación de capacidad suma cualquier
filial presente en `fact_aeromexico_domestic_capacity_estimate` sin exigir
coincidencia exacta. Se agregó una nota de alcance visible
(`#network-scope-note`) que documenta explícitamente la composición interna:
*"Grupo Aeroméxico · combina Aerovías de México y Aeroméxico Connect"* — es
el único lugar donde los nombres de las dos razones sociales aparecen en la
interfaz nacional, y aparecen juntos como explicación de la consolidación,
nunca como series separadas.

### Internacional: auditoría de alcance por fuente

Se inspeccionó `data/gold/fact_international_route_observations.parquet`
(público, 350 filas) usado por `src/dashboard/international_routes.py`:

| Fuente | `observation_scope` | `operator_icao` observado | Alcance real |
|---|---|---|---|
| BTS T-100 (EE. UU.) | `carrier_route` | Siempre `AMX` | Operador — Aerovías de México |
| ANAC (Brasil) | `carrier_route` | Siempre `AMX` | Operador — Aerovías de México |
| Aerocivil (Colombia) | `carrier_route` | Siempre `AMX` | Operador — Aerovías de México |
| CAA (Reino Unido) | `carrier_route` | Siempre `AMX` | Operador — Aerovías de México |
| Aena (España) | `carrier_airport` | Siempre `AMX` | Operador — Aerovías de México |

`AEROMEXICO_CONNECT` tiene ICAO `SLI` (`src/transform/stage6_dimensions.py`).
El transformador (`src/transform/international_routes.py`) sí sabe
distinguir `SLI` de `AMX` cuando la fuente lo reporta (ANAC y Aerocivil
tienen esa rama de código: `operator='SLI' if 'AEROLITORAL' in name else
'AMX'`), pero **ninguna fila retenida en el Gold público usa `SLI`**: las
350 filas son 100% `AMX`. Es decir, no existe evidencia retenida de
Aeroméxico Connect en la red internacional para estos periodos — no porque
el código la excluya arbitrariamente, sino porque no aparece en la fuente.
`src/dashboard/international_routes.py` además filtra explícitamente a
`operator_icao=='AMX'`, así que si en el futuro una fuente sí trajera una
fila `SLI`, el filtro actual la descartaría en silencio; se documenta aquí
como algo a revisar si eso llega a pasar, pero no se cambió en esta sesión
por no tener ninguna fila real que lo ejerza.

También se encontró, en una sola fila de Aerocivil (CTG→MEX, 2025M10), la
distinción operador/comercializador que el dashboard ya declara en
`carrier_role`/`marketing_carrier` pero nunca expone al cliente:
`operator_icao='AMX'` (quien voló el avión) con `marketing_carrier='AXM'`
(bajo qué código se vendió el boleto) — evidencia real, aunque marginal, de
que "operador" y "comercializador" pueden diferir. No se activó esa
distinción en la interfaz (fuera de alcance de este encargo), solo se deja
documentada aquí para quien audite el alcance de la etiqueta después.

**Conclusión de la auditoría**: la red internacional representa únicamente
a **Aerovías de México como operador reportante**, nunca a Grupo Aeroméxico.
Etiquetarla como "Grupo Aeroméxico" habría sido una sobreclaim de alcance
prohibida explícitamente por el encargo ("no presentes una cifra como
consolidada si su alcance real es más estrecho").

### Corrección aplicada

- `#network-scope-note` en modo Internacional dice
  *"Aerovías de México (operador reportante) · no incluye Aeroméxico
  Connect"* — nunca "Grupo Aeroméxico".
- La franja de volumen (`#network-volume`) en modo Internacional cambió de
  `"vuelos en la red internacional"` (sin atribución de operador) a
  `"vuelos operados por Aerovías de México (no incluye Aeroméxico Connect)
  en la red internacional"`.
- El payload JSON (`#flight-dashboard-data`) sigue sin contener
  "Aerovías de México" ni "Aeroméxico Connect" en ningún dato de ruta (los
  nombres solo existen como texto fijo dentro del código fuente de
  `flights.js`, para construir la nota de alcance en tiempo de ejecución) —
  verificado con una prueba dedicada.
- No se incorporaron otras aerolíneas (Volaris, Viva Aerobus, etc.) a la
  interfaz: la pestaña Vuelos sigue exclusivamente sobre Grupo Aeroméxico o,
  en Internacional, sobre Aerovías de México como operador.

## 4. Pulido de interfaz (seguimiento, retroalimentación directa del usuario)

Tras revisar capturas de la pestaña Vuelos ya con las correcciones
anteriores publicadas, el usuario pidió seis ajustes puntuales de
presentación:

1. **Detalle expandido de cada ruta, redundante.** Antes, cada línea del
   desglose por mes repetía "Grupo Aeroméxico" y el nombre del mes (p. ej.
   tres veces "Grupo Aeroméxico · abril" para las dos direcciones de un solo
   mes). Ahora la caja de detalle declara "Grupo Aeroméxico" una sola vez
   arriba y agrupa las líneas de ida/vuelta bajo un rótulo de mes sutil
   (`abril`, `mayo`, `junio`), con un separador ligero entre grupos
   (`.route-estimate-month`, borde superior de 1px). Con un solo mes
   seleccionado no se repite el rótulo de mes en absoluto, ya que el
   contexto ya está claro por el trimestre/mes mostrado arriba.
2. **Símbolo "≈" eliminado** de toda la pestaña (franja de volumen, celdas
   de la tabla y detalle expandido). El rango de sensibilidad y la
   explicación de que es una estimación ya quedan disponibles en el `title`
   de cada celda y en el subtexto `<small>` con el rango, así que el
   símbolo era redundante.
3. **"Pasajeros estimados de Grupo Aeroméxico" → "pasajeros de Grupo
   Aeroméxico" + insignia de información.** La palabra "estimados" se quitó
   del texto visible; en su lugar aparece una insignia circular ámbar
   (`.estimate-info-badge`, reutiliza `--amber`) con un `title` que explica
   que es una estimación AFAC + AeroDataBox con rango de sensibilidad,
   siguiendo el mismo patrón que el ícono "i" ya usado en las tarjetas KPI
   (`_kpi_card`), pero en color distinto para diferenciarlo visualmente.
4. **Puntos de cobertura verde/amarillo/rojo, corregidos.** El código nuevo
   de `coverageDotHtml` para el agregado nacional multi-mes tenía un error:
   cuando la cobertura era completa (3 de 3 meses) devolvía cadena vacía en
   vez de un punto verde, así que en la práctica nunca se veía verde, solo
   rojo en las pocas rutas incompletas. Además el punto se calculaba contra
   los meses *seleccionados* (variable según lo que el usuario tuviera
   marcado) en vez de contra los tres meses de calendario del trimestre
   completo, que es como ya funciona Internacional. Se corrigieron ambos
   problemas: `aggregateDomesticMonths` ahora calcula la cobertura de cada
   ruta recorriendo siempre los meses de calendario del trimestre
   (`monthsInQuarter(domesticMonthsQuarterId)`), no la selección manual
   vigente, así el punto no cambia de color solo porque el usuario
   deselecciona un mes; y `coverageDotHtml` ya no oculta el punto cuando la
   cobertura es completa (`is-full`, verde), reproduciendo exactamente la
   semántica de Internacional (verde 3/3, amarillo 2/3, rojo 1/3). Con los
   datos reales de 2T26: 45 rutas quedan en verde y 1 (`CLQ↔MEX`, con datos
   solo de junio) en rojo.
5. **Mapa nacional con zoom a México.** El mapa nacional usaba el mismo
   encuadre mundial que Internacional sin región seleccionada
   (`lat: [-60, 85], lon: [-180, 180]`), heredado de una rama de código que
   solo aplicaba el zoom a México para el modo `scheduled_domestic`
   (trimestres previos a las estimaciones AeroDataBox). Como el modo vigente
   es `estimated_domestic`, nunca entraba a esa rama. Se generalizó la
   condición a `networkMode === "domestic"` (cualquier modo nacional), así
   que ahora siempre hace zoom a México (`fitViewToCanvas([13, 34], [-119,
   -86])`), igual que Internacional hace zoom a Norteamérica/Sudamérica/
   Europa/Asia cuando se elige una región.
6. **Internacional: "Grupo Aeroméxico" en el detalle expandido.** Antes de
   aplicar este cambio se le señaló al usuario la tensión con la auditoría
   de la sesión anterior (las fuentes internacionales retenidas son 100%
   Aerovías de México, cero Aeroméxico Connect) y se le preguntó cómo
   resolverlo. Eligió mantener "Grupo Aeroméxico" como marca general en el
   detalle por ruta, ya que Connect simplemente no tiene rutas
   internacionales en la evidencia retenida (no es una afirmación falsa,
   solo menos precisa que "Aerovías de México"). La nota de alcance
   (`#network-scope-note`) y la franja de volumen superior en Internacional
   **no cambiaron**: siguen diciendo explícitamente "Aerovías de México
   (operador reportante) · no incluye Aeroméxico Connect", que es donde
   vive la precisión técnica de la auditoría. Solo el detalle expandido por
   ruta, que antes no mencionaba ninguna aerolínea, ahora dice "Grupo
   Aeroméxico" una vez por caja, igual que en Nacional.

### Pruebas nuevas de este seguimiento

Seis pruebas nuevas en `tests/test_flights_frontend_interactions.py` (con
Chromium real sobre la página autónoma regenerada, total 12/12 en el
archivo): el detalle nacional nombra "Grupo Aeroméxico" exactamente una vez
y agrupa las tres líneas de mes bajo su rótulo (`abril`/`mayo`/`junio`);
ningún texto de la pestaña nacional contiene el símbolo "≈"; al menos un
punto de cobertura nacional es verde (`is-full`); el mapa nacional usa un
encuadre de longitud/latitud mucho más angosto que el mundial
(verificado leyendo `_fullLayout.geo.lonaxis.range`/`lataxis.range` del
gráfico Plotly ya renderizado); y el detalle expandido internacional
también nombra "Grupo Aeroméxico" una vez. Se actualizó además una
aserción existente en `tests/test_flights_prototype.py` que buscaba la
cadena literal "pasajeros estimados" en el código fuente (ya no existe,
sustituida por la insignia) por una que busca `estimate-info-badge`.

## Diferencia de granularidad Nacional (mensual) vs. Internacional (trimestral)

Nacional ahora navega por mes (con agregación al trimestre cuando el
usuario selecciona los meses completos) porque `domestic_monthly_networks`
existe desde el PR #19. Internacional sigue siendo estrictamente trimestral:
`route_networks`/`international_networks` se calculan una vez por trimestre
(`_load_routes`/`extend_networks`, con `expected_months` de 3 meses fijos) y
no existe ningún `international_monthly_networks` equivalente. Convertir
Internacional a granularidad mensual es una segunda etapa explícitamente
fuera de alcance de este encargo; no se implementó ni se dejó ningún gancho
a medias para ello.

## Pruebas ejecutadas

- `tests/test_flights_national_quarter_selection.py` (nuevo, 5 pruebas,
  contra datos reales vía `build_flight_payload()`):
  meses del trimestre 2T26; el agregado trimestral coincide exactamente con
  la suma independiente de los tres pagos mensuales (incluida la regla de
  cobertura de capacidad parcial); la ocupación agrupada usa totales y no el
  promedio de los tres porcentajes mensuales; 2026Q1 (solo marzo disponible)
  se marca `availability: "partial"` sin inventar enero/febrero; GDL–MEX de
  junio reproduce el resultado conocido.
- `tests/test_flights_frontend_interactions.py` (nuevo, 7 pruebas, con
  Chromium real vía Playwright sobre la página autónoma regenerada):
  el trimestre por defecto selecciona automáticamente abril/mayo/junio;
  deseleccionar un mes actualiza la tabla sin mover el trimestre; cambiar de
  trimestre descarta la selección manual, selecciona marzo en solitario para
  2026Q1 y muestra "cobertura parcial: 1 de 3 meses"; alternar
  Nacional↔Internacional tres veces seguidas funciona en ambos sentidos;
  una selección manual de meses sobrevive una visita a Internacional y se
  restaura al volver; Nacional nunca muestra "Aerovías"/"Connect" fuera de
  la nota de alcance consolidada; Internacional nombra su alcance real
  (Aerovías de México) y nunca dice "Grupo Aeroméxico".
- `tests/test_flights_prototype.py::test_review_html_is_self_contained_accessible_and_responsive`:
  actualizada para el nuevo `aria-label` del selector de meses y para
  verificar la ausencia de los nombres de las filiales tanto en el payload
  JSON como en el texto estático de la página, en vez de en todo el
  documento (que ahora incluye, a propósito, el código fuente de
  `network-scope-note`).
- Suite completa (`uv run python -m pytest -q`) con el warehouse local
  reconstruido: los únicos fallos restantes son los ya documentados por
  archivos locales ausentes (`data/bronze/...`), sin relación con este
  cambio.
- `git diff --check`: sin advertencias para los cambios de código y pruebas.
  El parche a `static/aeromexico_tracker.html`/`resumen_ejecutivo.html` sí
  produce 16 avisos de espacio en blanco al final de línea: son líneas en
  blanco con indentación que ya existían en la plantilla de
  `_kpi_card()`/`render_flights_panel()` (sin cambios en esta sesión) y que,
  en la publicación anterior, quedaban colapsadas porque el documento
  completo pasaba por un ciclo de reserialización de BeautifulSoup. El
  parche quirúrgico preserva el resto del documento byte a byte a propósito
  (ver "Publicación del dashboard integrado") y por eso no recibe esa
  limpieza incidental. Es cosmético —invisible en el HTML renderizado— y se
  documenta aquí en vez de corregirse tocando una plantilla no relacionada
  con este encargo.

## Regeneración de artefactos

- `python -m src.dashboard.build_flights` regeneró
  `prototypes/vuelos/vuelos_revision.html` (la vista autónoma de revisión,
  sin puerta de aprobación) contra datos reales y vigentes.
- `prototypes/etapa-11/resumen_ejecutivo.html` y `static/aeromexico_tracker.html`
  (el dashboard integrado publicado) se actualizaron en un segundo momento
  de esta misma sesión, con autorización explícita del usuario para
  publicar esa vez ("Te doy autorización de la actualización del dashboard
  publicado por esta ocasión"). Ver la sección siguiente para el
  procedimiento exacto.

## Publicación del dashboard integrado (autorizada explícitamente)

Con la autorización del usuario, se intentó primero el flujo normal:
restaurar `analysis_runs/` (y, para que la re-verificación de evidencia
desde la fuente funcionara, también `data/bronze/` y `data/silver/`) desde
el respaldo privado ya clonado y verificado por hash
(`verify_snapshot.py` había confirmado sus 1,879 archivos antes en esta
sesión), y llamar a `src/analysis_agent/stage18.py::publish()` con el
registro ya aprobado el 2026-09-06 (`analysis_runs/stage18/publication_authorization.json`,
`decision: "approve_analysis"`) — el mismo `version`/`content_hash` que ya
está incrustado en el dashboard publicado actual
(`<script id="analysis-manifest">`), confirmando que la narrativa aprobada
no ha cambiado desde entonces.

Ese flujo normal falló con `ValueError: Excerpt does not match its source
locator` dentro de `src/analysis_agent/evidence.py::validate` — una
verificación de integridad que re-extrae el texto exacto de un extracto
citado directamente del HTML crudo de la fuente (SEC) y lo compara byte a
byte contra lo aprobado. No se investigó a fondo la causa (podría ser una
diferencia de la copia restaurada, del parser, o algo más) y, siguiendo
`AGENTS.md` ("no fabriques una aprobación... no cambies el estado del
Analysis Agent para hacer pasar una prueba"), **no se intentó sortear ni
debilitar esa verificación**. Es una falla real que alguien con más
contexto sobre el expediente de análisis financiero debería investigar por
separado; no tiene relación con Vuelos.

En su lugar, se aplicó un parche quirúrgico a nivel de texto sobre los dos
archivos HTML ya publicados y aprobados, que nunca pasa por
`consumer_payload`/`verified_inputs` ni por ninguna re-verificación de
evidencia, y por lo tanto nunca podía verse afectado por esa falla:

1. Se localizaron, por posición exacta en el HTML actual, los cuatro
   fragmentos que `src/analysis_agent/reader_ui.py::refine()` inserta y que
   dependen de Vuelos: el contenido de `<section id="panel-flights">`
   (con conteo balanceado de `<section>` anidados, no con una expresión
   regular ingenua), el `<style>` cuyo contenido empieza con
   `#panel-flights {` (el CSS con alcance de `integrated_flights_css()`),
   el `<script id="flight-dashboard-data">` (el payload JSON) y el
   `<script data-runtime="flights-dashboard">` (el código fuente de
   `flights.js`).
2. Se generó contenido nuevo para esos cuatro fragmentos con exactamente
   los mismos generadores ya usados y probados en esta sesión
   (`render_flights_panel`, `integrated_flights_css`,
   `integration_flight_payload(build_flight_payload())`, y el archivo
   `flights.js` corregido), sin tocar el resto del documento.
3. Se reconstruyó el archivo por concatenación de segmentos (texto sin
   modificar + contenido nuevo), nunca reanalizando ni reserializando el
   documento completo — evitando así el riesgo, verificado empíricamente,
   de que un ciclo completo de BeautifulSoup sobre el archivo de 7 MB no es
   idempotente a nivel de bytes (colapsa saltos de línea en partes no
   relacionadas).
4. Antes de aplicar el cambio real, se verificó en un ensayo (`dry run`)
   que **cada byte fuera de esos cuatro fragmentos permanece idéntico**
   (comparación exacta segmento por segmento, no una comparación visual),
   que el manifiesto de análisis aprobado
   (`version`/`content_hash`/`approval_event`/`audit_hash`) no cambia, y
   que el resultado es HTML válido sin IDs duplicados.
5. Se probó el resultado con Chromium real (Playwright) en el contexto
   íntegro real —con las tres pestañas del lector (`Lectura ejecutiva`,
   `Economía unitaria`, `Vuelos`) y el evento `reader-tab-visible` real,
   algo que no había sido posible probar antes en esta sesión porque la
   página autónoma no tiene pestañas—: la pestaña Vuelos abre sin errores
   de consola, selecciona automáticamente abril/mayo/junio de 2026, el
   agregado trimestral coincide con lo esperado (≈3,831,997 pasajeros), y
   alternar Nacional → Internacional → Nacional funciona repetidamente.
6. Solo entonces se aplicó el mismo parche a los archivos reales del
   repositorio; se confirmó que ambos archivos publicados siguen siendo
   idénticos byte a byte entre sí (invariante ya existente) y que su
   contenido coincide exactamente con lo validado en el ensayo.

`data/bronze/`, `data/silver/` y `analysis_runs/` restaurados permanecen
locales e ignorados por git (no se subió nada de ahí al repositorio
público); solo se usaron para el intento de flujo normal y, tras su
hallazgo, quedan disponibles localmente para que una sesión futura
investigue la falla de verificación de evidencia sin tener que restaurarlos
de nuevo.

## Invariantes de gobierno confirmadas sin cambio

- `historically_eligible_at_2026_07_13 = false` y `agent_eligible = false`
  se siguen fijando explícitamente.
- `flight_evidence_v1` no se activa; el candidato de evidencia que genera
  `build_flights` sigue con `status: "candidate_unapproved"`.
- No se hicieron llamadas nuevas a AeroDataBox ni se consumieron unidades de
  RapidAPI.
- No se cambió ninguna aprobación del Analysis Agent ni el expediente de
  `analysis_runs/`.

## Archivos modificados

- `src/dashboard/assets/flights.js`: selección múltiple de meses
  nacionales sincronizada con el trimestre global, agregación multi-mes,
  corrección del botón Nacional, `role="radio"`/`aria-checked`, nota de
  alcance Grupo Aeroméxico / Aerovías de México.
- `src/dashboard/assets/flights.css`: estilos para `.network-scope-note` y
  `.route-month-label`.
- `src/dashboard/flights_html.py`: markup de `role="radiogroup"`,
  `#network-scope-note`, `aria-label` de selección múltiple (en los dos
  templates); `months_covered`/`months_selected` en la proyección de ruta.
- `src/dashboard/domestic_routes.py`: expone `months_covered`/
  `months_selected` por ruta y anota `coverage_note` cuando una ruta cubre
  menos meses que el trimestre esperado.
- `tests/test_flights_prototype.py`: `aria-label` actualizado; el chequeo
  de no-filtración de filiales ahora distingue payload/texto estático del
  código fuente del generador.
- `tests/test_flights_national_quarter_selection.py`,
  `tests/test_flights_frontend_interactions.py`: pruebas nuevas.
- `prototypes/vuelos/vuelos_revision.html`: regenerado desde el generador.
- `prototypes/etapa-11/resumen_ejecutivo.html`,
  `static/aeromexico_tracker.html`: parche quirúrgico (ver "Publicación del
  dashboard integrado") que actualiza únicamente los cuatro fragmentos de
  Vuelos; el resto del documento —narrativa aprobada, KPIs, manifiesto de
  aprobación— permanece byte por byte idéntico, verificado antes de aplicar
  el cambio.
- `docs/etapas/vuelos-selector-trimestre-nacional-internacional-20260921.md`:
  este reporte.

### Seguimiento (pulido de interfaz, sección 4)

- `src/dashboard/assets/flights.js`: `aggregateDomesticMonths` calcula
  `quarterCoverage` sobre los tres meses del trimestre (no solo los
  seleccionados), corrigiendo el punto de cobertura para que muestre verde
  cuando una ruta tiene datos en los tres meses; `coverageDotHtml` ya no
  oculta el punto cuando la cobertura está completa; `renderFlowMap` aplica
  el zoom a México también en modo `estimated_domestic`; `renderNetworkVolume`
  quita "≈" y la palabra "estimados", añade el ícono informativo
  `.estimate-info-badge`; el detalle expandido de ruta (nacional e
  internacional) ahora indica "Grupo Aeroméxico" una sola vez por caja y
  agrupa las líneas nacionales por mes cuando hay más de uno seleccionado.
- `src/dashboard/assets/flights.css`: reglas nuevas
  `.route-estimate-carrier`, `.route-estimate-month`,
  `.route-estimate-month-label`, `.estimate-info-badge`; se eliminaron las
  reglas muertas `.route-month-label` y
  `.route-estimate-line .route-direction-name strong`.
- `tests/test_flights_prototype.py`: la aserción sobre el texto del banner
  (`"pasajeros estimados"`) se actualizó a `"estimate-info-badge"` tras el
  rediseño del banner.
- `tests/test_flights_frontend_interactions.py`: seis pruebas nuevas —
  agrupación por mes y mención única de "Grupo Aeroméxico" en el detalle
  nacional, ausencia de "≈" en las cifras, punto de cobertura verde con
  cobertura completa del trimestre, zoom del mapa nacional a México, y
  mención de "Grupo Aeroméxico" en el detalle internacional.
- `prototypes/vuelos/vuelos_revision.html`: regenerado desde el generador
  para reflejar los cambios anteriores.
- `prototypes/etapa-11/resumen_ejecutivo.html`, `static/aeromexico_tracker.html`:
  **no se tocaron en este seguimiento.** La publicación al dashboard
  integrado requiere una autorización explícita de "publica esto" cada vez
  (como se manejó en la ronda anterior); estos cambios quedan solo en el
  generador/prototipo hasta recibir esa instrucción.

## Limitaciones restantes

- `src/analysis_agent/evidence.py::validate` rechaza con "Excerpt does not
  match its source locator" al intentar reconstruir el resumen ejecutivo
  desde cero con el expediente restaurado
  (`tests/test_stage11_executive_prototype.py::test_generated_artifact_matches_current_renderer`
  también lo confirma). No se investigó la causa ni se intentó evadirla;
  queda como hallazgo para una sesión dedicada al Analysis Agent, sin
  relación con Vuelos. Mientras tanto, cualquier cambio futuro a la
  narrativa financiera (no a Vuelos) seguirá necesitando resolver esto
  antes de poder usar `stage18.publish()` de nuevo.
- La granularidad mensual de Internacional queda para una segunda etapa, sin
  implementación parcial en este cambio.
- No se pudo inspeccionar la publicación en vivo de Streamlit (sin
  despliegue accesible desde esta sesión); la verificación de interacción se
  hizo con Chromium real sobre el HTML autónomo regenerado.
