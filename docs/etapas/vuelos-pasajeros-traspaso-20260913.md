# Vuelos: guía de entrada

Versión candidata al 14 de octubre de 2026; publicación pendiente de aprobación. Reemplaza el traspaso del 13 de septiembre de
2026, que describía la app retirada; conserva la ruta del archivo porque
`AGENTS.md`, `REPO_MAP.md` y comentarios de `web/src/views/flights/` la citan.

## Dónde vive la vista

- **Interfaz:** [`web/src/views/flights/`](../../web/src/views/flights/)
  (Vite + TypeScript), única implementación publicada. Arranque en
  `bootstrap.ts`; estado y carga diferida de archivos por periodo en
  `state.ts`; mapa en `map.ts`; red y alcance en `network.ts`; tabla de rutas
  en `table.ts`; selector de aerolínea en `carriers.ts` y
  [`web/src/views/shell/carriers.ts`](../../web/src/views/shell/carriers.ts).
- **Contrato de datos:**
  [`contracts/web/flights.schema.json`](../../contracts/web/flights.schema.json).
- **Payload:** [`src/dashboard/flights.py`](../../src/dashboard/flights.py)
  (`build_flight_payload`),
  [`domestic_routes.py`](../../src/dashboard/domestic_routes.py),
  [`international_routes.py`](../../src/dashboard/international_routes.py) y,
  para Industria/Volaris/Viva,
  [`entity_routes.py`](../../src/dashboard/entity_routes.py),
  [`route_entities.py`](../../src/dashboard/route_entities.py) y
  [`route_capacity.py`](../../src/dashboard/route_capacity.py).
- **Lista blanca:**
  [`flights_html.py::integration_flight_payload`](../../src/dashboard/flights_html.py).
  Un campo que no esté ahí se descarta sin error.
- **Exportación y publicación:**
  [`src/web_export/flights.py`](../../src/web_export/flights.py) escribe
  `flights/quarters.json` y un archivo por periodo (`domestic/`,
  `international/`, `entities/<KEY>/`); [`src/publish/`](../../src/publish/)
  ensambla y firma `site/`. Ver [`REPO_MAP.md`](../../REPO_MAP.md) y
  [`AGENTS.md`](../../AGENTS.md).

## Qué muestra hoy

- **Tarjetas** (pasajeros, ASM, RPM, ocupación) con selector de una
  aerolínea: Industria, Aeroméxico, Volaris o Viva. Aeroméxico usa la serie
  trimestral SEC; las demás, su reporte trimestral (RPM en N/D donde no se
  publica).
- **Mezcla nacional/internacional** por trimestre o mes, con selector de
  varias aerolíneas: Aeroméxico sola usa la serie mensual AFAC Gold; cualquier
  otra selección usa AFAC por aerolínea.
- **Red de vuelos:** mapa y tabla «Rutas destacadas / Mayores cambios / Todas»
  con pasajeros, vuelos y ocupación por ruta; Nacional o Internacional;
  regiones internacionales; búsqueda de aeropuerto; selector de aerolínea
  (default Industria, que suma las tres y muestra el reparto por ruta).
- **Nacional:** programación oficial AICM de Aeroméxico donde existe, identificada
  como programada. No hay vuelos realizados ni pasajeros/asientos/ocupación
  por ruta disponibles. Volaris, Viva e Industria muestran ese faltante; sus
  pasajeros agregados AFAC y tarjetas reportadas permanecen.
- **Internacional:** México–EE. UU. observado por BTS T-100; Aeroméxico agrega
  observaciones ANAC/Aerocivil/CAA y actividad Aena en su grano de aeropuerto.
  Slots AICM/anuncios OMA son programación y no se suman como vuelos realizados.
  En 2T26, BTS local conserva abril–mayo y falta junio.
- **Asientos y ocupación:** solo medidas oficiales compatibles, como BTS.
  No se enriquecen fuentes con IPF ni frecuencias de AeroDataBox.
- Rutas solo con presencia, sin volumen atribuible, no se dibujan; la vista
  dice cuántas quedaron fuera.

## Reglas de significado que más pesan aquí

- Las estimaciones históricas IPF quedan fuera de la vista activa y del chat.
  Su metodología y linaje privado se conservan.
