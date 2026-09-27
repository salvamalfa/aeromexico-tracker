# Propuesta visual: mapa de Vuelos para lectura ejecutiva

Fecha: 2026-09-27. Estado: **vista previa para comentarios del dueño**.

## Alcance

Se conservan las tarjetas de Vuelos, el selector de meses existente y el
gráfico inferior. Solo cambia el módulo del mapa y su panel derecho.

- El mapa abre con las 12 rutas de mayor volumen de pasajeros disponible en el
  ámbito seleccionado. El control «Todas las rutas» devuelve el universo
  cuantificado, sin convertir rutas con presencia sin volumen en ceros.
- El panel derecho abre con el ranking de la red, no con las rutas de MEX.
  Seleccionar un aeropuerto filtra las rutas visibles y «Toda la red» restaura
  el ranking. Cada ruta muestra total trimestral de pasajeros, vuelos y
  ocupación cuando existen; se eliminó el desglose mensual y por sentido de
  este panel. Los asientos dejan de aparecer en él.
- Las variaciones interanuales de pasajeros solo se muestran cuando la ruta
  conserva un periodo anterior comparable. Las marcas de cobertura, el estado
  observado/estimado/programado y las fuentes permanecen disponibles.
- El total de la red queda separado del ranking y los detalles de método se
  consultan al desplegar «Alcance y método».

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
