# Dashboard v2 · Fase 2: selector de aerolíneas sobre la interfaz actual

Fecha: 30 de septiembre de 2026. Rama `claude/aerolineas-tracker-redesign-zqk94j`
(PR #77).

**Decisión del dueño:** conservar el dashboard actual y cambiar la información, no la
interfaz. La maqueta de la fase 1 (`prototypes/dashboard-v2/`, `src/dashboard/v2_mockup.py`)
se retiró.

## Qué cambió en pantalla

| Lugar | Cambio |
|---|---|
| Encabezado | Título “Aerolíneas MX Tracker” y una línea con la definición de Industria y su cobertura AFAC (99 % de los pasajeros de aerolíneas mexicanas en 2T26). |
| Lectura ejecutiva | Selector de aerolínea (una). Aeroméxico muestra el análisis aprobado, como antes; Industria, Volaris y Viva muestran el aviso de análisis pendiente. Default: Aeroméxico. |
| Lectura ejecutiva | Una tarjeta nueva con el mismo estilo: “Participación de pasajeros (AFAC)”. Una línea por aerolínea, segmento total/nacional/internacional y trimestre analizado sombreado. |
| Economía · tarjetas | Selector (una; default Industria). Con una aerolínea aparece un tercer chip, “vs. industria”: diferencia en ¢ o pp, y participación en el caso de ASK. La tabla por trimestre sigue a la misma entidad. |
| Economía · RASK vs. CASK | Selector (varias; default Industria). Con una entidad, la gráfica es la de siempre. Con varias, aparece el selector “Métrica” (RASK, CASK, CASK ex-fuel, Margen) y se dibuja una línea por aerolínea, con Industria punteada. |
| Economía · Precio vs. volumen | Con Industria, barras apiladas por aerolínea más el RASK de la industria; con varias, barras agrupadas; con una aerolínea, como antes. |
| Economía · Ocupación vs. RASK | Con una entidad, como antes (color por año); con varias, color por aerolínea y el trimestre analizado marcado. |
| Vuelos · tarjetas | Selector (una; default Industria). Aeroméxico usa la serie SEC de siempre; las demás usan su reporte trimestral. El RPM es N/D donde no se publica. |
| Vuelos · mezcla | Selector (varias; default Industria). Aeroméxico solo usa la serie de siempre; lo demás usa AFAC por aerolínea, con barras agrupadas y la parte internacional apilada sobre la nacional. |
| Vuelos · mapa | Sin cambio: sigue siendo la red de Grupo Aeroméxico hasta la fase 3. |

- **Selección compartible:** cada selección se guarda en la URL (`?sel_<card>=…`).
- **Selector:** usa el mismo estilo del `<select>` “Periodo”.
- **Colores:**
  - Aeroméxico conserva el azul de marca.
  - Volaris y Viva usan `#d05aa8` y `#1a9a5c`, validados con el verificador de paleta:
    separación CVD ≥ 9.5 entre todos los pares y contraste ≥ 3:1.
  - Industria va en gris punteado.

## Código

- **Estado y selector:** `web/src/views/shell/carriers.ts`, con su prueba en
  `carriers.test.ts`.
- **Datos:**
  - `web/src/views/executive/entities.ts`: acceso por entidad y `market.json`.
  - `web/src/views/executive/market.ts`: tarjeta de participación.
- **Economía:**
  - `web/src/views/economy/{kpis,table}.ts`: tarjetas y tabla por entidad.
  - `charts.ts` se dividió en `chart-common.ts` y `compare.ts` para respetar el límite de
    400 líneas.
- **Vuelos:** `web/src/views/flights/carriers.ts` (tarjetas y mezcla por aerolínea), con
  ganchos en `quarter.ts`, `mix.ts` y `bootstrap.ts`.
- **Backend:**
  - `rpk_km` en los registros por entidad (contrato `executive.schema.json`), para el RPM
    de Vuelos.
  - La comparación “vs. industria” ya no repite la etiqueta en el valor.
- **Compatibilidad:** sin el bloque `entities` (un export anterior), la página se queda
  como la v1.

## Validación

- **Web:** `npm run check` y `npm run test` (73 pruebas).
- **Python (CI):** `pytest -m "not local_data and not browser"`. Falla solo
  `test_unmodified_copy_passes`, porque `site/` sigue firmado contra los contratos
  anteriores.
- **Navegador:** `pytest -m browser` pasa; las 3 pruebas de `site/` se omiten por la misma
  razón.
- **Revisión visual:** capturas con Playwright del build real (`npm run build && vite
  preview`) en escritorio y móvil, en default y con dos o tres aerolíneas.

## Pendiente

- **Re-firmar `site/`** con el gate. Está pendiente de autorización porque la herramienta
  lo bloquea como despliegue. La publicación debe excluir la estimación internacional de
  pasajeros, que sigue sin aprobarse.
- **Fases siguientes:**
  - Fase 3: mapa por aerolínea.
  - Fase 4: capacidad por ruta de Volaris y Viva.
  - Fase 5: tesis de la industria y por aerolínea, con aprobación del dueño.
