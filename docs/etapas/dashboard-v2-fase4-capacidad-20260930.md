# Dashboard v2 · Fase 4: asientos y ocupación por ruta de Volaris y Viva

Fecha: 30 de septiembre de 2026. Rama `claude/aerolineas-tracker-redesign-zqk94j`
(PR #77).

## Decisión del dueño

**Método: promedio de flota.**

- **Por qué no el método de Aeroméxico:** Aeroméxico asigna los asientos por el modelo de
  avión de cada vuelo capturado. Para Volaris y Viva ese dato no se conservó, porque las
  capturas del proveedor eran temporales; solo quedaron los vuelos mensuales por ruta.
- **Qué autorizó el dueño:** la opción “promedio de flota”, que no consume ninguna API.
  El error de la ocupación estimada contra la observada se mide antes de publicar.
- **Cómo se publica:** asientos y ocupación siempre como “estimado”, con rango.

## Método

Canónico: `docs/estimacion-pasajeros-ruta-aerolinea.md` §9.15.

- **Asientos:** vuelos × asientos por salida.
  - Los asientos por salida son los del T-100 de cada aerolínea en los 12 meses
    anteriores al periodo. El periodo mismo nunca entra, así que la prueba de abajo es
    fuera de muestra.
  - Volaris: 196; Viva: 200–203.
- **Rango:** p10–p90 del tamaño de avión en rutas con ≥ 50 salidas.
  - Volaris: 182–214; Viva: 186–224.
- **Vuelos:**
  - En nacional son el peso de la semilla AeroDataBox, que coincide con los vuelos
    capturados en el mes. Si la ruta no se observó en el mes, la semilla es prestada de
    otro mes; esa celda queda sin capacidad y su ocupación en N/D.
  - En internacional son `departures_estimated`.
- **Industria:** usa el método por modelo para Aeroméxico y el promedio de flota para
  Volaris y Viva.
  - Si una celda de Aeroméxico tiene pasajeros pero no capacidad, bloquea la ocupación de
    esa ruta en vez de sumar cero asientos.
- **Reglas que no cambian:** completitud por mes y sentido; ocupación por encima de 100 %
  → `N/D (inconsistent_inputs)`.

## Validación del error (T-100, rutas México–EE. UU., abr–may 2026)

| Aerolínea | Mes | Rutas | Error en vuelos | Error en asientos | Ocupación observada | Ocupación estimada | Error por ruta (ponderado) | Error por ruta (mediana) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Volaris | abr | 66 | 2.8 % | 8.6 % | 73.9 % | 77.1 % | 8.4 pp | 4.6 pp |
| Volaris | may | 62 | 1.9 % | 8.8 % | 78.8 % | 83.8 % | 9.2 pp | 5.2 pp |
| Viva | abr | 29 | 5.2 % | 10.2 % | 69.5 % | 67.6 % | 8.5 pp | 6.9 pp |
| Viva | may | 26 | 6.8 % | 12.2 % | 76.6 % | 72.3 % | 10.5 pp | 8.2 pp |

- **De dónde viene el error por ruta:**
  - Solo del tamaño de avión: 6–8 pp.
  - Solo de los pasajeros estimados: 5–10 pp.
- **Contraste con lo reportado (2T26):**
  - Volaris: nacional estimada 84.5 %, reportada total 84.8 %.
  - Viva: nacional estimada 86.0 %, reportada total 85.9 %.
- **Dispersión:** es similar a la del método por modelo de Aeroméxico. Entre 6 % y 25 %
  de las rutas quedan en N/D por pasar de 100 % en algún mes; Aeroméxico oculta ~20 %.

## Qué cambió en pantalla

- **Mapa de Volaris, Viva e Industria:**
  - Columnas de vuelos y ocupación por ruta.
  - Tarjeta de ocupación de la red.
- **Nota de alcance:** “asientos por promedio de flota (ocupación por ruta ±9 pp)”.
- **Grupo Aeroméxico:** sin cambios; sus archivos exportados son idénticos byte a byte.

## Código

- **Nuevos:**
  - `src/analytics/fleet_capacity.py`: tamaño de avión por aerolínea y capacidad por
    celda.
  - `src/dashboard/route_capacity.py`: capacidad por entidad.
- **Cambios:**
  - `route_entities.py`: `fleet_capacity_carriers`.
  - `domestic_routes.py` y `entity_routes.py` usan el nuevo cargador.
  - `web/src/views/flights/network.ts`: nota de alcance.
- **Pruebas:**
  - `tests/test_fleet_capacity.py`: periodo excluido del tamaño de avión, semilla
    prestada sin capacidad, solo Volaris y Viva, y bloqueo de Industria.
  - `tests/test_route_entities.py` (datos locales): ocupación dentro de (0, 1] y asientos
    dentro de su rango.

## Límites

- **Rutas densas:** en las que operan aviones más grandes que el promedio (A321), como
  GDL–TIJ, MEX–TIJ o CUN–MEX, los asientos quedan cortos y algún mes pasa de 100 %. La
  ocupación de esas rutas queda en N/D.
- **Tamaño de avión nacional:** se toma del T-100 (rutas a EE. UU.), porque no hay fuente
  pública del tamaño de avión nacional por ruta.
- **Mejora posible:** una nueva captura con modelo de avión mejoraría el método, pero
  consume API pagada y requiere autorización específica.
