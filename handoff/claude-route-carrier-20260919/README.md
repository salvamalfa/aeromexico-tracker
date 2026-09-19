# Entrega: estimador de pasajeros por ruta y aerolínea (mercado nacional mexicano)

Fecha: 19 de septiembre de 2026 · Autor: sesión de Claude Code · Destinatario: Codex

---

## 1. El problema y lo que se construyó

El dashboard muestra, para cada ruta que toca Estados Unidos, pasajeros, asientos
y ocupación por aerolínea. Eso viene de BTS T-100, que publica ese cruce hecho.

Para México no existe nada equivalente. AFAC publica **dos cortes del mismo
universo y nunca la celda**: pasajeros por par de ciudades sumando todas las
aerolíneas, y pasajeros por aerolínea sumando toda su red. Ninguno dice cuántos
de los 258,813 pasajeros de México–Cancún de julio de 2026 fueron de Volaris.

Que el cubo conjunto existe está demostrado: sobre 22 meses, **20 reconcilian
exactamente al pasajero** entre las dos publicaciones; las otras dos difieren en
10 y 36 sobre totales cercanos a cinco millones.

**La solución construida** es un ajuste iterativo proporcional (IPF): se parte de
una semilla que aporta la *estructura* de la oferta —cuántos vuelos hizo cada
aerolínea en cada ruta— y se escala hasta satisfacer ambas marginales publicadas
a la vez. La semilla nunca aporta pasajeros; los pasajeros son de AFAC.

## 2. Qué está terminado y qué falta

### Terminado

| Componente | Archivo | Pruebas |
|---|---|---:|
| Estimador IPF y arnés de validación contra T-100 | `src/analytics/route_carrier.py` | 29 |
| Prueba de aceptación de una fuente candidata | `src/analytics/seed_acceptance.py` | 15 |
| Reconstrucción de las marginales de AFAC | `src/ingest/afac/margins.py` | 8 |
| Adaptador de itinerarios AeroDataBox | `src/ingest/aerodatabox/flights.py` | 14 |
| CLI con `--dry-run`, presupuesto y muestreo ponderado | `src/ingest/aerodatabox/__main__.py` | 11 |
| Marginales y crosswalks | `data/reference/*.csv` | — |
| Documentación de método, fuentes y decisiones | `docs/*.md` | — |

**Exactitud medida** (ver `evidence/`): 1.40 pp de error en participación con
semilla de asientos, **1.98 pp con semilla de conteo de vuelos**, sobre rutas
competidas de T-100 en 2025.

### Falta

1. **La semilla.** Es el único insumo pendiente. Se compra un mes del plan
   Starter de AeroDataBox (USD 19, 40,000 unidades). Sin ella no hay estimación.
2. **Materializar el hecho** como tabla gold con su contrato y linaje.
3. **Publicar** en el Streamlit interno y en el HTML público.
4. **Asientos y ocupación**, que requieren una tabla de configuración por
   aerolínea y modelo derivable de T-100.

El plan completo, con fases, riesgos y decisiones abiertas, está en
[`original-plan.md`](original-plan.md).

## 3. Rama, commits y parches

| | |
|---|---|
| Rama de trabajo | `claude/pasajeros-aerolinea-ruta-mexico-q49ycz` |
| **Commit base de los parches** | **`26d3617`** (`Publish expanded Aeromexico flights coverage`) |
| HEAD al cerrar | `dc55d07` |
| Rama de esta entrega | `claude/route-carrier-handoff-20260919` |

Los cinco PRs ya están mergeados a `master`:

| PR | Commit | Qué aporta |
|---|---|---|
| #1 | `6d2656b` | Investigación, estimador IPF y elección de fuente |
| #2 | `1400621` | Comando único para convertir cuota en estimaciones |
| #3 | `137b7e1` | Cobertura medida contra los vuelos publicados por AFAC |
| #4 | `8b8bf0d` | Ponderación por día de la semana; los dos planes de la API |
| #5 | `dc55d07` | Host correcto del plan directo; veredicto por completitud |

