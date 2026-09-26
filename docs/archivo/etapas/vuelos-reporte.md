# Vuelos — reporte de entregas

## Entrega 1 · Primer incremento aislado

Fecha de validación: 2026-09-06  
Estado: listo para revisión; sin integración en la navegación principal.

### Resultado

- Se creó una vista HTML local y autocontenida para Vuelos con el diseño visual vigente del Tracker.
- El selector trimestral controla exclusivamente capacidad, demanda, pasajeros, ocupación y mezcla SEC. La red T-100 y el forecast conservan ventanas independientes y visibles.
- La red incluye un globo 3D giratorio, selección de rutas y aeropuertos, ranking por pasajeros/asientos/salidas, perfil de ruta, comparación contra la ventana móvil anterior y concentración recalculada con la métrica elegida.
- A 360 y 736 px la vista inicial es Lista. En escritorio la vista inicial es Mapa. La lista ofrece búsqueda, selección y navegación con flechas, Inicio y Fin.
- Se creó un paquete complementario `flight_evidence_v1` en estado `candidate_unapproved`. No se alteró ni activó el paquete aprobado del Analysis Agent.

### Cobertura y cifras verificadas

| Bloque | Periodo | Resultado |
| --- | --- | --- |
| Indicadores trimestrales | 2T26 | 6.014 M pasajeros; 9.256 mil M ASM; 7.851 mil M RPM; ocupación 84.9% |
| Mezcla de pasajeros | abr–jun 2026 | 3.936 M nacional; 2.078 M internacional; total 6.014 M |
| Red T-100 observada | jun 2025–may 2026 | 96 mercados; 49 aeropuertos; 3,801,147 pasajeros; 4,566,932 asientos; 26,427 salidas |
| Comparación de rutas | jun 2024–may 2025 | Ventana anterior de igual longitud; ausencia preservada como no disponible |
| Forecast vigente | jul 2026–jun 2027 | SARIMA; bandas 80% y 95%; entrenado 2026-08-24 con información hasta 2026M06 |

La mezcla SEC completa existe para 1T25, 2T25, 1T26 y 2T26. Los demás trimestres muestran “no disponible” porque no tienen tres meses comparables en la fuente mensual preservada.

### Elegibilidad para Analysis Agent 2T26

Evidencia candidata:

- Indicadores trimestrales SEC: elegibles al corte 2026-07-13.
- Mezcla nacional/internacional derivada de los anexos mensuales 99.2–99.4 del mismo 6-K: elegible y reconciliada con los totales trimestrales.
- T-100: excluido; la copia local fue descargada y revisada después del corte y no preserva la versión exacta disponible entonces.
- AFAC: excluida por falta de una versión certificada al corte dentro del paquete.
- Forecast: excluido porque su entrenamiento ocurrió después del corte.
- Rutas anunciadas y comercializador/codeshare: excluidos por ausencia de una fuente estructurada y versionada.

Paquete generado: `analysis_runs/flight_evidence/2026Q2_5bde445fafe7faded2b2a5e2d6f51c3b035b0d135ab2f7c75d01b643fee424c6.json`  
Fingerprint de evidencia: `5bde445fafe7faded2b2a5e2d6f51c3b035b0d135ab2f7c75d01b643fee424c6`  
SHA-256 del archivo: `23aec382d2c3eb6dc92a5dd8b452fbe3e582717cac0e4b86a77b7c04eaf8570e`

### Archivos de esta entrega

- Contrato y preparación: `src/dashboard/flights.py`
- Render y comando de construcción: `src/dashboard/flights_html.py`, `src/dashboard/build_flights.py`
- Presentación e interacción: `src/dashboard/assets/flights.css`, `src/dashboard/assets/flights.js`
- Paquete complementario: `src/analysis_agent/flight_evidence.py`
- Pruebas: `tests/test_flights_prototype.py`
- Vista de revisión: `prototypes/vuelos/vuelos_revision.html`
- Evidencia visual: `docs/assets/vuelos/vuelos-360.png`, `vuelos-736.png`, `vuelos-desktop.png`

Vista HTML SHA-256: `9a4617428b065c834bb0699730da5ff58b7bd64f24ac71ba865c7df99b541077`.

### Validaciones

- 28 pruebas dirigidas aprobadas: Vuelos más regresión de Etapas 11 y 18.
- Reconciliación exacta en 2T26 de nacional + internacional = total para pasajeros, ASM y RPM.
- Ventanas T-100 actual y comparable de 12 meses, mercados únicos, coordenadas completas, salidas positivas y totales reconciliados.
- Forecast con 12 observaciones de backtest, 12 meses futuros e intervalos correctamente anidados.
- Navegador real en 360, 736 y 1440 px: sin desbordamiento horizontal, errores de página, errores de consola ni solicitudes externas.
- Comprobados: vista móvil Lista, vista escritorio Mapa, búsqueda, teclado, selección de ruta, cambio de importancia y actualización del HHI.
- HTML autocontenido menor a 6 MB y regeneración determinista.

### Protección del trabajo compartido

No se editaron en esta entrega el HTML principal, el controlador actual de pestañas ni los estilos/JavaScript compartidos. Se registró la línea base previa a una futura integración:

| Archivo compartido | SHA-256 observado |
| --- | --- |
| `prototypes/etapa-11/resumen_ejecutivo.html` | `40517b715c0a69727869dbad02d90a1a318898dcc7d41eb0d8df57bf5405793b` |
| `src/analysis_agent/reader_ui.py` | `5f79c3edccfd64f98eeb1b1e771e14fe1633dc4fd7de16242cb1df156a9efa4b` |
| `src/dashboard/assets/executive_summary.css` | `5e7a0fe264c268b36812b61c020eeec997e67b5e3e6cdf899274a5547e3e4705` |
| `src/dashboard/assets/executive_summary.js` | `1648f5624e658425de95706214a4a9766b75564d37c58c859801aba3cbc4b691` |

El repositorio ya contenía cambios sin consolidar en algunos de estos archivos; sus modificaciones siguen perteneciendo a otras sesiones.

### Faltantes y límites

