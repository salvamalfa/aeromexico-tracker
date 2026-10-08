# Asientos y ocupación estimados de Vuelos internacional

Fecha: 25 de septiembre de 2026.
Estado: **generador de capacidad y vista de revisión de Vuelos integrados;
dashboard integrado no tocado**, pendiente de su propia autorización.

Detalle técnico vigente: documento canónico §9.14, que continúa la
integración de pasajeros descrita en §9.13 y
[`aerodatabox-internacional-integracion-vuelos-20260925.md`](aerodatabox-internacional-integracion-vuelos-20260925.md).

## Qué cambió

- Nuevo módulo `src/analytics/international_capacity.py`
  (`python -m src.analytics.international_capacity 2026M04,2026M05,2026M06,2026M07`)
  construye el Gold `fact_aeromexico_international_capacity_estimate`
  (ignorado en este repositorio): una fila por mes × origen × destino ×
  operador (Aerovías, Connect), con `departures_estimated`,
  `seats_estimated(_low/_high)`, `aircraft_model_coverage` y
  `capacity_usable`, sin conteo de modelo por ruta. Reutiliza
  `capture_from_sweep` y `add_foreign_through_support` de
  `international_route_carrier` en vez de duplicar el filtro de tramo, para
  que sus vuelos reconcilien con los de la tabla de pasajeros.
- `stage6_warehouse` la carga como extensión opcional; añadida a
  `.gitignore` junto a su hermano de pasajeros.
- `src/dashboard/international_routes.py`: `_estimated_routes` y la rama de
  enriquecimiento de `extend_networks` calculan asientos y ocupación por
  celda (mes × dirección), con la misma regla de completitud y de
  plausibilidad (ocupación fuera de 0–100 % oculta) que el estimador
  nacional. Una ruta con asientos propios (T-100, ANAC) nunca se sobrescribe.
- `flights.js` no cambió: ya interpretaba `seats`, `seats_low/high`,
  `load_factor(_low/high)` y `capacity_estimated` para nacional, y la
  Vuelos internacional los reutiliza sin tocar el generador de HTML/JS.

## Mezcla de modelos y cobertura

| Mes | Cobertura de modelo | Celdas utilizables | Vuelos candidatos |
|---|---:|---:|---:|
| 2026M04 | 99.98 % | 142/142 | 4,964 |
| 2026M05 | 99.98 % | 141/141 | 4,846 |
| 2026M06 | 99.98 % | 143/143 | 4,826 |
| 2026M07 | 100.00 % | 141/141 | 5,348 |

Único modelo sin mapear: `Beechcraft 350 Super King Air` bajo `AEROMEXICO`,
un vuelo por mes en abril–junio (peso 1.0), ausente en julio. Es un jet
privado fuera de la flota operativa del 20-F; se excluye como "King Air" en
el estimador nacional, sin inventarle asientos y sin agregar un alias nuevo.
Todo el resto de la mezcla observada (737-800, 737 MAX 8, 737 MAX 9,
737-900, 787-8, 787-9, 787-900, Embraer 190) ya tenía fila propia en
`aeromexico_aircraft_seat_capacity.csv`; no se necesitó ningún alias nuevo.

Un grupo de tramos con operador `AEROMEXICO` cae fuera del universo de
ciudades AFAC — sobre todo destinos australianos (SYD, MEB, AVV, PQQ, BNE,
TSV, ROK) con King Air o un 737 aislado — y se excluye tanto del candidato
como del mapa: es ruido del proveedor (Aeroméxico no vuela México–Sídney),
no una cobertura real que se esté perdiendo.

## Reconciliación con la tabla de pasajeros

La tabla de capacidad publica cada par de aeropuertos capturado
directamente; la tabla de pasajeros (`fact_route_carrier_international_estimate`)
colapsa una ruta-ciudad AFAC a su par de aeropuertos dominante. En abril,
sobre 142 celdas de Aerovías/Connect, 140 reconciliaron exactamente al vuelo
y 2 (México–San Diego, ambos sentidos, 32 vuelos) no tuvieron contraparte en
Gold porque AFAC no publicó pasajeros para esa ruta ese mes. Es la diferencia
esperada de grano entre las dos tablas, no un error de captura.

## Resultado en 2T26 (abril–junio), rutas de muestra

| Ruta | Mes | Pasajeros | Asientos | Ocupación |
|---|---|---:|---:|---:|
| MEX–MAD | abr | 38,370 | 47,382 | 81.0 % |
| MEX–MAD | may | 38,927 | 49,843 | 78.1 % |
| MEX–MAD | jun | 38,092 | 46,710 | 81.5 % |
| MEX–BOG | abr | 24,363 | 31,023 | 78.5 % |
| MEX–BOG | may | 25,131 | 31,790 | 79.1 % |
| MEX–BOG | jun | 25,035 | 31,618 | 79.2 % |
| MEX–LIM | abr–jun | 11,155 / 11,837 / 11,006 | 9,850 / 9,753 / 9,427 | N/D (113–121 %, ocupación implausible) |
| GDL–MAD (ruta nueva) | abr | 12,848 | 13,452 | 95.5 % |
| GDL–MAD (ruta nueva) | jun | 11,912 | 12,992 | 91.7 % |

MEX–LIM queda como ejemplo del control de plausibilidad ya existente:
cobertura de modelo perfecta, pero el ajuste de pasajeros supera los
asientos estimados, así que la ocupación se oculta (`inconsistent_inputs`)
en vez de mostrarse por encima de 100 %, igual que hace el estimador
nacional.

## Verificación

- `uv run python -m pytest tests/test_international_capacity.py
  tests/test_international_routes.py tests/test_international_route_carrier.py
  tests/test_international_gold.py` — 50 aprobadas.
- Reconstrucción completa del warehouse local
  (`build_warehouse(max_stage=9)`, Gold públicos + las tablas privadas del
  repositorio de datos) y regeneración de `prototypes/vuelos/vuelos_revision.html`
  vía `python -m src.dashboard.build_flights`.
- `git status` tras la reconstrucción no modificó `models/*.json`.

## Pendiente

- Publicar al dashboard integrado sigue requiriendo su propia autorización
  explícita, como en §9.13.
- La tabla de capacidad no distingue los tramos con vía técnica (México–Madrid
  vía Monterrey, México–Seúl/Tokio vía Monterrey): el origen y destino
  publicados por el tablero ya son los del mercado completo, así que no hace
  falta partir el tramo; se deja anotado por si una futura fuente reporta el
  tramo técnico por separado.