### Parches

`patches/` contiene **19 parches** de `git format-patch`, generados con
`--binary --no-signature` desde `26d3617`. Aplicar en orden:

```bash
git checkout 26d3617
git am --3way handoff/claude-route-carrier-20260919/patches/*.patch
```

**Verificado**: los 19 aplican limpio sobre `26d3617` y producen un árbol
**idéntico** al de `dc55d07`. No hay `working-tree.patch` porque el árbol estaba
limpio: todo el trabajo está en commits.

## 4. Cómo ejecutar

```bash
# Pruebas del código entregado (89 pruebas)
uv run pytest tests/test_route_carrier_ipf.py tests/test_seed_acceptance.py \
              tests/test_afac_margins.py tests/test_aerodatabox_flights.py \
              tests/test_aerodatabox_cli.py

# Backtest contra T-100: reimprime el error medido
uv run python -m src.analytics.route_carrier

# Plan de llamadas a la API sin gastar cuota
uv run python -m src.ingest.aerodatabox 2026M07 --dry-run

# El día que exista la llave (AERODATABOX_API_KEY o RAPIDAPI_KEY en .env)
uv run python -m src.ingest.aerodatabox 2026M07
```

El comando barre los 58 aeropuertos, cachea cada respuesta en disco, arma la
semilla, corre la prueba de aceptación y **solo entonces** ajusta. Si la semilla
no pasa, sale con código 2 y no publica nada.

## 5. Resultados reales de las pruebas

Ejecutadas el 19 de septiembre de 2026 en este contenedor:

```
Código entregado:   89 passed in 5.04s
Suite completa:     268 passed, 4 failed, 5 skipped in 58.37s
```

Las cuatro fallas son `test_stage9_lineage`, `test_stage9_scd2` y dos de
`test_stage9_silver_contracts`. **Son artefacto del entorno, no regresión**: este
contenedor no tiene `data/silver/`, que `.gitignore` excluye. Se verificó que
fallan idénticas en `master` sin ninguno de estos cambios. En un checkout local
con la capa silver poblada deberían pasar, pero **eso no está verificado**.

Salidas completas en `evidence/pruebas_*.txt`.

## 6. Supuestos, limitaciones y decisiones pendientes

### Supuestos no verificados

1. **El 1.98 pp está medido en rutas México–Estados Unidos, no en el mercado
   doméstico.** Que el doméstico se comporte igual es extrapolación. Es la
   limitación más importante de toda la entrega.
2. **La ventana histórica del proveedor está en disputa**: 180 días según el
   tarifario, pero una consulta a 224 días funcionó y una a 379 no. Acotada entre
   225 y 378. Se resuelve con 8 unidades antes de gastar el resto.
3. **El muestreo semanal no está validado** contra datos reales.
4. **El presupuesto no alcanza para siete meses completos**: 49,184 unidades
   contra 40,000. Caben cinco completos, o siete si el muestreo semanal valida.

### Limitaciones de esta revisión

Se trabajó desde un contenedor con un clon limpio. **No se pudo inspeccionar**:
el generador local de `static/aeromexico_tracker.html`, las ingestas locales de
ANAC, Aerocivil, CAA y slots del AICM, ni `data/silver`, `data/bronze` o el
warehouse. Todo juicio sobre esos bloques es inferencia desde el código
versionado. **Donde el código local contradiga esta entrega, manda el local.**

### Decisiones pendientes

1. **Linaje**: los padres naturales de la tabla nueva son las marginales de AFAC,
   que hoy son CSV en `data/reference/` y no tablas gold con `record_id`. O se
   acepta linaje por declaración, o se suben primero a gold. Se recomienda lo
   segundo.
2. **`dim_route` no tiene ni una ruta doméstica** (0 de 3,407). Hay que
   extenderla antes de declarar cualquier clave foránea.
3. **Las 56 rutas domésticas que ya están en el HTML** (`domestic_networks`,
   `2026Q2`) vienen de slots del AICM y una heurística de monopolio, para
   exactamente el trimestre que el IPF estimaría. Hay que decidir si sustituye,
   convive o corrige.