- El globo usa una esfera local sin fronteras políticas. Las rutas y aeropuertos son geográficos, pero la orientación depende de la interacción del usuario.
- La red representa exclusivamente la cobertura T-100 México–Estados Unidos; no representa la red mundial de Aeroméxico.
- Los códigos IATA siguen siendo la identidad de presentación. Una ampliación histórica requiere Airport ID.
- No se incorporó una fuente de rutas anunciadas ni de comercializador/codeshare.
- No se hizo backfill, reentrenamiento, cambio de modelos, modificación de Gold ni despliegue.

### Siguiente paso propuesto

Pausar para comentarios sobre jerarquía, densidad y comportamiento del globo/lista. Tras aceptación, revisar nuevamente los hashes y el diff de los archivos compartidos, registrar Vuelos desde el generador vigente y generalizar la navegación de pestañas sin editar manualmente el HTML generado.

## Entrega 2 · Fusión mensual y diagnóstico de flow map

Fecha de validación: 2026-09-06  
Estado: gráfica implementada; sustitución del globo pendiente de aceptación tecnológica.

### Cambio en capacidad y demanda

- Se eliminaron los dos cuadros redundantes de pasajeros por segmento y composición trimestral.
- Una sola gráfica presenta barras mensuales apiladas de pasajeros nacionales e internacionales y una línea superpuesta calculada como `nacional + internacional`.
- El selector trimestral resalta el trimestre elegido dentro de la serie, pero no cambia ni recorta su cobertura mensual.
- La serie abarca octubre de 2024–junio de 2026: 14 meses observados y siete meses sin fuente SEC preservada. Los meses faltantes aparecen como huecos y la línea usa `connectgaps: false`.
- En los meses publicados, el total de la línea siempre se calcula desde los dos segmentos. Se conserva por separado el total reportado y su diferencia de redondeo para trazabilidad.

### Investigación de la referencia Highcharts

- La demo enlazada utiliza la serie `flowmap` de Highcharts Maps. Highcharts permite evaluación y determinados usos personales/educativos, pero su EULA exige una licencia comercial para trabajo interno de una organización o uso profesional. No se recomienda incorporarlo sin confirmar una licencia vigente.
- La interacción y el aspecto se pueden reproducir sin Highcharts. La alternativa recomendada para el siguiente incremento es `deck.gl` con `GlobeView`, `GeoJsonLayer` y `GreatCircleLayer`: licencia MIT, rutas seleccionables, ancho por pasajeros/asientos/salidas y arcos geodésicos sobre un globo giratorio.
- Para conservar el HTML local y sin red, la librería, la geometría mundial simplificada y sus licencias deberán fijarse por versión, guardarse localmente y registrarse con SHA-256. No se usarán tiles, CDN ni llamadas remotas.
- MapLibre GL JS también es open source bajo BSD-3-Clause y soporta proyección de globo, pero su flujo habitual depende de estilos y tiles vectoriales. Añade complejidad innecesaria para la primera versión autocontenida.
- Plotly.js, ya incluido y con licencia MIT, admite líneas sobre mapas ortográficos. Es viable, aunque lograr fronteras, curvas ponderadas, flechas y picking con la misma calidad exige más implementación propia que `deck.gl`.
- `globe.gl` es MIT y tiene una capa de arcos 3D, pero incorpora Three.js y produce una estética más tridimensional que la referencia de Highcharts.

Fuentes técnicas revisadas:

- Highcharts Flow map: https://www.highcharts.com/docs/maps/flowmap-series
- Highcharts EULA: https://shop.highcharts.com/license-eula
- deck.gl GreatCircleLayer: https://deck.gl/docs/api-reference/geo-layers/great-circle-layer
- deck.gl MIT: https://github.com/visgl/deck.gl/blob/master/LICENSE
- MapLibre GL JS: https://maplibre.org/maplibre-gl-js/docs
- MapLibre BSD-3-Clause: https://github.com/maplibre/maplibre-gl-js/blob/main/LICENSE.txt
- Plotly lines on maps: https://plotly.com/javascript/lines-on-maps/
- Plotly MIT: https://github.com/plotly/plotly.js/blob/master/LICENSE
- globe.gl: https://github.com/vasturiano/globe.gl

### Validación

- 29 pruebas dirigidas aprobadas, incluida la comprobación de eje mensual continuo, siete huecos explícitos y suma de segmentos.
- Navegador real en 360, 736 y 1440 px: tres trazas renderizadas, sin desbordamiento, errores de consola, errores de página ni solicitudes externas.
- Capturas actualizadas en `docs/assets/vuelos/`.
- SHA-256 actualizado de la vista HTML: `daeb6b16f854af214f2f225d456f9b25dee8f7a1cae994faa2e4c9e038a8eb93`.
- Los hashes observados del HTML principal y `reader_ui.py` permanecen iguales a la Entrega 1.

### Siguiente paso propuesto

Tras comentarios sobre la gráfica fusionada, construir una prueba aislada del nuevo flow map con `deck.gl` y geometría local, comparar legibilidad, peso y controles con el globo Plotly actual y conservar la Lista como alternativa móvil y accesible. No sustituir el globo vigente hasta aprobar esa prueba.

## Entrega 3 · Serie Gold continua, selector y mapa de flujos

### Resultado

- La gráfica de pasajeros utiliza ahora la fuente consolidada AFAC de Gold: 138 meses continuos entre enero de 2015 y junio de 2026, con nacional, internacional y total.
- La línea original coincide exactamente con la suma de ambos segmentos en cada mes. El bloque conserva visible la diferencia de alcance frente al KPI trimestral SEC; para 2T26 AFAC suma 5,917,011 pasajeros y SEC reporta 6,014,000.
- El selector `Original / Desestacionalizada` usa `passengers_afac_sa`, la serie Gold derivada mediante STL robusto de periodo 12. La mezcla por segmento se presenta en la vista original; la vista ajustada muestra la línea total para evitar atribuir el ajuste a segmentos no modelados.
- El globo anterior se sustituyó por un mapa ortográfico de flujos bidireccionales. Las rutas T-100 se dibujan como arcos ponderados por pasajeros, asientos o salidas y mantienen selección sincronizada con la lista y el perfil.
- La geometría mundial es Natural Earth 5.1.2 a escala 1:110m, dominio público, guardada localmente y embebida en el HTML. SHA-256: `6866c877d39cba9c357620878839b336d569f8c662d3cfab4cb1dbe2d39c977f`.

