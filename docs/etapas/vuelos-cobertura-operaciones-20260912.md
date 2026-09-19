# Cobertura operativa de Vuelos frente a AFAC

> **Actualización del 13 de septiembre:** se integró una vista distinta de [45 rutas nacionales programadas desde/hacia el AICM](vuelos-nacional-aicm-integracion-20260913.md), obtenidas del PDF oficial de slots AM. Las cifras de esta página sobre rutas **observadas** y el indicador provisional no deben sumarse a los slots ni leerse como una cobertura de operaciones efectivamente realizadas. La afirmación más abajo de que el mapa carece de rutas nacionales describe el estado anterior a ese incremento.

Fecha de revisión: 12 de septiembre de 2026. Diagnóstico de la vista local, la capa Gold y dos libros AFAC preservados. No modifica fuentes, mapa ni Analysis Agent.

## Qué aparece hoy

Para 2T26, `build_flight_payload()` entrega 46 mercados bidireccionales observados de Aerovías de México: 40 México–Estados Unidos (BTS T-100, abril–mayo), cuatro México–Colombia (Aerocivil, abril–junio), uno México–Brasil (ANAC, abril–junio) y uno México–Reino Unido (CAA, solo junio). Aena agrega Madrid y Barcelona por **compañía × aeropuerto español**, fuera del conteo de rutas porque falta la contraparte mexicana.

La red no incluye rutas nacionales, Canadá, Japón, Corea, ni otras rutas sudamericanas fuera de Brasil/Colombia. Chile tiene registros históricos investigados, pero Aeroméxico no aparece en abril–julio 2026 del CSV JAC revisado; Perú y Argentina siguen sin conjunto integrado. AFAC sí registra mercados de esos países, pero sin compañía por ruta.

## Porcentaje provisional de operaciones observadas por ruta

