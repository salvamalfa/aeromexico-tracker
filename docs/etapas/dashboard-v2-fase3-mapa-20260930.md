# Dashboard v2 · Fase 3: mapa de rutas por aerolínea

Fecha: 30 de septiembre de 2026. Rama `claude/aerolineas-tracker-redesign-zqk94j`
(PR #77).

## Decisión del dueño (30 sep 2026)

- **Qué muestra el mapa de Vuelos** para Industria, Aeroméxico, Volaris y Viva:
  - rutas nacionales estimadas;
  - México–EE. UU. con BTS T-100 observado;
  - el resto del internacional con estimaciones.
- **Default:** Industria.
- **Qué autoriza:** publicar la estimación internacional de pasajeros por ruta
  (AFAC + AeroDataBox, IPF). Hasta hoy seguía pendiente; aplica a las tres aerolíneas,
  incluida Aeroméxico. Siempre se muestra como “estimado” y conserva su rango de
  sensibilidad.
- **Qué no autoriza:** activar `flight_evidence_v1`, cambiar aprobaciones del Analysis
  Agent ni consumir APIs.

## Qué cambió en pantalla

| Lugar | Cambio |
|---|---|
| Vuelos · Red de vuelos | Selector “Aerolínea” (una) junto a Nacional / Internacional, con el mismo estilo del resto. Default Industria. |
| Mapa y “Rutas destacadas” | Mismo mapa, mismas líneas y mismo panel, filtrados a la entidad elegida. Con Industria, cada ruta suma las tres y la tabla muestra el reparto (p. ej. “Volaris 52% · Viva 31% · Aeroméxico 17%”). |
| Nota de alcance | Dice qué fuente cubre cada tramo. Con Viva en internacional añade la nota de mayor incertidumbre (~15 % de error medido contra T-100). |
| Línea de volumen | Para Industria, Volaris y Viva usa los pasajeros AFAC de la entidad (`market.json`). |
| Grupo Aeroméxico | Idéntico a la v1: conserva sus capas propias (slots AICM, mercados exclusivos AIFA, OMA, ANAC/Aerocivil/CAA/Aena) y la capacidad de asientos. |
| Volaris, Viva, Industria | Asientos y ocupación por ruta “N/D” hasta la fase 4. Sin capas propias de Aeroméxico. |

## Fuentes y precedencia

- **Nacional:** `fact_route_carrier_domestic_estimate` filtrado a las claves de la
  entidad (Aerovías y Connect siguen separados en el estimador y se suman solo en la
  vista de grupo).
- **México–EE. UU.:** `fact_route_traffic_summary` de los reportantes T-100 de la
  entidad. Connect no reporta aparte a BTS.
- **Resto del internacional:** `fact_route_carrier_international_estimate`. Un mercado
  con T-100 nunca se sobrescribe con la estimación, igual que en Grupo Aeroméxico.
- **Industria:** cada ruta es la suma de las tres. `carrier_breakdown` conserva los
  pasajeros por aerolínea, y la prueba local comprueba que el desglose suma el total de
  la ruta.
- **Error medido del estimador:**
  - Internacional contra T-100: Volaris 4.3 %, Aeroméxico 6–7 %, Viva ~15 %.
  - Nacional (backtest): ~2 pp para las tres.

## Código

- **Entidades:** `src/dashboard/route_entities.py` define qué claves cubre cada
  entidad, sus etiquetas, capas, capacidad y desglose.
- **Constructores por entidad:** `src/dashboard/entity_routes.py` construye el mapa
  internacional (T-100 + estimación), el desglose T-100 y el mensual nacional de cada
  entidad.
- **Módulos existentes:** `flights.py`, `domestic_routes.py` e
  `international_routes.py` reciben la entidad como parámetro; el default
  `AEROMEXICO_ROUTES` deja la salida de Grupo Aeroméxico igual. El crecimiento de
  `flights.py` (+7) y de `international_routes.py` (+6) queda registrado en la
  ALLOWLIST de `tests/test_repo_budgets.py`.
- **Export:**
  - `src/web_export/flights.py` escribe
    `flights/entities/<KEY>/{domestic,international}/<periodo>.json` y los lista en
    `quarters.json → available_periods.entities`.
  - Tamaño: ~11 MB en total (Industria 5 MB, Volaris 3 MB, Viva 2.4 MB). Se descarga un
    periodo a la vez; el archivo más grande pesa 430 KB.
- **Contratos:**
  - `flights.schema.json` agrega `entity_networks` y el `carrier_breakdown` de cada ruta,
    y amplía el enum `carrier_key`.
  - `privacy.yaml` agrega `VOLARIS`, `VIVA_AEROBUS` e `INDUSTRY` a
    `allowed_estimated_carriers`.
- **Web:**
  - `web/src/views/flights/state.ts`: entidad del mapa, rutas de datos y caché por
    entidad, y descarte de respuestas de una entidad anterior.
  - `bootstrap.ts`: el selector.
  - `network.ts`: nota de alcance.
  - `table.ts`: reparto por aerolínea.
  - `domestic.ts`: suma el desglose de los meses elegidos.
  - `volume.ts`: pasajeros AFAC por entidad.

## Validación

- **Python (CI):** `uv run pytest -m "not local_data and not browser" -q` con 550
  pruebas.
  - Excluye `test_unmodified_copy_passes`, que falla porque `site/` sigue firmado contra
    los contratos anteriores.
- **Python (datos locales):** `tests/test_route_entities.py`:
  - las entidades no traen capas de Aeroméxico;
  - el desglose de Industria suma el total de cada ruta.
- **Web:** `npm run check` y `npm run test`.
- **Navegador:** `pytest -m browser`.
- **Regeneración:** `python -m src.dashboard.build_flights` y
  `python -m src.web_export --out web/public/data/v1 --allow-missing-analysis`. Mover el
  código a `entity_routes.py` dejó el export idéntico byte a byte.
- **Revisión visual:** capturas con Playwright del build real (`npm run build && vite
  preview`):
  - Industria nacional e internacional;
  - Volaris internacional;
  - Viva nacional e internacional;
  - Aeroméxico internacional.

  No hubo errores de consola.

## Pendiente

- **Re-firmar `site/`** con el gate sobre el warehouse completo, ya que la estimación
  internacional está autorizada. La herramienta lo bloquea como despliegue: hace falta
  permiso en la sesión o que el dueño lo ejecute.
- **Fase 4:** asientos y ocupación por ruta de Volaris y Viva.
- **Fase 5:** tesis de la industria y por aerolínea, con aprobación del dueño.
