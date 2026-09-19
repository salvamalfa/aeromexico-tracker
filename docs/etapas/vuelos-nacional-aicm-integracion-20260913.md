# Vuelos nacionales: slots del AICM en el dashboard local

## Resultado

La pestaña Vuelos del [HTML local principal](../../prototypes/etapa-11/resumen_ejecutivo.html) ofrece dos vistas del mapa para 2T26: **Nacional · programado** e **Internacional · observado**. La primera reúne 45 rutas mexicanas con el AICM como extremo y vuelos con número AM en el [horario histórico de Verano 2026 del AICM](https://www.aicm.com.mx/aicm/negocios/slots/horarios-historicos-para-verano-2026-pdf). España sigue en un bloque separado por aeropuerto: Madrid, 188,234 pasajeros y 780 operaciones; Barcelona, 31,808 pasajeros y 156 operaciones según las exportaciones autenticadas de Aena de abril–junio de 2026. Los dos bloques son visibles a la vez.

Los números del mapa nacional son **asignaciones programadas de slots**, no vuelos efectivamente realizados ni pasajeros. El PDF se identifica como `AM AEROMEXICO` y enumera arribo/salida, número de vuelo, sufijo, equipo, hora UTC, origen, destino, fechas, días de semana y operaciones. No permite separar con seguridad Aerovías de México de Aeroméxico Connect por operador legal. La vista señala esa limitación junto a la tabla. Las rutas no originadas o terminadas en el AICM quedan fuera.

| Ruta desde/hacia MEX | Asignaciones programadas, ambos sentidos, abr–jun 2026 |
|---|---:|
| Cancún | 2,704 |
| Monterrey | 2,510 |
| Guadalajara | 2,030 |
| Mérida | 1,608 |
| Tijuana | 1,529 |
| **45 rutas** | **31,098** |

El total agrega ambos sentidos y los tres meses. Una asignación con igual número AM, pero con sufijo u hora diferente, es una entrada distinta del horario. La verificación inicial que deduplicaba sólo por número/fecha quitaba 302 asignaciones; se corrigió al incluir sufijo y hora UTC. Después de esta corrección no quedaron duplicados con la clave completa. Cada una de las 2,836 filas operativas del PDF reconcilió su columna `Operaciones` con los días de frecuencia expandidos.

## Bronze → Silver → Gold

1. **Bronze:** PDF original [AMX verano 2026](../../data/bronze/domestic_routes_research/aicm_aeromexico_summer_slots_2026S26_20260913T004629Z.pdf), descargado el 13 de septiembre de 2026, con [metadatos](../../data/bronze/domestic_routes_research/aicm_aeromexico_summer_slots_2026S26_20260913T004629Z.pdf.meta.json), URL, fecha y SHA-256 `d97364b9eee36936ca8f21b60b3ad1ff308c3deb2fbe19d5bf53550fbc4d7ef9`. La página oficial contiene el enlace AMX; el PDF tiene 61 páginas y una fecha interna de generación del 5 de febrero de 2026.
2. **Silver:** [asignaciones por vuelo y fecha](../../data/silver/domestic_slots/aicm_amx_assigned_flight_days.parquet), 31,098 filas tras expandir días de semana al periodo 1 de abril–30 de junio. Cada fila mantiene número, sufijo, hora, origen/destino, página, localizador, URL y hash. Sólo se admiten extremos mexicanos identificados en `dim_airport` y una pierna con MEX.
3. **Gold:** [fact_domestic_scheduled_route_movements](../../data/gold/fact_domestic_scheduled_route_movements.parquet), 270 filas con grano **mes × origen × destino**. El [puente de linaje](../../data/gold/bridge_domestic_slot_lineage.parquet) relaciona las 270 filas con el artefacto Bronze en `dim_source_artifact`. La [calidad](../../data/quality/domestic_slots.json) registra filas, cobertura, exclusiones y reconciliación.

El transformador reproducible es [domestic_slots.py](../../src/transform/domestic_slots.py). Para esta versión fijada:

```powershell
.\.venv\Scripts\python.exe -m src.transform.domestic_slots
.\.venv\Scripts\python.exe -m src.dashboard.build_flights
.\.venv\Scripts\python.exe -m src.analysis_agent.stage18 --record analysis_runs/drafts/2026Q2/26bc91353505dd8b0ec7df38af8dd9d715d92c36ef6a2cbcde8d9e97c2a0aaf1.json --output prototypes/etapa-11/resumen_ejecutivo.html
```

Un periodo nuevo requiere descargar y preservar el PDF de la temporada correspondiente y actualizar la selección de fuente; este comando está fijado a Verano 2026 y todavía no es un actualizador general. La exportación española es otro proceso autenticado descrito en [España: integración](vuelos-espana-integracion-20260912.md). Ninguna cifra de slots ni de Aena se añadió al análisis histórico aprobado del 2T26 ni se publicó en Streamlit.

## Relación con AFAC y límites

La [estadística AFAC por origen–destino](https://www.gob.mx/cms/uploads/attachment/file/1100280/sase-julio-2026-27082026.xlsx) informa totales de mercado sin aerolínea. El [resumen por aerolínea](https://www.gob.mx/cms/uploads/attachment/file/1100279/resumen-julio-2026-27082026.xlsx) desglosa Aerovías y Connect por mercado nacional/internacional, sin ruta. El [libro por aeropuerto](https://www.gob.mx/cms/uploads/attachment/file/1100275/producto-aeropuerto-2006-2026-jul-27082026.xlsx) tampoco aporta aerolínea y origen/destino juntos. **No se aplicó una cuota nacional de Aeroméxico a cada ruta**; hacerlo convertiría participaciones agregadas en pasajeros o vuelos por ruta no observados.

Los slots pueden exceder o quedar por debajo de vuelos realizados debido a cancelaciones, cambios de programación, diferencia entre operadores y alcance AICM. No hay una razón válida para dividir 31,098 por los 20,886 vuelos nacionales de Aerovías reportados por AFAC: el PDF AM puede incluir vuelos de Connect y mide programación, mientras AFAC mide operación realizada. El porcentaje de cobertura nacional de operaciones efectivas **permanece sin determinar**.

El PDF descargado hoy tiene fecha interna previa al corte del comunicado del 2T26, pero no está acreditado que esta versión exacta estuviera disponible el 13 de julio de 2026. Por ello queda `agent_eligible=false` y no entra en el Analysis Agent histórico. Aena tampoco queda habilitada al corte por su fecha de exportación y la ausencia de publicación verificable de los archivos exactos.

## Validación y captura

- 22 pruebas enfocadas de vuelos, rutas internacionales, integración y nuevo linaje nacional; todas aprobaron.
- La puerta de aceptación materializada de Etapa 9 también aprobó tras sustituir el conteo fijo de fuentes/artefactos por la comparación exacta con el catálogo y manifiesto actuales. La validación de tipos de fecha se mantiene separada del cotejo de bytes y filas persistidos.
- Interfaz revisada en Chromium a 360, 736 y 1440 px: Nacional/Internacional, trimestre anterior, tarjetas Aena, búsqueda de MTY, ausencia de errores JavaScript y desplazamiento contenido del mapa móvil.
- [Captura general del dashboard](../assets/vuelos/domestic_spain_dashboard_2026Q2.png) y [captura con Monterrey seleccionado](../assets/vuelos/domestic_mty_spain_dashboard_2026Q2.png).

Siguiente incremento de calidad: comparar el horario asignado con la utilización mensual de slots que publica AICM y una fuente de vuelos realizados, manteniendo por separado pasajeros por ruta. Esto permitiría medir cuánto de la programación se efectuó antes de hablar de cobertura de operaciones reales.