### Archivos modificados

- `src/dashboard/flights.py`
- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `src/dashboard/assets/ne_110m_admin_0_countries.geojson`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones

- 138 de 138 meses AFAC presentes; sin huecos, duplicados ni diferencias entre total y suma de segmentos.
- Selector original/desestacionalizada operativo y con estado accesible `aria-pressed`.
- Mapa generado con 96 rutas, 49 aeropuertos y geometría local; sin solicitudes externas.
- A 360 y 736 px la Lista es la vista inicial; a 1440 px inicia el mapa. No se detectó desbordamiento horizontal ni mensajes de consola.
- La vista contiene 276 barras mensuales, la línea total y 326 trazos SVG en el mapa.

### Faltantes y elegibilidad

- La versión AFAC Gold vigente fue ingerida el 20 de agosto de 2026; no demuestra disponibilidad histórica al corte del 13 de julio de 2026 y permanece fuera de `flight_evidence_v1`.
- El ajuste STL vigente también permanece fuera del paquete histórico. No se recalculó el modelo ni se inició backfill.
- T-100 conserva alcance México–Estados Unidos y ventana móvil; el mapa no representa toda la red mundial.

### Evidencia candidata para el agente

Sin cambios: el paquete candidato continúa incorporando exclusivamente las métricas SEC certificadas de 2T26. Gold AFAC, STL, T-100 y forecast se mantienen como contexto actual no elegible.

### Siguiente paso

Pausar para revisión visual. Tras la aceptación, revisar nuevamente los cambios compartidos y proponer la integración concreta en el generador de pestañas, sin editar manualmente el HTML principal.

## Entrega 4 · Composición trimestral predeterminada

### Resultado

- Se retiró de la interfaz la opción desestacionalizada; el bloque muestra exclusivamente la serie original AFAC Gold.
- El control replica el patrón discreto `Periodo` de Economía unitaria mediante un selector compacto con dos opciones: `Trimestral` y `Mensual`.
- `Trimestral` es la selección inicial. La gráfica suma nacional e internacional dentro de cada trimestre y dibuja la línea total como suma de ambos segmentos.
- `Mensual` conserva los 138 meses originales sin interpolación ni ajuste estacional.

### Archivos modificados

- `src/dashboard/flights.py`
- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones

- Vista inicial: 46 trimestres, 92 barras apiladas y una línea total.
- Vista mensual: 138 meses, 276 barras apiladas y una línea total.
- El selector cambia la granularidad sin mensajes de consola y conserva la fuente AFAC Gold.
- A 360 px el selector mide 210 px, no genera desbordamiento y la composición inicia en `Trimestral`.
- Las 22 pruebas dirigidas de Vuelos y regresión de Etapa 11 pasan.

### Faltantes, evidencia candidata y siguiente paso

No cambia la elegibilidad histórica: AFAC Gold permanece fuera del paquete piloto 2T26 hasta disponer de una versión certificada al corte. No se modificó `flight_evidence_v1`, no se recalculó ningún modelo y no se inició backfill. Pausar para comentarios antes de integrar la pestaña en la navegación compartida.

## Entrega 5 · Mapa rectangular fijo y diagnóstico AFAC de rutas

### Diagnóstico de cobertura

- La fuente AFAC actualmente integrada no tiene grano de ruta. Para Aeroméxico contiene mes, tipo de servicio y mercado agregado `domestic/international`, pero no origen, destino ni aeropuerto.
- `fact_route_traffic` contiene 189,809 registros, 3,407 rutas y 171 operadores; todos provienen de `bts_t100`. No existe en Gold otra fuente de rutas que permita ampliar de forma válida la red de Aeroméxico fuera de México–Estados Unidos.
- Las tablas de tráfico aeroportuario disponibles no identifican la ruta ni necesariamente el operador y no pueden sustituir evidencia origen–destino.
- El límite aplica a la fuente AFAC integrada en el proyecto. No demuestra que AFAC u otra autoridad carezca de cualquier conjunto público adicional; incorporar uno exigiría diagnóstico, descarga preservada, parser, paquete versionado y validación de disponibilidad histórica.

### Resultado visual

- Se eliminó el globo ortográfico y cualquier capacidad de giro o zoom.
- La red se muestra en una proyección equirectangular rectangular fija, acotada a Norteamérica para aprovechar el espacio disponible y hacer legibles los flujos México–Estados Unidos.
- Los 96 mercados permanecen como arcos seleccionables, ponderados por pasajeros, asientos o salidas. La selección de ruta/aeropuerto sigue sincronizada con perfil y lista.
- La geometría Natural Earth permanece local y autocontenida; no se agregaron solicitudes externas.

### Archivos modificados

- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones y siguiente paso

- Las 22 pruebas dirigidas y de regresión pasan.
- El mapa contiene 326 trazos SVG, no conserva el elemento del globo anterior y no produjo avisos de consola.
- Cobertura y ventana T-100 permanecen visibles junto al mapa. La Lista continúa como vista predeterminada a 360 y 736 px.
- Pausar para revisión. Ampliar la red mundial requerirá primero incorporar una fuente origen–destino distinta de la AFAC agregada actualmente en Gold.

## Entrega 6 · Enfoque de rutas por aeropuerto

### Resultado

- La vista en reposo muestra únicamente los 12 mercados con mayor valor según la métrica elegida como contexto tenue, además de la ruta seleccionada.
- Al pasar el cursor sobre un aeropuerto, las rutas no relacionadas se ocultan visualmente y se resaltan todas las conexiones observadas que llegan o salen de ese aeropuerto.
- El subtítulo cambia durante el enfoque para mostrar el código del aeropuerto y el número de rutas observadas. Al retirar el cursor se restaura el contexto resumido.
- La interacción no cambia el alcance: siguen siendo mercados bidireccionales T-100 México–Estados Unidos, no itinerarios comerciales ni toda la red mundial.

### Casos verificados

