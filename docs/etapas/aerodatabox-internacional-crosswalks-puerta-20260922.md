# Crosswalks, puerta de aceptación y plan de captura internacional

Fecha: 22 de septiembre de 2026.
Alcance: completar todo el trabajo preparatorio del IPF internacional que no
requiere gastar unidades de AeroDataBox — los dos crosswalks, la puerta de
aceptación, el adaptador al contrato del IPF, la agregación Grupo Aeroméxico,
la exclusión de doble conteo con T-100, y un plan de captura verificado por
`--dry-run` y un `preflight` offline.
Estado: **no se consumió ninguna unidad de API en esta sesión.** El sondeo de
8 unidades del 2026-09-10 (documentado en
[`aerodatabox-internacional-investigacion-20260921.md`](aerodatabox-internacional-investigacion-20260921.md))
no se repitió. No se despachó el workflow de captura del repositorio privado.
No se tocó el dashboard, `flight_evidence_v1`, la elegibilidad histórica ni el
Analysis Agent.

Este reporte es un registro de la sesión. El contenido técnico completo,
verificable y destinado a durar está en el documento canónico
[`docs/estimacion-pasajeros-ruta-aerolinea.md`](../estimacion-pasajeros-ruta-aerolinea.md)
§§9.5–9.10, que es la referencia a leer antes de tocar el estimador
internacional.

## Qué se construyó

| Pieza | Archivo | Pruebas |
|---|---|---:|
| Crosswalk ciudad AFAC internacional ↔ IATA | `src/ingest/afac/international_crosswalks.py` + `data/reference/afac_international_city_overrides.csv` (54 reglas) → `afac_international_city_iata_crosswalk.csv` | 10 |
| Crosswalk aerolínea AFAC ↔ IATA/ICAO | `data/reference/afac_international_carrier_crosswalk.csv` (62 aerolíneas, 3 niveles de confianza) | (mismas 10) |
| Puerta de aceptación internacional | `src/analytics/international_route_carrier.py`, `international_seed_acceptance_v1` | 20 |
| Verificación offline de captura | subcomando `preflight` en `src/ingest/aerodatabox/international_cli.py` | 8 |
| Diagnósticos de codeshare/estado en la semilla | `src/ingest/aerodatabox/international.py` (`codeshare_unknown`, `status_incomplete`) | (cubiertas en las 20 + 8) |
| Workflow de captura mensual, tope duro | `.github/workflows/aerodatabox-international-sweep.yml` (repositorio privado) | — |

**38 pruebas nuevas**, todas enfocadas en el modo de falla, no en el caso
feliz: cada comprobación de la puerta tiene un test que la dispara sola y dos
que confirman que las demás comprobaciones no se disparan por error.

## Resultado de los crosswalks

Cobertura final, tras corregir dos errores encontrados durante la
construcción (ver más abajo):

| Marginal | Cobertura | Detalle |
|---|---:|---|
| Rutas (`REG INT`) | **100 %** de pasajeros, en los 7 meses | 178 etiquetas de ciudad → 241 aeropuertos, 0 sin resolver |
| Aerolíneas | **99.7 – 99.9 %** de pasajeros, según el mes | 57 de 62 aerolíneas usables (34 `resolved` + 23 `probable`); 5 `unresolved` (≤0.07 % cada una) |

Aerolíneas sin resolver, con su participación en el total: `SKY Airline Perú`
(0.07 %), `Volaris El Salvador` (0.06 %), `Breeze Airways` (0.05 %), `Orbest`
(0.04 %), `Aerus` (0.01 %). Ninguna entra a la semilla; sus pasajeros AFAC
quedan fuera de la marginal de aerolínea y se reportan como brecha, no se
reparten entre vecinos.

### Dos errores encontrados y corregidos en el propio proceso de construcción

1. **`United Airlines` contra `United Airlines, Inc.`**: la primera versión
   del crosswalk de aerolínea usaba el nombre corto; la marginal real de AFAC
   usa la razón social completa. La discrepancia de escritura descartaba en
   silencio el **9.5 % de los pasajeros internacionales** — la aerolínea
   individual más grande del margen. Se detectó porque `build()` ahora incluye
   `carriers_missing_from_crosswalk()`, un guardia dedicado que compara los
   nombres de la marginal contra los del crosswalk y reporta cualquier nombre
   de la marginal que el crosswalk no mencione en absoluto, en vez de dejarlo
   pasar como "cobertura baja" sin explicación. Tiene su propia prueba
   (`test_a_margin_name_absent_from_the_crosswalk_is_reported_loudly`).
2. **`LIÈGE` contra `LIEGE`**: la etiqueta real de AFAC lleva acento grave
   (`È`, U+00C8); el override inicial la escribió sin acento. Como el
   emparejamiento de overrides usa la clave exacta `(ciudad, país)` — no la
   forma normalizada, que solo se usa para el emparejamiento automático contra
   `dim_airport` —, el override no coincidía y la etiqueta quedaba sin
   resolver, bajando la cobertura de rutas de 100 % a 99.90 %. Corregido
   comparando bytes exactos de la fuente.

