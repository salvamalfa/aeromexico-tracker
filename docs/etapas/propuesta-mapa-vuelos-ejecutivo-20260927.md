# Propuesta visual: mapa de Vuelos para lectura ejecutiva

Fecha: 2026-09-27. Estado: **vista previa para comentarios del dueño**.

## Alcance

Se conservan las tarjetas de Vuelos y el gráfico inferior. El mapa toma todos
los meses disponibles del trimestre global, sin selector mensual propio.

- El mapa abre con las 12 rutas de mayor volumen de pasajeros disponible en el
  ámbito seleccionado. «Todas las rutas» devuelve el universo cuantificado,
  sin convertir rutas con presencia sin volumen en ceros.
- «Mayores cambios» muestra hasta seis aumentos y seis caídas porcentuales
  interanuales de rutas internacionales observadas. Compara los mismos meses
  disponibles con el año anterior y exige al menos 5 mil pasajeros en alguno
  de los dos periodos para evitar porcentajes dominados por bases diminutas.
  No se presenta como cambio frente al trimestre inmediato anterior. La opción
  se desactiva en nacional: de 1T26 solo está marzo y no existe una base
  trimestral comparable con abril–junio.
- El panel derecho abre con el ranking de la red, no con las rutas de MEX.
  Seleccionar un aeropuerto filtra las rutas visibles y «Toda la red» restaura
  el ranking. La ruta queda a la izquierda y pasajeros, vuelos y ocupación
  aparecen en tres columnas. No se muestran asientos, desglose mensual ni por
  sentido. Las rutas se nombran por ciudad; el código IATA queda en el título
  de consulta. Encima del ranking hay tres indicadores compactos por trimestre:
  pasajeros, vuelos y ocupación.
- Las variaciones interanuales aparecen solo en la vista de cambios. Las
  marcas de cobertura y las fuentes permanecen disponibles. En internacional,
  los pasajeros estimados por ruta llevan una marca discreta para distinguirlos
  de los observados.

## Límites de interpretación

La selección por volumen es una propuesta de lectura, no una clasificación de
rentabilidad ni de oportunidad para la tarjeta. En nacional, los pasajeros por
ruta son estimaciones AFAC + AeroDataBox. En internacional coexisten operaciones
observadas de Aerovías y estimaciones de Grupo Aeroméxico, con meses de
cobertura distintos; los vuelos programados no se suman a los operados.
El indicador compacto de pasajeros usa la misma serie AFAC Gold nacional o
internacional que el gráfico inferior, por lo que ambos coinciden. Vuelos suma
las rutas con dato estimado en nacional y solo vuelos observados de Aerovías
en internacional. Ocupación divide pasajeros entre asientos únicamente en
rutas con ambos datos compatibles; no es la ocupación de la red completa.
La selección regional y las rutas resaltadas afectan mapa y ranking, no esos
indicadores de la red completa. En 2T26, AFAC registra 3,856,840 pasajeros
nacionales y 2,060,171 internacionales. La suma nacional por ruta estimada es
3,831,997 (0.6% menos que AFAC); la suma internacional con dato por ruta es
653,731 (68.3% menos). La diferencia internacional es de cobertura y fuente,
no un error que se pueda ajustar legítimamente a 5–10%. El total SEC de
pasajeros del trimestre también tiene un alcance diferente.

## Presentación y decisión pendiente

La rama `preview/flights-executive-map` se puede servir localmente desde
`web/` con los datos públicos ya incluidos en `web/public/data/v1/`. La versión
se muestra en el navegador de Codex antes de cualquier PR, merge o despliegue
en Pages. El siguiente paso depende de los comentarios del dueño sobre el
número de rutas destacadas, el contenido del panel y la relevancia de los
movimientos interanuales.
