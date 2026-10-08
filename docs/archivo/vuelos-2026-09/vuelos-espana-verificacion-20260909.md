# España: verificación autenticada de Aena

Fecha de inspección: 9 de septiembre de 2026. Se utilizó la sesión iniciada por el usuario en Chrome y navegación ordinaria. Este documento complementa el diagnóstico de acceso anterior; el inicio de sesión ya está resuelto.

## Resultado

Aena sí presenta exportación: en el informe detallado por compañía, el menú «Opciones de visualización» ofrece «Mostrar datos» y «Exportar», con opciones «PDF» y «Datos». Se comprobó el menú; no se completó una descarga. La limitación observada para este incremento es la separación de compañía y origen–destino en los conjuntos ofrecidos.

En https://www.aena.es/es/estadisticas/consultas-personalizadas.html se ejecutaron las cuatro consultas para 2026 y se inspeccionó el panel visible «Conjuntos de datos»:

| Consulta | Dimensiones relevantes visibles | Métricas visibles | Brecha para rutas de Aeroméxico |
|---|---|---|---|
| Operaciones por compañía | Aeropuerto Base, Año, Compañía, Grupo Compañía, Mes, Movimiento, País, Clase, Servicio, Tipo Avión, Tipo Tráfico | Operaciones Totales | Sin aeropuerto del otro extremo |
| Operaciones O/D | Aeropuerto Base, Aeropuerto ORI/DES, Año, Mes, Movimiento, País, Clase, Servicio, Tipo Avión, Tipo Tráfico | Operaciones Totales | Sin compañía |
| Pasajeros/Mercancías por compañía | Aeropuerto Base, Año, Compañía, Grupo Compañía, Mes, Movimiento, País, Clase, Servicio, Tipo Avión, Tipo Tráfico | Pasajeros, Pasajeros Totales, Tránsitos, Mercancías, Mercancías Totales, Mercancías Tránsito, Kg Correo | Sin aeropuerto del otro extremo |
| Pasajeros/Mercancías Escala | Aeropuerto Base, Aeropuerto Escala, Año, Mes, Movimiento, País, Clase, Servicio, Tipo Avión, Tipo Tráfico | Pasajeros, Pasajeros Totales, Tránsitos, Mercancías, Mercancías Totales, Mercancías Tránsito, Kg Correo | Sin compañía |

La vista detallada «Información de rutas por aeropuertos» también presenta aeropuerto base, año, mes, país y movimiento, sin selector de compañía observado. Los resultados iniciales son agregados de mercado y no se incorporan como tráfico de Aeroméxico. La dimensión País no se reinterpretó como aeropuerto contraparte.

## Decisión del incremento

No se obtuvo una tabla conjunta compañía + ambos aeropuertos + mes. España permanece pendiente para el mapa de rutas por operador. Esto describe las consultas inspeccionadas; no demuestra que Aena carezca de otro producto con ese desglose. Una solicitud específica a Aena podría resolverlo, pero no se envió ningún mensaje externo.

Se aplica la alternativa autorizada por el usuario: conservar y verificar la integración local disponible de Brasil, Colombia y Reino Unido. Esas fuentes ya recorrieron Bronze → Silver → Gold → HTML. En este turno no se agregaron observaciones españolas ni nuevas rutas de otros países. Las 18 pruebas de integración internacional, prototipo Vuelos y publicación Stage 18 pasaron (22.58 s). La documentación del incremento y sus ventanas está en `vuelos-integracion-internacional-20260908.md`.

Para 2T26 se mantienen seis mercados adicionales a BTS: MEX–GRU, MEX–BOG, MEX–MDE, MEX–CTG, MEX–CLO y MEX–LHR. CAA cubre junio solamente; las otras cinco rutas cubren abril–junio. Se conserva la exclusión de estas versiones del análisis histórico al corte del 13 de julio de 2026.

## Próximo incremento útil

Completar abril y mayo de CAA y verificar exportaciones por operador y ruta de las siguientes autoridades. Para España, obtener un extracto que incluya explícitamente la compañía y el aeropuerto contraparte; los agregados separados pueden servir como contexto de mercado, pero no permiten repartir pasajeros entre rutas de Aeroméxico.
