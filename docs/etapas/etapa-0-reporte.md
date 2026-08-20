# Etapa 0 — Setup

Fecha de cierre: 2026-08-20
Estado: COMPLETA

## Qué se construyó

- Repositorio reproducible con Python 3.13, `uv.lock`, dependencias exactas y
  grupos `analytics`, `dashboard` y `dev`.
- Estructura completa bronze/silver/gold, paquetes de ingesta, parseo,
  transformación, analítica y dashboard.
- `src/config.py` con identidades, rutas, URLs y límites conservadores.
- Cliente HTTP con `User-Agent` SEC obligatorio, token bucket, timeout, retry con
  backoff+jitter y logging de cada intento.
- Almacenamiento bronze inmutable con SHA-256, metadata, deduplicación global,
  versionado y ledger de restatements.
- Logging JSON + consola y ledger append-only de calidad de datos.
- Smoke test de ocho fuentes y verificador reproducible de CIKs.
- `justfile`, workflow de GitHub Actions, README y shell mínimo de Streamlit.

## Datos obtenidos

| Fuente | Periodos | Filas | Tamaño | Método de acceso |
|---|---|---:|---:|---|
| SEC `company_tickers.json` | Snapshot 2026-08-20 | Catálogo JSON completo | 794,799 bytes | httpx |

Archivo: `data/bronze/sec/sec_company_tickers_current_20260820T173101Z.json`
SHA-256: `84f1c78aabb686e73e6ec3d1e4df59e0571d2cd33b44d25bd345f68c0f5e0b0c`

El archivo crudo y su `.meta.json` permanecen locales. El manifiesto con hash y
URL sí se versiona conforme a la decisión del usuario.

## Validaciones ejecutadas

| Check | Resultado | Detalle |
|---|---|---|
| Entorno bloqueado | PASS | 122 paquetes resueltos; 121 instalados, Python 3.13.15 |
| Suite | PASS | 21 tests en 0.34 s en la validación final |
| Rate limiter | PASS | Test determinista: 2 req/s produce adquisiciones en 0.0, 0.5 y 1.0 s |
| `save_bronze()` | PASS | Bytes exactos, hash, metadata, dedupe, `_v2` y restatement probados |
| SEC sin identidad | PASS | Falla antes de red si falta `SEC_USER_AGENT` |
| HTTP retry | PASS | 503 reintentado; 404 no reintentado |
| Smoke test | PASS | Ocho fuentes; ninguna excepción no manejada |
| DuckDB | PASS | `data/warehouse.duckdb` abrió y ejecutó `select 1` |
| Stack principal | PASS | DuckDB, Polars, PyArrow, Pandas, Streamlit y spaCy cargaron |
| Comandos `just` | PASS | `setup`, `test`, `ingest`, `parse`, `transform`, `rebuild`, `verify-identities`; dashboard inició en puerto controlado |
| Idempotencia de identidad | PASS | Segunda corrida reutilizó el mismo archivo/hash; manifiesto conserva una fila |

## Cifras ancla verificadas

| Métrica | Esperado | Obtenido | ¿Coincide? |
|---|---|---|---:|
| CIK Aeroméxico | `0001561861` | `0001561861` | Sí |
| CIK Volaris | `0001520504` | `0001520504` | Sí |
| Fuentes en matriz | 8 | 8 | Sí |

No corresponden cifras financieras u operativas a la Etapa 0.

## Qué NO funcionó y por qué

- El plan llegó directamente en `docs/`, no en `docs/plan/`; se reubicó sin
  pérdida para cumplir la arquitectura.
- La primera resolución de `statsforecast` usó 2.0.1 sin wheel de Windows y
  trató de compilar C++. Se fijó 2.1.1, que sí publica wheel para Python 3.13;
  no se instalaron Visual C++ Build Tools.
- El primer comando de descarga del modelo spaCy no encontró `uv` por el PATH
  aún no refrescado de la sesión. Se expuso el binario ya instalado y el modelo
  quedó bloqueado en `pyproject.toml`/`uv.lock`.
- La validación final encontró el mismo PATH sin refrescar en el proceso de Codex;
  se repitió con las rutas persistentes de usuario y todos los checks pasaron. Una
  terminal nueva recibe ambas rutas de WinGet normalmente.
- Aeroméxico IR falló con httpx y Chromium headless; funcionó con Chromium
  visible aislado. Se adoptó EDGAR como fuente primaria.
- EIA devolvió 403 porque `EIA_API_KEY` está vacío. No es evidencia de anti-bot.
- Al instalar Chromium 1234, Playwright eliminó automáticamente de su caché las
  revisiones no usadas 1228; son binarios regenerables, no datos del proyecto.

## Decisiones tomadas

- No versionar bronze; versionar manifiesto, restatements y fixtures pequeños.
- Python 3.13 para conservar wheels de todo el stack previsto.
- Dependencias directas con pins exactos y transitivas cerradas en `uv.lock`.
- Logging estándar de Python con formatter JSON; evita una dependencia adicional.
- `statsforecast` como motor especializado de forecast, junto con statsmodels.
- EDGAR primero y portal IR únicamente como fallback visible.
- Deshabilitar telemetría de uso de Streamlit.

## Supuestos hechos

- El correo entregado para `SEC_USER_AGENT` es real y monitoreado.
- Banxico y EIA seguirán sin token/key hasta la Etapa 4; FRED sigue siendo
  alternativa válida para combustible si no se configura EIA.
- Los targets de ingesta/parseo/transformación son entry points vacíos y honestos
  en Etapa 0; cada etapa posterior registrará trabajo real sin cambiar la interfaz.

## Preguntas para el usuario

Ninguna pendiente para cerrar la Etapa 0.

## Riesgos para la siguiente etapa

- El portal IR no es automatizable headless en la prueba actual; SEC debe cubrir
  el descubrimiento de 6-K/20-F.
- El acceso a la página BMV/AFAC no demuestra todavía acceso a sus archivos.
- `companyfacts` debe inspeccionarse en Etapa 1; el plan advierte que puede seguir
  prácticamente vacío.
- Los secretos gratuitos de Banxico/EIA no están configurados todavía.

## Comandos para reproducir

```powershell
just setup
just test
just smoke-test
just verify-identities
uv run python -c "import duckdb; duckdb.connect('data/warehouse.duckdb').close()"
git log --oneline
```