4. **Un bug conocido**: `src/ingest/aerodatabox/__main__.py:176` pone
   `is_estimated = True` en todas las filas, pero el estimador ya emite
   `is_exact` para rutas de un solo operador, que **no son estimación**. Debe ser
   `is_estimated = ~is_exact`.

## 7. Archivos creados o modificados

Copia íntegra en `files/`, preservando la estructura del repositorio.

### Creados

```
src/analytics/route_carrier.py            540 líneas   estimador IPF + arnés
src/analytics/seed_acceptance.py          395 líneas   aceptación de la semilla
src/ingest/afac/margins.py                273 líneas   marginales de AFAC
src/ingest/aerodatabox/flights.py         332 líneas   adaptador de itinerarios
src/ingest/aerodatabox/__main__.py        184 líneas   CLI y dry-run
src/ingest/aerodatabox/__init__.py
tests/test_route_carrier_ipf.py            29 pruebas
tests/test_seed_acceptance.py              15 pruebas
tests/test_afac_margins.py                  8 pruebas
tests/test_aerodatabox_flights.py          14 pruebas
tests/test_aerodatabox_cli.py              11 pruebas
data/reference/afac_od_nacional_regular.csv        13,224 filas, 22 meses
data/reference/afac_carrier_domestic.csv              180 filas, 22 meses
data/reference/afac_carrier_flights_domestic.csv      145 filas, 19 meses
data/reference/afac_city_iata_crosswalk.csv            58 ciudades ↔ IATA
data/reference/afac_carrier_crosswalk.csv               9 nombres ↔ carrier_key
docs/estimador-ruta-aerolinea.md          método, fuentes, costos, umbrales
docs/pasajeros-por-ruta-y-aerolinea.md    la investigación y sus pruebas
docs/solicitud-pnt.md                     solicitud de transparencia (vía descartada)
```

### Modificados

```
.env.example                  ranuras AERODATABOX_API_KEY y RAPIDAPI_KEY
src/ingest/afac/__init__.py   docstring del paquete
```

**No se tocó el dashboard.** Ni `static/aeromexico_tracker.html`, ni
`src/dashboard/`, ni `streamlit_app.py`.

## 8. Qué NO se incluye

Por instrucción explícita y por higiene:

- Llaves de API, tokens, correos o secretos. `.env` está en `.gitignore` y **no**
  se copió. `.env.example` sí se incluye: se verificó que sus ocho variables
  están vacías.
- Respuestas crudas de AeroDataBox.
- `data/bronze`, `data/silver`, warehouses DuckDB, entornos virtuales.
- Cualquier cambio al dashboard.

Los CSV de `data/reference/` sí se incluyen: derivan de estadística pública de
AFAC y DATATUR, y ya estaban versionados en el repositorio.

### Una salvedad sobre los parches

Se escaneó la entrega en busca de secretos: **no hay ninguna llave de API**. Sí
aparecen tres direcciones de correo, todas ya presentes en el repositorio y
ninguna nueva:

- `salvamalfas@gmail.com`, en las cabeceras `From:` de los 19 parches, por ser el
  autor de los commits. Quitarla rompería la autoría que `git am` preserva y
  además invalidaría la verificación de que los parches reproducen un árbol
  idéntico.
- `transparencia@afac.gob.mx` y `maria.bello@sict.gob.mx`, en
  `docs/solicitud-pnt.md`, que son contactos oficiales de transparencia
  publicados por el propio gobierno. Ese documento describe una vía que se
  **abandonó**; se conserva porque registra por qué.

Si se prefiere que no viajen, los parches se regeneran con
`git format-patch --from='Codex <codex@example.com>'`, a costa de la autoría.

## 9. Integridad

`MANIFEST.sha256` trae el SHA-256 de todos los archivos de la entrega. Para
verificar:

```bash
cd handoff/claude-route-carrier-20260919 && sha256sum -c MANIFEST.sha256
```