La ventana comparable disponible para la mayoría de las fuentes es **abril–mayo de 2026**. El libro [AFAC Resumen por aerolínea, julio 2026](https://www.gob.mx/cms/uploads/attachment/file/1100279/resumen-julio-2026-27082026.xlsx), hoja `VLOSREG`, registra para Aeroméxico (Aerovías de México) 14,653 vuelos nacionales (`E10:F10`) y 8,459 internacionales (`E27:F27`), total 23,112. Connect figura en filas 11 y 28 y **no está incluido** en ese denominador.

En el warehouse, para el mismo bimestre y operador AMX:

| Fuente | Movimientos/segmentos regulares con ruta identificada | Comprobación |
|---|---:|---|
| BTS T-100 México–EE. UU. | 4,446 | `fact_route_traffic`, `carrier_key='AEROMEXICO'`, abril–mayo, `service_class='F'`, suma de `departures_performed` |
| Aerocivil Colombia | 681 | `fact_international_route_observations`, AMX, abril–mayo, `carrier_route`, suma de `departures` tras filtro regular internacional y aeropuerto de registro |
| ANAC Brasil | 122 | Misma tabla, AMX, abril–mayo, servicio regular, suma de despegues |
| **Total visible por ruta** | **5,249** | Fuentes y mercados distintos; no se han completado reconciliaciones vuelo a vuelo entre autoridades |

**Indicador provisional:** 5,249 / 23,112 = **22.7%** de los vuelos regulares de Aerovías de México en abril–mayo representados por observaciones con compañía y ruta. Frente a los 8,459 vuelos internacionales de esa compañía, 5,249 / 8,459 = **62.1%**. No es un porcentaje certificado de la red: las autoridades no comparten necesariamente idéntica definición de vuelo/etapa, parte de BTS puede reportar revisiones, y el denominador AFAC no permite reconciliar país/ruta de la compañía. El mapa incluye además **cinco** salidas T-100 de servicio no regular `L`, excluidas del indicador para compararlo con `VLOSREG`.

Si el universo deseado es **Grupo Aeroméxico = Aerovías + Connect**, `VLOSREG` registra otros 8,747 vuelos regulares de Connect en abril–mayo (`E11:F11` y `E28:F28`). Las mismas 5,249 observaciones de Aerovías equivalen al **16.5%** de los 31,859 vuelos de ambas operadoras. Este cociente muestra el alcance actual respecto del grupo; no significa que se hayan identificado rutas de Connect.

La cifra de todo 2T26 no debe publicarse como cobertura comparable. BTS aún no tiene junio en el warehouse; CAA solo aporta junio. El mapa suma 5,721 registros de salida/movimiento durante las ventanas que muestra (incluidos los cinco `L`), pero dividirlo por los 33,677 vuelos regulares de Aerovías en abril–junio daría un cociente artificialmente bajo y mezclaría ventanas. Aena añade 936 operaciones de la compañía en MAD y BCN durante el trimestre, pero el CSV no prueba el extremo mexicano ni filtra el mismo universo de servicio regular; por ello tampoco se suma al indicador de rutas.

AFAC `VLOSREG` informa además 20,886 vuelos nacionales y 12,791 internacionales de Aerovías en abril–junio. Los nacionales representan **62.0%** del total de Aerovías y hoy no tienen representación por compañía y ruta en el mapa. Connect registra otros 11,308 nacionales y 1,731 internacionales: incluirlo cambiaría el universo; requiere fuentes y reconciliaciones propias.

## Rutas nacionales y mercados faltantes

El [AFAC Origen–Destino, julio 2026](https://www.gob.mx/cms/uploads/attachment/file/1100280/sase-julio-2026-27082026.xlsx) sí contiene `REG NAC` por pares de ciudades direccionales y mes. Para **MEXICO → MONTERREY**, abril–junio (`F282:H282` vuelos, `S282:U282` pasajeros) suma 2,680 vuelos y 414,835 pasajeros. Para **MONTERREY → MEXICO**, filas 323, suma 2,505 vuelos y 398,496 pasajeros. Ambos sentidos: **5,185 vuelos y 813,331 pasajeros de todo el mercado**. La hoja no tiene aerolínea ni identifica inequívocamente el aeropuerto cuando una ciudad tiene más de uno. No atribuir este total a Aeroméxico.

En `REG INT`, el mismo libro registra MEXICO↔TORONTO (628 vuelos y 84,190 pasajeros en abril–junio) y MEXICO↔TOKYO (363 vuelos y 65,256 pasajeros), sumando ambos sentidos. Son **mercados de todas las compañías** y el producto está rotulado origen–destino (OFOD); no se ha probado equivalencia con un segmento sin escala. Muestran actividad del mercado, pero no resuelven la cobertura por operador para Canadá o Japón.

La hoja `VLOSREG` del resumen AFAC distingue empresa, servicio nacional/internacional y mes, pero omite ciudades. Las dos tablas no tienen una clave compartida que permita distribuir los 5,185 vuelos MEXICO↔MONTERREY entre Aeroméxico, Connect, Viva, Volaris u otras compañías. La salida correcta para un primer incremento doméstico sería una capa **Mercado nacional · todas las aerolíneas**, visualmente separada de la red de Aeroméxico. Para medir Aeroméxico por ruta se necesita otra fuente que incluya compañía, ambos extremos, mes y vuelos; o una entrega oficial verificable de AFAC. Una programación de vuelos podría informar frecuencias ofertadas, pero no pasajeros transportados.

## Evidencia y límites

- [Resumen AFAC preservado](../../data/bronze/afac_research/afac_research_airline_summary_2026M07_20260908T182133Z.xlsx), SHA-256 `479df73d3565cfda19d7445e17233478acf89c75a098cc75ea6269b2e9214bba`.
- [Origen–Destino AFAC preservado](../../data/bronze/afac_research/afac_research_city_pairs_2026M07_20260908T182059Z.xlsx), SHA-256 `6f81b242fcb84ec04fa74236b7fd52b91c6e99b64eab7945d9eed299a86cf9fd`.
- [Definición BTS de clases F y L](https://www.transtats.bts.gov/gettingstarted.pdf): F es servicio programado de pasajeros/carga; L es servicio civil no programado.
- Las tablas actuales son una perspectiva retrospectiva descargada después del corte del Analysis Agent de 2T26. Ninguna de estas cifras entra automáticamente en el análisis histórico aprobado.

Para reproducir el indicador, consultar en DuckDB la suma de `departures_performed` de `fact_route_traffic` con `carrier_key='AEROMEXICO'`, `period_id IN ('2026M04','2026M05')` y `service_class='F'`; sumar `departures` de `fact_international_route_observations` con `operator_icao='AMX'`, `observation_scope='carrier_route'`, `source_system IN ('aerocivil','anac')` y los mismos meses. Contrastar con `VLOSREG!E10:F10` y `E27:F27`, sin incluir `Aerolitoral` ni filas de fletamento.
