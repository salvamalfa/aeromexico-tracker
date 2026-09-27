# Propuesta visual: mapa de Vuelos para lectura ejecutiva

Fecha: 2026-09-27. Estado: **vista previa para comentarios del dueño**.

## Alcance

Se conservan las tarjetas de Vuelos y el gráfico inferior. El mapa toma todos
los meses disponibles del trimestre global, sin selector mensual propio. Si
faltan meses, el total nacional muestra la fracción cubierta (p. ej. 1/3).

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
  sentido. El total de la red se expresa en una línea con el trimestre.
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
El total SEC de pasajeros del trimestre y la suma de rutas tienen alcances
distintos y no se presentan como una reconciliación exacta.

## Presentación y decisión pendiente

La rama `preview/flights-executive-map` se puede servir localmente desde
`web/` con los datos públicos ya incluidos en `web/public/data/v1/`. La versión
se muestra en el navegador de Codex antes de cualquier PR, merge o despliegue
en Pages. El siguiente paso depende de los comentarios del dueño sobre el
número de rutas destacadas, el contenido del panel y la relevancia de los
movimientos interanuales.