- `SEA`: 5 mercados observados (`MEX`, `GDL`, `ACA`, `AGU` y `QRO`). El hover mostró `SEA · 5 rutas observadas`.
- `ACA`: 8 mercados observados hacia aeropuertos estadounidenses. El hover mostró `ACA · 8 rutas observadas`.
- La Lista permanece como alternativa para teclado, tacto y pantallas de 360/736 px; ninguna consulta depende exclusivamente del hover.

### Archivos modificados y validación

- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

Las 22 pruebas dirigidas y de regresión pasan. Seattle y Acapulco se verificaron sobre la vista renderizada, incluida la restauración al retirar el cursor, sin avisos de consola ni solicitudes externas.

### Faltantes y siguiente paso

AFAC Gold sigue sin ofrecer grano origen–destino. La interacción mejora la lectura de la cobertura existente, pero una ampliación geográfica exige una fuente de rutas adicional, preservada y versionada. Pausar para comentarios antes de integrar navegación compartida.

## Entrega 7 · Detalle direccional y selección fija por aeropuerto

### Resultado

- Se eliminó el selector `Importancia de ruta`; pasajeros queda como criterio único para grosor, orden, concentración y selección de la ruta principal.
- Se retiraron el aviso `Cobertura parcial` y las cuatro tarjetas resumen de la red. El mapa comienza directamente debajo del título y mantiene su periodo y cobertura en el subtítulo.
- El hover sobre un aeropuerto muestra todos sus mercados observados, cada uno con un color diferente, total bidireccional y pasajeros por sentido.
- Si T-100 no contiene uno de los sentidos, se muestra `No disponible · Sin operación observada en este sentido`; no se convierte la ausencia en cero.
- Un clic sobre el aeropuerto fija todas sus conexiones, filtra la lista por ese código y lleva al perfil la ruta de mayor volumen de pasajeros. Un segundo clic sobre el mismo punto libera el conjunto.
- La detección del clic prioriza la posición visible del marcador frente a las líneas superpuestas, corrigiendo la selección accidental de una ruta distinta.

### Fuentes y linaje

- `fact_route_traffic` se une con `dim_route` para conservar origen y destino reportados en cada sentido dentro de la misma ventana móvil T-100.
- Cada total direccional se reconcilia contra el mercado bidireccional antes de producir `flight_dashboard_payload_v1`.
- El alcance permanece limitado a operaciones observadas México–Estados Unidos y al operador/reportante BTS Aeromexico (AM). No se infiere comercializador, ingreso ni rentabilidad.

### Archivos modificados

- `src/dashboard/flights.py`
- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones

- Las 22 pruebas dirigidas de Vuelos y regresión de Etapa 11 pasan.
- Los 96 mercados reconciliaron la suma de pasajeros por sentido contra su total bidireccional.
- Caso Miami verificado en la vista renderizada: seis mercados, seis colores, `MIA → MEX` 172,810 y `MEX → MIA` 170,912; la selección fija mantiene el conjunto al retirar el cursor y abre `MEX ↔ MIA`, la ruta de mayor volumen.
- El segundo clic libera Miami, limpia el filtro y restaura el contexto del mapa. No se registraron mensajes de consola ni solicitudes externas.

### Evidencia candidata, faltantes y siguiente paso

Sin cambios en elegibilidad: el detalle T-100 es contexto actual y no entra en `flight_evidence_v1`. No se modificó el análisis aprobado, no se inició backfill y no se recalculó ningún modelo. La lista accesible sigue siendo la alternativa inicial a 360 y 736 px. Pausar para comentarios antes de cualquier integración en navegación compartida.

## Entrega 8 · Interacción exclusiva por aeropuerto y red trimestral

### Resultado

- Las líneas del mapa quedaron como elementos visuales pasivos: no producen tooltip ni responden al clic. La interacción del mapa se limita a los puntos amarillos de aeropuerto.
- El tooltip detallado solo se abre al enfocar o seleccionar un aeropuerto y continúa mostrando sus mercados y pasajeros por sentido.
- La red ahora cambia junto con el selector de trimestre. Rutas, pasajeros, asientos, salidas, concentración, perfil y comparación se calculan únicamente con los meses T-100 pertenecientes al periodo seleccionado.
- La comparación de cada ruta usa los mismos meses del año anterior, evitando comparar un trimestre con una ventana móvil de doce meses.
- Cuando la fuente no cubre todo el trimestre se informa la cobertura observada y el mes faltante de forma explícita.

### Caso piloto 2T26

- T-100 local contiene abril y mayo de 2026, pero no junio. El mapa se rotula `2T26 · abr 2026–may 2026 · 2 de 3 meses disponibles; jun 2026 no disponible`.
- La red parcial observada contiene 40 mercados, 33 aeropuertos, 612,660 pasajeros, 758,735 asientos y 4,451 salidas.
- Miami muestra dos mercados en este periodo; `MEX ↔ MIA` registra 50,551 pasajeros, divididos en 26,180 `MIA → MEX` y 24,371 `MEX → MIA`.
- Al cambiar a 1T26, el mapa se actualiza a enero–marzo de 2026, se rotula como trimestre completo y muestra 47 mercados.

### Archivos modificados

- `src/dashboard/flights.py`
- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones, elegibilidad y siguiente paso

- Las 22 pruebas dirigidas de Vuelos y regresión de Etapa 11 pasan.
- En navegador se comprobó que el centro de una línea no genera tooltip ni selección; Miami sí abre el panel desde el punto amarillo.
- El cambio 2T26 → 1T26 actualizó periodo, rutas y perfil sin mensajes de consola.
- T-100 continúa fuera de `flight_evidence_v1`: la copia local no demuestra disponibilidad histórica exacta al corte. No se modificó el análisis aprobado, no se inició backfill y no se recalculó ningún modelo.

Pausar para comentarios antes de la siguiente ampliación.

## Entrega 9 · Tooltip trimestral y detalle de rutas junto al mapa

### Resultado