- Observado, programado y estimado no se suman. Slots AICM y anuncios OMA son
  programación (`operation_status`), no vuelos realizados.
- Operador ≠ comercializador/codeshare. Aerovías y Connect se ajustan por
  separado y se suman como Grupo Aeroméxico; en internacional la evidencia
  observada es solo de Aerovías.
- T-100 cubre operaciones del reportante entre México y EE. UU.; no la red
  mundial, codeshares ni ingresos.
- Faltante es N/D, nunca cero.
- `flight_evidence_v1` es candidato no aprobado. `python -m
  src.dashboard.build_flights` lo regenera como candidato; no lo actives ni
  hagas backfill.

El método canónico está en
[`docs/estimacion-pasajeros-ruta-aerolinea.md`](../estimacion-pasajeros-ruta-aerolinea.md);
léelo antes de tocar el estimador y no lo reconstruyas desde reportes sueltos.

## Cambios típicos

- UI o columna nueva: recetas (a) y (b) de
  [`REPO_MAP.md` § Recetas](../../REPO_MAP.md#recetas).
- Mes nuevo: obtener la edición oficial por la ronda documentada en
  [catálogo y calendario](../catalogo-fuentes-calendario.md), preservando grano,
  meses, linaje y comparación. Exportar no requiere los cuatro Gold privados
  de estimaciones; `config/web_inputs.yaml` exige las tablas oficiales BTS y
  aeropuertos. No llamar a AeroDataBox.
- Pruebas focalizadas (marcadas `local_data`: necesitan warehouse local):
  `tests/test_flights_prototype.py`, `tests/test_international_routes.py`,
  `tests/test_aicm_international_slots.py`, `tests/test_route_entities.py`,
  `tests/test_flights_national_quarter_selection.py`. Sin datos locales
  corren `tests/test_route_carrier_ipf.py` y `tests/test_fleet_capacity.py`.
  En `web/`: `npm run check && npm run test`.

## Reportes vigentes relacionados

- [`vuelos-capacidad-ocupacion-estimada-20260920.md`](vuelos-capacidad-ocupacion-estimada-20260920.md):
  asientos y ocupación nacionales.
- [`correcciones-codex-estimaciones-20260927.md`](correcciones-codex-estimaciones-20260927.md):
  correcciones a bandas de ocupación y Gold de rutas.
- Dashboard v2: [fase 0](dashboard-v2-fase0-datos-20260928.md) (datos de
  Volaris y Viva), [fase 2](dashboard-v2-fase2-web-20260930.md) (selectores),
  [fase 3](dashboard-v2-fase3-mapa-20260930.md) (mapa por aerolínea),
  [fase 4](dashboard-v2-fase4-capacidad-20260930.md) (capacidad por promedio
  de flota).

## Límites y pendientes

- Internacional fuera de EE. UU. sigue parcial: hay evidencia en Brasil
  (ANAC), Colombia (Aerocivil), Reino Unido (CAA) y Perú (DGAC); España sigue
  bloqueada por falta de cruce compañía + ambos aeropuertos + mes en Aena
  ([`ROADMAP.md`](../../ROADMAP.md)).
- Auditoría de exclusividad de operador en mercados nacionales candidatos
  (p. ej. MEX–CPE, MEX–MAM) antes de tratar un total AFAC como pasajeros de
  Aeroméxico.
- El error medido del estimador viene de un mercado transfronterizo corto y no
  garantiza Europa, Asia o Latinoamérica; el rango `low/high` es sensibilidad,
  no incertidumbre estadística (§12 del método canónico).
- Activar datos en el dashboard no cambia la elegibilidad histórica al
  2026-07-13 ni el Analysis Agent.

## Historia

Los reportes de investigación e integración de septiembre de 2026 (AFAC,
AeroDataBox, Aena, AICM, ANAC/Aerocivil/CAA y pilotos de pasajeros) se
consolidaron; su contenido duradero vive en
[`docs/estimacion-pasajeros-ruta-aerolinea.md`](../estimacion-pasajeros-ruta-aerolinea.md).
Los originales se consultan en
[`docs/archivo/vuelos-2026-09` en `7478082`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/vuelos-2026-09).
