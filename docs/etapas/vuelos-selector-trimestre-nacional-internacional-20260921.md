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
- `git diff --check`: sin advertencias.

## Regeneración de artefactos

- `python -m src.dashboard.build_flights` regeneró
  `prototypes/vuelos/vuelos_revision.html` (la vista autónoma de revisión,
  sin puerta de aprobación) contra datos reales y vigentes.
- `prototypes/etapa-11/resumen_ejecutivo.html` y `static/aeromexico_tracker.html`
  (el dashboard integrado publicado) **no se regeneraron**: su generador
  (`src/analysis_agent/stage18.py::consumer_html`, llamado desde
  `publish()`) exige el expediente de aprobación del Analysis Agent en
  `analysis_runs/`, que es local/privado y no está disponible en esta
  sesión (nunca se restauró el snapshot completo, solo los dos Parquet de
  capacidad nacional necesarios para el warehouse). Fabricar esa aprobación
  o sortear la puerta está explícitamente prohibido por `AGENTS.md`. Se
  verificó en cambio que `render_flights_panel()` — la función pura que
  aporta el fragmento de Vuelos al dashboard integrado, sin puerta de
  aprobación — produce el mismo marcado corregido (`role="radiogroup"`,
  `#network-scope-note`, `aria-label` de selección múltiple) que la página
  autónoma. **Antes de publicar esta corrección**, alguien con acceso al
  expediente de aprobación privado debe ejecutar el flujo normal de
  `stage18.publish()` para reconstruir los dos artefactos integrados; hasta
  entonces siguen mostrando el selector de un solo mes y el error de
  Nacional/Internacional.

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
- `docs/etapas/vuelos-selector-trimestre-nacional-internacional-20260921.md`:
  este reporte.

## Limitaciones restantes

- `prototypes/etapa-11/resumen_ejecutivo.html` y `static/aeromexico_tracker.html`
  quedan pendientes de una republicación autorizada (ver arriba).
- La granularidad mensual de Internacional queda para una segunda etapa, sin
  implementación parcial en este cambio.
- No se pudo inspeccionar la publicación en vivo de Streamlit (sin
  despliegue accesible desde esta sesión); la verificación de interacción se
  hizo con Chromium real sobre el HTML autónomo regenerado.