- El tooltip de capacidad y demanda presenta una sola cabecera por periodo. Para la vista trimestral usa el nombre completo del trimestre y muestra, en este orden, total, nacional e internacional.
- Nacional e internacional incluyen pasajeros y participación sobre el total; cada serie conserva su identificador de color azul o amarillo y el total usa un identificador oscuro.
- El mapa ocupa la columna izquierda y el detalle del aeropuerto seleccionado permanece en una columna fija a la derecha, fuera del área cartográfica.
- La columna lateral presenta todos los mercados del aeropuerto en una tabla con ruta, pasajeros, asientos, salidas y ocupación. Cada fila conserva el color de su flujo y muestra también los pasajeros observados por sentido.
- Se retiraron los bloques inferiores `Perfil de ruta seleccionada` y `Concentración de la red observada`, porque sus métricas relevantes ya están consolidadas en la tabla lateral.
- La interacción continúa limitada a los puntos amarillos de aeropuerto. Las líneas permanecen como elementos visuales pasivos.

### Caso verificado

- El tooltip de `1T24` muestra una única cabecera `Primer trimestre de 2024`, total de 5,924,477 pasajeros, nacional de 3,968,475 (67.0%) e internacional de 1,956,002 (33.0%).
- Al seleccionar `MEX`, la tabla lateral muestra 22 mercados y cinco columnas. La primera fila, `LAX ↔ MEX`, presenta 75,284 pasajeros, 89,616 asientos, 487 salidas y 84.0% de ocupación; los sentidos son 37,143 `LAX → MEX` y 38,141 `MEX → LAX`.

### Archivos modificados

- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones, faltantes y siguiente paso

- Las 22 pruebas dirigidas de Vuelos y regresión de Etapa 11 pasan.
- La tabla lateral no presenta desbordamiento horizontal, queda alineada con la parte superior del mapa y mantiene 14 px de separación en escritorio.
- La vista renderizada no contiene los bloques retirados ni produce mensajes de consola.
- La Lista continúa como alternativa accesible y vista inicial a 360 y 736 px.
- No cambió la elegibilidad de fuentes: T-100 permanece como contexto actual fuera de `flight_evidence_v1`. No se modificó el análisis aprobado, no se inició backfill, no se recalculó ningún modelo y no se tocaron la navegación compartida ni el HTML principal.

Pausar para comentarios antes de la siguiente ampliación.

## Entrega 10 · Desagregación direccional y alineación visible del mapa

### Resultado

- `MEX · Mexico City` queda seleccionado de forma predeterminada al abrir la vista y al cambiar de trimestre cuando existen rutas observadas para el aeropuerto.
- La columna `Salidas` se presenta al usuario como `Vuelos`. La métrica subyacente continúa siendo `departures_performed` de BTS T-100: salidas efectivamente realizadas, no vuelos anunciados ni itinerarios comercializados.
- Cada mercado conserva su total bidireccional y añade dos renglones visuales coordinados, uno por sentido, en pasajeros, asientos, vuelos y ocupación. La ocupación direccional se calcula como pasajeros divididos entre asientos del mismo sentido.
- El panel lateral se alinea contra el marco geográfico realmente dibujado por Plotly. Esto elimina la diferencia visual causada por el espacio que la proyección dejaba arriba y abajo dentro del contenedor del mapa.
- El hover de cada punto amarillo muestra una etiqueta breve con código IATA y ciudad; el detalle completo continúa en la tabla lateral.

### Caso verificado

- `LAX → MEX`: 37,143 pasajeros, 44,671 asientos, 243 vuelos y 83.1% de ocupación.
- `MEX → LAX`: 38,141 pasajeros, 44,945 asientos, 244 vuelos y 84.9% de ocupación.
- Total `LAX ↔ MEX`: 75,284 pasajeros, 89,616 asientos, 487 vuelos y 84.0% de ocupación.
- En navegador, el marco geográfico y el panel lateral miden 486.67 px de alto; sus bordes superior e inferior difieren menos de 0.03 px y no existe desbordamiento horizontal.
- La etiqueta del punto se comprobó con `NLU · Mexico City`.

### Archivos modificados

