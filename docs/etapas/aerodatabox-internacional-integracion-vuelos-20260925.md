# Integración de la estimación internacional a Vuelos

Fecha: 25 de septiembre de 2026.
Autorización: el operador aprobó revisar y continuar con todos los pasos
("Adelante con todo") tras el resumen de siguientes pasos.
Estado: **generador y vista de revisión de Vuelos integrados; dashboard
integrado publicado sin tocar**, pendiente de su propia autorización.

Detalle técnico vigente: documento canónico §9.13.

## Qué cambió

- `src/analytics/international_gold.py` construye la tabla Gold
  `fact_route_carrier_international_estimate` desde los ajustes mensuales,
  en llave de aeropuertos (`MAD<>MEX`), con rango de ±16 % medido contra
  T-100.
- `stage6_warehouse` la carga como extensión opcional;
  `international_routes.extend_networks` la aplica con precedencia: lo
  observado nunca se sobrescribe, Estados Unidos queda para T-100, y un
  mercado con vuelos sin pasajeros recibe pasajeros solo para los meses que
  su fuente cubre.
- `flights.js`: las rutas estimadas se muestran aunque no tengan vuelos
  observados; sus vuelos de AeroDataBox no entran al conteo de vuelos
  operados de Aerovías; línea aparte con los pasajeros estimados; Santiago
  (SCL) en Sudamérica.
- Regla revisada de escala extranjera para Emirates (DXB–BCN–MEX).

## Resultado en 2T26

34 rutas internacionales con pasajeros estimados (912,954): 30 que mostraban
`N/D` y 4 nuevas (GDL–MAD, MTY–ICN, MTY–NRT, MEX–SCL).

## Verificación

- Antes de cambiar nada se reprodujo el HTML publicado de Vuelos byte a byte
  desde el warehouse reconstruido en la nube (Gold público + las dos tablas
  nacionales del repositorio privado).
- Pruebas de Vuelos (prototipo, interacciones con Playwright, fuentes
  internacionales, AICM) aprobadas; dos pruebas se actualizaron porque
  fijaban `N/D` en rutas que ahora tienen estimación, y ganaron aserciones de
  precedencia (observado intacto, sin Estados Unidos, meses propios de CAA).
- Revisión visual en Chromium: sin errores de consola.

## Pendiente

- Publicar al dashboard integrado: requiere autorización explícita de
  publicación y, para la ruta normal, resolver la falla conocida de
  `evidence.validate` del Analysis Agent (no relacionada con Vuelos).
- SKY Airline Perú y Orbest siguen sin resolver: no aparecen con ningún
  código en las cuatro capturas, así que no hay evidencia para mapearlas.
