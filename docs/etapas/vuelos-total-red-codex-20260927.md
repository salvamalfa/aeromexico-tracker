# Vuelos: total de la red y rutas sin volumen (hallazgos de Codex) — 2026-09-27

Cierra los hallazgos de interfaz de Codex que seguían abiertos en PRs
anteriores (#6, #7, #8, #10 y #19), verificados contra la vista real de
`web/`.

## Qué cambió y por qué

**1. El total de vuelos mezclaba vuelos observados con programados
(#10).** `web/src/views/flights/volume.ts` sumaba `departures` de todas las
rutas salvo las estimadas con AeroDataBox, bajo la etiqueta "vuelos operados
por Aerovías de México". Así entraban los slots asignados del AICM y el
anuncio fechado de OMA (`assigned_slot_not_flown`,
`scheduled_from_dated_release`), que son programación, y los movimientos de
mercado AFAC atribuidos por exclusividad (`carrier_inferred_market_observed`),
que son inferencia. Ahora el titular cuenta solo vuelos observados. Los
programados y los inferidos aparecen en líneas propias, con su número de
rutas, y se aclara que no se incluyen arriba.

**2. Las rutas con presencia pero sin volumen desaparecían sin aviso
(#10).** `network.ts` filtra, a propósito, las rutas sin volumen propio (por
ejemplo, las ocho de AIFA con `carrier_route_present_volume_unresolved`),
porque no hay magnitud que dibujar. El filtro se conserva, pero ahora se
cuenta cuántas quedaron fuera, respetando la región seleccionada, y la línea
de volumen lo declara: "N rutas con presencia documentada de Aeroméxico sin
volumen atribuible (N/D), no dibujadas en el mapa ni en la tabla".

**3. Una región elegida en otro trimestre dejaba la vista vacía (#7).** Al
pasar de 2T26 con Europa o Asia seleccionada a un trimestre sin rutas de esa
región, `selectedRegion` seguía activo: el mapa, la tabla y la línea de
volumen quedaban vacíos, y el botón activo ni siquiera se mostraba. La nueva
función `normalizeSelectedRegion` (`regions.ts`) limpia la selección cuando
el periodo no tiene rutas de esa región.

**4. El recorte del mapa no se recalculaba al redimensionar (#8).**
`fitViewToCanvas` fija rangos de latitud y longitud según el aspecto del
lienzo, pero el `resize` solo realineaba el detalle. Ahora, si cambia el
ancho del lienzo con la pestaña de Vuelos visible, `bootstrap.ts` vuelve a
dibujar el mapa, a lo más una vez por cuadro.

## Hallazgos que ya no aplican

- **#6** (`static/aeromexico_tracker.html`, texto que prometía fuente,
  meses y estado por fila): ese HTML ya no existe. En `web/` cada fila lleva
  su punto de cobertura (`coverageDotHtml`) y el icono de programado
  (`scheduledIconHtml`), así que no queda un texto que prometa detalle
  ausente.
- **#19, botón Nacional que no reabría la vista**: en `web/` la carga inicial
  y el clic usan la misma función, `domesticAvailableForQuarter`, así que el
  botón alterna en ambos sentidos.
- **#19, extensión del mapa para `estimated_domestic`**: `map.ts` elige la
  extensión de México según `state.networkMode === "domestic"`, sin importar
  el modo del payload, así que la red nacional estimada ya usa la vista
  nacional.

## Cómo se validó

- `cd web && npm run check && npx vitest run && npm run build` → tsc sin
  errores; 63 pruebas Vitest; dos nuevas en `volume.test.ts` (el titular
  excluye programados e inferidos, que se listan aparte, y la línea declara
  las rutas solo de presencia) y dos en `regions.test.ts`
  (normalización de la región).
- El redimensionado del mapa no tiene prueba automática: depende del
  tamaño real del lienzo en el navegador.
- Sin cambios en Python ni en `site/`.

## Límites

- `site/` no se republicó: el cambio llega al dashboard público cuando el
  dueño regenere y publique.
- Las rutas solo de presencia siguen sin dibujarse; solo se declaran.