- `src/dashboard/flights.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones, elegibilidad y siguiente paso

- Pasajeros, asientos y vuelos de cada sentido reconcilian con el total bidireccional de todos los mercados incluidos.
- Las ocupaciones total y direccionales usan sus propios pasajeros y asientos; no se promedian porcentajes.
- Las 22 pruebas dirigidas de Vuelos y regresión de Etapa 11 pasan.
- T-100 permanece como contexto actual fuera de `flight_evidence_v1`. No se modificó el análisis aprobado, no se inició backfill, no se recalculó ningún modelo y no se tocaron la navegación compartida ni el HTML principal.

Pausar para comentarios antes de la siguiente ampliación.

## Entrega 11 · Limpieza del encabezado y encuadre superior de la red

### Resultado

- Se retiraron el título interno `Mapa fijo de flujos operados` y su subtítulo dinámico.
- Se eliminó la instrucción situada debajo del mapa; la columna izquierda contiene únicamente la visualización.
- Mapa y tabla comienzan inmediatamente al inicio del panel, sin margen adicional entre el encabezado de sección y el contenido.
- El encuadre geográfico se ajustó al corredor México–Estados Unidos para eliminar el espacio blanco que la proyección dejaba arriba y abajo.
- La línea bajo el aeropuerto seleccionado se simplificó a `2T26 · 22 rutas observadas · Selecciona el destino para ver el detalle.`; se actualiza con el trimestre y el número de rutas del punto activo.

### Archivos modificados

- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones y siguiente paso

- En escritorio, el mapa dibujado y el panel lateral comienzan en la misma coordenada y ambos miden 571 px de alto.
- El espacio superior interno del mapa es nulo dentro de la tolerancia de renderizado de medio píxel.
- La tabla conserva sus cinco columnas, no presenta desbordamiento horizontal y `MEX · Mexico City` permanece como selección inicial.
- Las 22 pruebas dirigidas de Vuelos y regresión de Etapa 11 pasan; la vista no produce mensajes de consola.
- No se modificaron fuentes, elegibilidad, navegación compartida, HTML principal, backfill ni modelos.

Pausar para comentarios antes de la siguiente ampliación.

## Entrega 12 · Limpieza de demanda y variación interanual por ruta

### Resultado

- Los tooltips trimestrales de pasajeros usan el código corto del periodo, por ejemplo `2T26`, en lugar del nombre desarrollado del trimestre.
- Se conservaron únicamente el título `Pasajeros y contribución por segmento` y el selector de periodo dentro de la tarjeta. Se retiraron el subtítulo descriptivo y la conciliación inferior AFAC Gold–SEC.
- La altura de la gráfica bajó de 430 a 390 px en escritorio; las variantes de 736 y 420 px también se compactaron.
- Junto al total de pasajeros de cada mercado se añadió un chip pequeño con la variación contra los mismos meses del año anterior. El chip no se repite en asientos, vuelos, ocupación ni filas direccionales.
- Si el trimestre T-100 está incompleto, la línea del aeropuerto muestra en negritas el mes faltante entre el trimestre y el número de rutas. Para 2T26 se presenta `Falta junio de 2026`.

### Comparabilidad y caso verificado

- Como 2T26 solo contiene abril y mayo, los chips comparan abril–mayo de 2026 contra abril–mayo de 2025; no comparan dos meses actuales con tres meses históricos.
- `LAX ↔ MEX` muestra 75,284 pasajeros y un chip de `-9.9%`, calculado contra 83,562 pasajeros en abril–mayo de 2025.
- Cuando el mercado no tiene base comparable se muestra `N/D`, nunca cero.

### Archivos modificados

- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones y siguiente paso

- En navegador se comprobó el tooltip `2T26` con total, nacional e internacional; el subtítulo y la nota retirados ya no existen en el documento.
- El aviso `Falta junio de 2026` tiene peso 850 y la tabla lateral no presenta desbordamiento horizontal.
- Las 22 pruebas dirigidas de Vuelos y regresión de Etapa 11 pasan; no se registraron mensajes de consola.
- No se modificaron fuentes, elegibilidad, navegación compartida, HTML principal, backfill ni modelos.

Pausar para comentarios antes de la siguiente ampliación.

## Entrega 13 · Búsqueda integrada y comparativos completos por ruta

### Resultado

- Se retiraron el selector `Mapa / Lista` y la vista de lista independiente; la red conserva una sola experiencia sin duplicar la tabla de detalle.
- Se añadió una lupa en la esquina superior derecha del panel de rutas. El buscador acepta código IATA, ciudad o nombre del aeropuerto, ignora acentos y muestra hasta ocho coincidencias con su número de rutas.
- Elegir un resultado actualiza simultáneamente el punto fijado, los flujos del mapa, el encabezado y la tabla. También se puede elegir la primera coincidencia con `Enter` y cerrar con `Escape`.
- Cada total de mercado presenta ahora cuatro comparativos contra los mismos meses del año anterior: pasajeros, asientos, vuelos y ocupación. Los tres primeros se expresan como variación porcentual y ocupación como diferencia en puntos porcentuales.
- Los chips aparecen solo junto a los totales bidireccionales; las dos filas direccionales conservan exclusivamente sus valores de ida y vuelta. Ante ausencia de base comparable se muestra `N/D`.

### Comparabilidad y casos verificados

- Para `LAX ↔ MEX`, abril–mayo de 2026 contra abril–mayo de 2025 muestra `-9.9%` en pasajeros, `-9.3%` en asientos, `-6.0%` en vuelos y `-0.6 pp` en ocupación.
- La búsqueda de `Miami` devuelve `MIA · Miami` con dos rutas y, al seleccionarla, la tabla cambia a `MEX ↔ MIA` y `CUN ↔ MIA`.
- El periodo incompleto continúa visible como `2T26 · Falta junio de 2026`; ningún comparativo incorpora junio de 2025.

### Archivos modificados

- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones y siguiente paso

- Las 22 pruebas dirigidas de Vuelos y regresión de Etapa 11 pasan.
- En navegador se comprobó la búsqueda por ciudad, el cambio a MIA, cuatro chips en cada total y la ausencia de la vista y el selector de lista.
- En escritorio, el mapa mide 570 px y el panel lateral 571 px; no existe desbordamiento horizontal ni mensajes de consola asociados a la interacción verificada.
- No se modificaron fuentes, elegibilidad, navegación compartida, HTML principal, backfill ni modelos.

Pausar para comentarios antes de la siguiente ampliación.

## Entrega 14 · Orden final de la vista autónoma

### Resultado

- Se mantuvieron los KPI trimestrales inmediatamente después del encabezado.
- La sección `Red observada` se movió por encima de `Capacidad y demanda`, de modo que el mapa y la tabla de rutas preceden a la gráfica de pasajeros y mezcla nacional/internacional.
- No se alteraron la interacción del mapa, el buscador, los comparativos, el selector mensual/trimestral ni la perspectiva secundaria de la vista autónoma.

### Archivos modificados

- `src/dashboard/flights_html.py`
- `tests/test_flights_prototype.py`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validaciones y siguiente paso

- Una prueba de estructura exige ahora el orden `Red observada` antes de `Mezcla nacional e internacional`.
- Las 22 pruebas dirigidas de Vuelos y regresión de Etapa 11 pasan.
- La jerarquía resultante se comprobó en navegador: KPI, red observada, capacidad y demanda, perspectiva secundaria y metodología.
- El siguiente paso propuesto es integrar únicamente KPI, red observada y capacidad/demanda en la pestaña Vuelos del dashboard principal; el forecast queda omitido por ahora.

Pausar para la integración en una sesión separada.

## Entrega 15 · Detalle direccional desplegable en la red integrada

### Resultado

- Cada mercado muestra inicialmente una sola fila con la ruta en negritas y los totales de pasajeros, asientos, vuelos y ocupación.
- Un control `>` situado junto al nombre de la ruta despliega o contrae los dos sentidos con sus métricas direccionales alineadas bajo las mismas columnas.
- Todos los mercados comienzan contraídos; el control expone `aria-expanded`, funciona con teclado y rota al abrirse.
- La tipografía de los totales aumentó un punto, de 8.9 px a 9.9 px.

### Archivos modificados

- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `tests/test_stage18_integration.py`
- `prototypes/vuelos/vuelos_revision.html`
- `prototypes/etapa-11/resumen_ejecutivo.html`
- `docs/assets/vuelos/red-rutas-desplegable.png`
- `docs/etapas/vuelos-reporte.md`

### Validaciones

- Se regeneraron la revisión autónoma y el HTML local integrado mediante sus generadores.
- Las 34 pruebas dirigidas de Vuelos, Etapa 11, integración y navegación pasan.
- En navegador se verificaron 22 rutas contraídas por defecto, una sola fila direccional abierta al seleccionar `LAX ↔ MEX`, ausencia de desbordamiento horizontal y cero errores de página.
- El detalle abierto reconcilia `LAX → MEX` y `MEX → LAX` con los valores direccionales ya validados.

Pausar para comentarios.

## Entrega 15 · Integración como tercera pestaña del dashboard principal

### Resultado

- `Vuelos` quedó integrada como la tercera pestaña del HTML principal, después de `Lectura ejecutiva` y `Economía unitaria`. El orden se declara en `src/dashboard/navigation.py` y el flujo aprobado de consumer payload continúa generando `prototypes/etapa-11/resumen_ejecutivo.html`.
- El panel integrado reutiliza `build_flight_payload`, el marcado compartido de `flights_html.py` y los mismos JavaScript/CSS de la vista autónoma. El payload para el HTML principal se proyecta a los campos consumidos por KPI, red y capacidad/demanda para mantener el artefacto por debajo de 6 MB.
- Se incluyeron únicamente los cuatro KPI trimestrales, la red observada México–Estados Unidos y la serie histórica de pasajeros con selector `Trimestral/Mensual`. Forecast, metodología y sus datos no se incrustan en el dashboard principal; permanecen sin cambios funcionales en la vista autónoma.
- El selector trimestral del encabezado es global y actualiza la lectura ejecutiva, los KPI de Vuelos y la red T-100. `MEX · Mexico City` permanece como aeropuerto inicial.
- La navegación por teclado admite cualquier cantidad de pestañas: flechas izquierda/derecha recorren circularmente el conjunto; Inicio y Fin llevan a los extremos.

### Cifras reconciliadas y linaje

- KPI SEC 2T26: 6,014,000 pasajeros, 9,256 millones de ASM, 7,851 millones de RPM y 84.9% de ocupación, con periodo 1 de abril–30 de junio de 2026 y corte 13 de julio de 2026.
- La mezcla reconstruida desde los tres comunicados mensuales SEC suma 3,936,000 pasajeros nacionales + 2,078,000 internacionales = 6,014,000 total.
- La visual histórica AFAC Gold para abril–junio de 2026 suma 3,856,840 nacionales + 2,060,171 internacionales = 5,917,011. La diferencia de 96,989 frente al KPI consolidado SEC se conserva como diferencia de alcance documentada; las dos fuentes no se sustituyen ni se fuerzan a coincidir.
- La red T-100 de 2T26 conserva abril–mayo de 2026: 40 mercados, 33 aeropuertos, 612,660 pasajeros, 758,735 asientos y 4,451 vuelos. La interfaz muestra explícitamente `Falta junio de 2026` y compara contra abril–mayo de 2025.
- `LAX ↔ MEX` conserva 75,284 pasajeros, 89,616 asientos, 487 vuelos y 84.0% de ocupación; sus comparativos son -9.9%, -9.3%, -6.0% y -0.6 pp. Los sentidos conservan 37,143 pasajeros `LAX → MEX` y 38,141 `MEX → LAX`.

### Archivos modificados

- `src/dashboard/navigation.py`
- `src/dashboard/flights_html.py`
- `src/dashboard/assets/flights.js`
- `src/dashboard/assets/flights.css`
- `src/analysis_agent/reader_ui.py`
- `src/analysis_agent/stage18.py`
- `tests/test_dashboard.py`
- `tests/test_stage18_integration.py`
- `prototypes/etapa-11/resumen_ejecutivo.html`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/etapas/vuelos-reporte.md`

