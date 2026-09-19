# España: Aena en Bronze, Silver, Gold y HTML local

## Revisión del portal y presentación actual

Se volvió a entrar a la sesión autenticada de [Consultas personalizadas de Aena](https://www.aena.es/es/estadisticas/consultas-personalizadas.html) el 12 de septiembre de 2026. En el editor de **Pasajeros por Compañía** y **Operaciones por Compañía**, el conjunto de datos expone `Compañía`, `Aeropuerto Base`, `Mes`, `País` y la métrica, pero no `Aeropuerto ORI/DES` ni `Aeropuerto Escala`. En **Operaciones por O/D**, expone `Aeropuerto Base`, `Aeropuerto ORI/DES`, `Mes` y la métrica, pero no `Compañía`. Las cuatro exportaciones originales conservadas confirman esa separación. Por tanto, la interfaz y los archivos verificados no permiten extraer directamente compañía × ambos aeropuertos × mes. La sesión seguía iniciada; no hizo falta otra autenticación.

Se incorporaron al [HTML local principal](../../prototypes/etapa-11/resumen_ejecutivo.html) y al [prototipo Vuelos](../../prototypes/vuelos/vuelos_revision.html) las cifras **por compañía y aeropuerto español** que sí están disponibles. Para 2T26, Madrid muestra 188,234 pasajeros y 780 operaciones; Barcelona, 31,808 y 156. Cada tarjeta muestra sus meses, y los periodos incompletos se marcan como parciales. No se trazó MEX–MAD ni MEX–BCN con esos totales: la cifra de Madrid podría combinar MEX, GDL y MTY. El mapa permanece reservado a observaciones verificadas por ruta; el bloque español muestra la actividad por aeropuerto sin inventar una distribución.

La presentación consume la tabla Gold ya normalizada y el campo `operations` corregido, sin añadir estos datos al expediente histórico del Analysis Agent ni publicar Streamlit. El enlace a Aena lleva a la consulta, no al CSV autenticado exacto; los originales, hashes y localizadores siguen preservados en Bronze/Silver/Gold.

Validación de esta revisión: 17 pruebas de rutas y Vuelos, 3 pruebas de integración del HTML, comprobación sintáctica de JavaScript y lectura del dashboard local en 2T26 y 1T26. El payload publicado contiene las dos tarjetas de 2T26 y ninguna ruta sintética MEX–MAD o MEX–BCN. En 1T26 Barcelona indica solo marzo; Madrid indica enero–marzo.

Actualización: la [investigación complementaria](vuelos-espana-fuentes-alternativas-20260912.md) aclara cómo usar los agregados de Aeroméxico por aeropuerto e identifica fuentes para rutas. También corrigió en Silver/Gold la métrica de Aena `Operaciones Totales`, ahora `operations` en vez de `departures`.

Fecha de cierre: 12 de septiembre de 2026. Este incremento continúa la [verificación autenticada](vuelos-espana-verificacion-20260909.md). La sesión iniciada por el usuario permitió descargar cuatro CSV originales desde [Consultas personalizadas de Aena](https://www.aena.es/es/estadisticas/consultas-personalizadas.html). La página es un punto de consulta autenticado; los archivos exportados no tienen URL pública permanente.

## Corrección de presentación tras revisar las cuatro exportaciones

La primera versión del [HTML local](../../prototypes/etapa-11/resumen_ejecutivo.html) dibujó MEX–MAD y MEX–BCN con métricas de Aeroméxico en N/D y un panel de contexto. Esa representación sugería que se habían identificado rutas de la compañía con datos operativos. **Se retiraron ambas líneas del mapa** tras la revisión solicitada por el usuario. Los cuatro CSV y las 52 observaciones normalizadas se conservan en Bronze, Silver y Gold para uso contextual o una futura reconciliación con una fuente de mayor granularidad.

Los encabezados originales son:

| Exportación Aena | Dimensiones y métrica |
|---|---|
| Operaciones por compañía | Compañía, Aeropuerto Base, Mes, Operaciones Totales |
| Pasajeros por compañía | Compañía, Aeropuerto Base, Mes, Pasajeros Totales |
| Operaciones O/D | Aeropuerto ORI/DES, Aeropuerto Base, Mes, Operaciones Totales |
| Pasajeros por escala | Aeropuerto Escala, Aeropuerto Base, Mes, Pasajeros Totales |

En las dos consultas por compañía falta el otro extremo de la ruta; en las dos consultas por aeropuertos falta la compañía. El editor del portal muestra estos mismos conjuntos de datos separados. Los informes detallados de compañía y de rutas también tienen filtros separados. Esto verifica la limitación **de los cuatro archivos exportados y las vistas examinadas**, sin afirmar que ninguna otra fuente de Aena pueda proporcionar el cruce.

## Alcance de los datos conservados

La cifra de la compañía corresponde a su actividad **en el aeropuerto español**, sin contraparte de ruta en esa tabla. La cifra MEX–MAD o MEX–BCN corresponde a **todas las aerolíneas**. “Operaciones” es la métrica original de Aena; no se convierte en vuelos de Aeroméxico por ruta.

| 2T26, abril–junio | Aerovías de México en aeropuerto español | Mercado entre aeropuertos, todas las compañías |
|---|---:|---:|
| Madrid: pasajeros / operaciones | 188,234 / 780 | MEX–MAD: 275,898 / 1,089 |
| Barcelona: pasajeros / operaciones | 31,808 / 156 | MEX–BCN: 61,862 / 338 |

Son agregados de tres meses completos de cada exportación; no hay comparación interanual en el expediente descargado. La presencia simultánea de la compañía y el mercado **no identifica cuántos pasajeros u operaciones de Aeroméxico pertenecen a MEX–MAD o MEX–BCN**. El 20-F archivado en SEC el 30 de abril de 2026 menciona Madrid y la adición prevista de Barcelona, pero una ruta prevista tampoco sustituye una tabla operacional por compañía y origen–destino.

## Originales y linaje

Cada CSV es UTF-16 y conserva su versión en `data/bronze/international_routes/`, con `.meta.json`, entrada en `data/bronze/_manifest.jsonl`, SHA-256 y fecha de descarga UTC. La selección activa está en `data/bronze/international_routes/selection.json`; se guardó también un comprobante `selection-*.json`. Los localizadores en Silver y Gold tienen formato `record:n` y se resuelven por `bridge_international_route_lineage` hacia `dim_source_artifact`.

La captura inicial registró `http_status: 200` mediante el valor predeterminado del guardado en Bronze; ese campo **no fue observado en la interfaz del navegador** y no debe usarse como comprobación HTTP de la exportación. El importador ahora registra `0` (estado no capturado) para futuras descargas manuales. Los cuatro originales y sus metadatos iniciales se conservaron sin sobrescribir.

| Selección | Original Bronze | SHA-256 |
|---|---|---|
| Compañía, operaciones | [CSV](../../data/bronze/international_routes/aena_company_operations_2026M01-2026M07_20260912T135952Z.csv) | `a701b141e5dc239607d161b5b1c3c6216d8c1dc9d013c5f6af39201abf58107c` |
| Compañía, pasajeros | [CSV](../../data/bronze/international_routes/aena_company_passengers_2026M01-2026M07_20260912T135952Z.csv) | `c768509585ec02f955e4cf122dc2ad8b58f0b9477c195b7f24a0ff70be205294` |
| Aeropuertos, operaciones | [CSV](../../data/bronze/international_routes/aena_market_operations_2026M01-2026M07_20260912T135952Z.csv) | `e5340c1ac887fc0ef4c7dc2249400625de2cf4085591092ca03bc13b3d8487c8` |
| Aeropuertos, pasajeros | [CSV](../../data/bronze/international_routes/aena_market_passengers_2026M01-2026M07_20260912T135952Z.csv) | `678d11544eb48f4c8d76117f363eb830bde76eacb5a3b77dc0a27ef7a9de4c73` |

La transformación `src/transform/international_routes.py` produjo 52 observaciones Aena en [Silver](../../data/silver/international_routes/observations.parquet) y [Gold](../../data/gold/fact_international_route_observations.parquet), distribuidas entre `carrier_airport` y `market_route`. Las 52 referencias de registro enlazan con cuatro artefactos únicos. Los originales de Bronze son locales y se excluyen de Git; requieren la misma conservación externa que el resto del archivo Bronze si se traslada el proyecto.

## Controles y límites

- Se verificaron hashes, 2026 y los siete meses de cada exportación, etiquetas de aeropuerto, operador, granularidad, duplicados, métricas no negativas y vínculos de linaje. La fecha de cada fila se lee del CSV; no se fija a 2026 dentro del transformador.
- La URL de Aena está catalogada como `landing_page_only`, ya que conduce a la consulta y no al CSV exacto.
- Se regeneraron el prototipo de Vuelos y el resumen ejecutivo local desde sus generadores; el análisis aprobado del 2T26 no se modificó. Una revisión posterior retiró los dos mercados españoles del mapa.
- La primera integración pasó 28 pruebas enfocadas. La corrección posterior se verificó con las pruebas de rutas y del HTML; el mapa ya no presenta entradas Aena sin métricas atribuibles a Aeroméxico.
- La fecha de publicación original de las consultas no quedó verificada. La exportación descargada el 12 de septiembre incluye julio de 2026; por ello estas observaciones **no son elegibles** para el Analysis Agent histórico al corte del 13 de julio de 2026. Tampoco se deducen asientos, factor de ocupación ni cuotas de Aeroméxico por ruta.
- La siguiente mejora de cobertura española requiere una fuente que reúna compañía, ambos aeropuertos y mes, o una respuesta oficial equivalente. No se incorporó esta evidencia al análisis histórico ni se publicó en Streamlit.