Ninguno de los dos errores llegó a publicarse en ningún artefacto: ambos se
detectaron y corrigieron dentro de esta misma sesión, antes de cualquier
commit. Se documentan porque son precisamente el tipo de fallo silencioso que
el diseño de "no adivinar por parecido de nombre" busca hacer visible, y en
ambos casos el mecanismo cumplió su función.

## Resultado de la puerta de aceptación

Nueve comprobaciones (duplicados, direcciones perdidas, operadores ambiguos,
Aeroméxico sin separar, operadores sin revisar, codeshare sin resolver,
cobertura de rutas, cobertura de aerolíneas, márgenes incompatibles, soporte
estructural inviable, vuelos por encima de AFAC, estado no operado — ver la
tabla completa en el documento canónico §9.8). Cada una reporta un `Finding`
con severidad propia (`reject`/`review`/`note`) en vez de un solo
pasa/no-pasa, para que quede explícito cuál propiedad falló.

**Ensayada contra datos reales, sin gastar unidades**: T-100 reconstruido con
la forma de una captura (vuelos por ruta y operador) sustituye a la semilla
real, que todavía no existe. Como T-100 solo cubre México–Estados Unidos, el
resultado esperado y obtenido es `REJECT` por cobertura (63–67 % de rutas,
78–84 % de aerolíneas según el mes) — lo que confirma que la puerta distingue
correctamente una semilla parcial de una completa, no que el método falle. La
razón de vuelos semilla/AFAC de 0.99 en las rutas comparables confirma que el
adaptador reproduce fielmente el volumen donde sí tiene datos.

## Plan de captura preparado

Diseño híbrido, aeropuertos priorizados por pasajeros internacionales AFAC
acumulados (ene–jul 2026):

- **Núcleo** (6 aeropuertos: CUN, MEX, GDL, SJD, PVR, MTY) — 88.6 % del
  tráfico internacional — capturado **mes completo**.
- **Resto** (31 aeropuertos) — 11.4 % — capturado en **muestra ponderada de
  siete días**, mismo mecanismo que el barrido nacional.

| Mes | Costo total | Margen en la ventana histórica (hipótesis de 210 días, no verificada) |
|---|---:|---|
| 2026M03 | 1,612 | **5 días** — se sale el 27-sep-2026 |
| **2026M04** | **1,588** | **36 días — recomendado** |
| 2026M05 | 1,612 | 67 días |
| 2026M06 | 1,588 | 98 días |
| 2026M07 | 1,612 | 128 días |

Se recomienda **2026M04 sobre marzo**: marzo tiene solo cinco días de margen
bajo una hipótesis de ventana histórica que sigue sin confirmarse contra el
panel de la suscripción, y una captura fallida a mitad de camino sin margen
para reintentar es peor que perder cinco días de opción.

Comandos preparados en el documento canónico §9.10.3 y en
`.github/workflows/aerodatabox-international-sweep.yml`
(`salvamalfa/aeromexico-tracker-data`, sin despachar). Costo máximo
combinado para abril: **1,588 unidades**.

### Verificación offline

`uv run python -m src.ingest.aerodatabox.international_cli preflight` — nuevo
subcomando — confirmó, sin emitir una sola solicitud HTTP:

- la credencial resuelve a RapidAPI (`RAPIDAPI_KEY` presente,
  `AERODATABOX_API_KEY` ausente);
- una ventana en caché no se vuelve a comprar (reanudación);
- el contenido de más de 7 días se elimina y no se reutiliza (retención);
- un plan que excede el presupuesto se rechaza antes de la primera llamada
  (tope duro).

La deduplicación se verificó por construcción (el `groupby` de la
normalización) y por la comprobación 1 de la puerta; que dos capturas del
mismo mes con aeropuertos distintos no se pisen se verificó con `--tag` en el
subcomando `sweep`.

## Validación

- 38 pruebas nuevas, todas aprobadas.
- Las 168 pruebas enfocadas de todo el trabajo internacional (crosswalks +
  puerta + preflight + márgenes + semilla + backtest + IPF + adaptador + CLI +
  márgenes domésticos) pasan juntas.
- Suite completa del clon de nube: **462 aprobadas, 47 fallidas** (la misma
  línea base documentada desde el 2026-09-21: `data/silver/`, `data/bronze/`
  y `analysis_runs/` no existen en un clon público). Cero fallas nuevas; 63
  pruebas más aprobadas que en la ronda anterior (todas las nuevas). Ninguna
  falla toca los módulos internacionales.
- `git diff --check` limpio en ambos repositorios; sin secretos, sin archivos
  de Bronze temporal, sin artefactos accidentales.

## Qué sigue

El único paso pendiente es la primera captura pagada de 2026M04
(§9.10.3 del documento canónico), a decisión explícita del operador. Después
de eso, el resto del tubo —ajuste, agregación, backtest con semilla real,
vista de revisión humana— ya está descrito y en código, pendiente solo de
datos.