### Validación

- Las 34 pruebas dirigidas de Vuelos, Etapa 11, integración Etapa 18 y dashboard principal pasan.
- En navegador se verificaron clic y teclado en las tres pestañas; cambio global 2T26 → 1T26; selección inicial MEX; búsqueda de `Miami`; tabla resultante con `MEX ↔ MIA` y `CUN ↔ MIA`; selector Trimestral/Mensual; y persistencia de MIA al hacer clic sobre una línea del mapa, confirmando que las líneas son pasivas.
- A 360 px, 736 px y escritorio no existe desbordamiento horizontal del documento. A 360 px las tres pestañas permanecen visibles, la tabla usa desplazamiento horizontal dentro de su panel y el eje histórico reduce las etiquetas a intervalos bienales. El control de periodo mide 38 px de alto y conserva foco visible.
- El navegador no registró errores ni advertencias de consola. El servidor local recibió únicamente el HTML y la solicitud automática local de favicon; no hubo solicitudes externas.
- El HTML principal mide 5,864,275 bytes, permanece autocontenido, no contiene identificadores duplicados y conserva exactamente la versión de análisis aprobada indicada en su manifest.

### Elegibilidad y límites

- `flight_evidence_v1` continúa como `candidate_unapproved`; no se activó en el Analysis Agent ni se modificó el análisis aprobado.
- La serie histórica AFAC Gold y T-100 continúan fuera del paquete histórico 2T26 por no demostrar la versión exacta disponible al corte. T-100 representa segmentos observados del operador/reportante Aeromexico (AM) entre México y Estados Unidos; no representa toda la red mundial, comercialización, codeshare, ingresos ni rentabilidad.
- No se inició backfill, no se recalcularon modelos y no se creó contenido para Competencia, Finanzas o Datos.

Pausar para comentarios antes de continuar con otra pestaña.

## Entrega 16 · Redistribución de KPI entre Lectura ejecutiva y Economía unitaria

### Resultado

- `Lectura ejecutiva` conserva únicamente la narrativa aprobada y deja de mostrar tarjetas KPI.
- `Economía unitaria` muestra cuatro tarjetas: RASK, CASK, ASK y el nuevo Margen unitario, calculado como RASK menos CASK.
- Factor de ocupación y Pasajeros se retiraron de Economía unitaria para evitar duplicarlos con Vuelos.
- `Vuelos` conserva sus cuatro tarjetas: Pasajeros, ASM, RPM y Ocupación.
- El nuevo Margen unitario responde al selector trimestral global y muestra comparativos contra el trimestre anterior y el mismo trimestre del año anterior.

### Archivos modificados

- `src/analysis_agent/reader_ui.py`
- `src/dashboard/assets/executive_summary.js`
- `src/dashboard/assets/executive_summary.css`
- `tests/test_stage18_integration.py`
- `prototypes/etapa-11/resumen_ejecutivo.html`
- `docs/etapas/vuelos-reporte.md`

### Validación

- Las pruebas dirigidas confirman cero tarjetas en Lectura ejecutiva, cuatro en Economía unitaria y cuatro en Vuelos.
- En 2T26, Margen unitario muestra `+0.43 ¢ USD`, con `-0.68 ¢ USD` contra el trimestre anterior y `-1.18 ¢ USD` contra el año anterior.
- En navegador se verificaron las tres pestañas a 360 px, 736 px y escritorio. Las cuadrículas quedan en dos columnas en móvil y pantalla mediana, y en cuatro columnas en escritorio.
- No existe desbordamiento horizontal del documento. La tabla histórica mantiene su propio desplazamiento horizontal cuando lo necesita.
- El HTML permanece autocontenido, sin identificadores duplicados ni recursos externos.

Pausar para comentarios antes de continuar con otra pestaña.

## Entrega 17 · Acento visual del Margen unitario

- La tarjeta de Margen unitario usa ahora el verde oficial del dashboard en su borde superior, con el mismo grosor y formato que RASK, CASK y ASK.
- Se añadió una prueba para exigir la variable de color válida en futuras generaciones.
- Las 34 pruebas dirigidas pasan y el navegador confirma un borde superior verde sólido de 3 px.

## Entrega 18 · Retiro de la leyenda de elegibilidad en Vuelos

- Se retiró del panel integrado y de la vista autónoma la leyenda de periodo, corte y elegibilidad que aparecía debajo de los cuatro KPI.
- La elegibilidad se conserva en `flight_evidence_v1` como metadato de auditoría. El paquete permanece `candidate_unapproved` y requiere revisión manual antes de alimentar al Analysis Agent.
- Las 34 pruebas dirigidas pasan. La vista móvil a 360 px muestra `Red observada` inmediatamente después de las tarjetas, sin la leyenda retirada ni desbordamiento horizontal.
- Se regeneraron `prototypes/etapa-11/resumen_ejecutivo.html` y `prototypes/vuelos/vuelos_revision.html`. Este cambio permanece local y no se publicó.

## Entrega 19 · Detalle direccional plegable por ruta

### Resultado

- El panel derecho muestra inicialmente una sola fila en negritas por mercado, con sus totales de pasajeros, asientos, vuelos y ocupación.
- Cada fila incorpora un único control `>`; al activarlo se despliegan exclusivamente los dos sentidos de esa ruta y el control comunica su estado con `aria-expanded`.
- Los totales aumentaron exactamente 1 px, de 9.9 px a 10.9 px, para mejorar su lectura sin aumentar la densidad del panel.

### Archivos modificados

- `src/dashboard/assets/flights.css`
- `tests/test_flights_prototype.py`
- `tests/test_stage18_integration.py`
- `prototypes/etapa-11/resumen_ejecutivo.html`
- `prototypes/vuelos/vuelos_revision.html`
- `docs/assets/vuelos/entrega-19-rutas-plegables.png`
- `docs/etapas/vuelos-reporte.md`

### Validación

- Las 34 pruebas dirigidas de Vuelos, Etapa 11, integración Etapa 18 y dashboard principal pasan.
- En navegador, las 22 rutas de MEX empiezan colapsadas; abrir LAX–MEX muestra una sola sección de detalle con dos sentidos.
- El mapa y el panel derecho conservan el mismo alto (570 px), el total computado mide 10.9 px y no se registraron errores de página.
- Se regeneraron ambos HTML locales. No se desplegó ni se modificó el estado del Analysis Agent.


## Entrega 20 · Rutas internacionales mediante Bronze, Silver y Gold

Se integran ANAC Brasil, Aerocivil Colombia y CAA Reino Unido. En 2T26, 46 mercados y 39 aeropuertos; seis mercados nuevos con MEX. Los 298 registros normalizados conservan linaje hasta Bronze. Fuente y meses visibles; métricas ausentes N/D; ninguna activación histórica del agente ni despliegue.

Validación: 40 pruebas dirigidas y UI offline en 360/736/1440 px, sin solicitudes externas. Reporte y comandos en [vuelos-integracion-internacional-20260908.md](vuelos-integracion-internacional-20260908.md).

## Entrega 21 · Nacional programado y España visible

La vista local ofrece Nacional · programado e Internacional · observado. El PDF AM de slots del AICM aporta 45 rutas mexicanas y 31,098 asignaciones de abril–junio de 2026, con linaje Bronze → Silver → Gold y etiqueta explícita de programación. Madrid y Barcelona conservan la actividad por compañía y aeropuerto Aena en ambas vistas. No se atribuyen pasajeros ni vuelos efectivamente realizados a las rutas nacionales, y estos slots quedan fuera del expediente histórico del Analysis Agent. Validación: 22 pruebas enfocadas, comprobación en navegador a 360/736/1440 px y capturas. Detalle en [vuelos-nacional-aicm-integracion-20260913.md](vuelos-nacional-aicm-integracion-20260913.md).

## Entrega 22 · Cobertura internacional ampliada a escala mundial

El mismo PDF AICM aporta 13,662 asignaciones internacionales de abril–junio en 50 destinos; 25 mercados se agregan a la vista internacional sin duplicar los 25 que ya tenían fuente observada. OMA añade MTY–CDG, con 68 movimientos programados derivables de su frecuencia, y MTY–MAD con presencia confirmada y volumen sin desglose. El mapa local muestra ahora 73 mercados internacionales y permite localizar Canadá, España, Japón, Corea y otros destinos antes ausentes. Las capas internacionales nuevas conservan Silver, Gold y puentes de linaje; mantienen los slots como programación y la precedencia de fuentes observadas. Bajo el supuesto explícito de contar los slots como vuelos realizados para estimar cobertura, el escenario llega a **97.6%** de los vuelos regulares de Aerovías y Connect del 2T26; no se presenta como porcentaje verificado. El análisis histórico aprobado permanece intacto. Método, brechas y captura en [vuelos-cobertura-ampliada-20260913.md](vuelos-cobertura-ampliada-20260913.md).
