# 01 — Arquitectura y Convenciones

## 1. Stack decidido

| Capa | Herramienta | Por qué |
|---|---|---|
| Lenguaje | Python 3.11+ | Perfil del usuario |
| Gestor de entorno | `uv` (preferido) o `venv` + `pip` | Reproducibilidad |
| Almacenamiento analítico | **DuckDB** (archivo local `.duckdb`) + **Parquet** en disco | Analítico, embebido, cero infra, lee Parquet nativo |
| Formato de intercambio | Parquet (snappy) | Tipado, comprimido, portable |
| DataFrames | Polars (preferido) o Pandas | Polars por rendimiento y API estricta; Pandas aceptable si simplifica |
| Transformación | SQL sobre DuckDB, encapsulado en archivos `.sql` versionados | El usuario piensa en SQL; facilita migrar a BigQuery |
| Parseo de PDF | `pdfplumber` (tablas) + `pypdf` (texto/metadata) + `camelot` como fallback | Los comunicados traen tablas complejas |
| Parseo de Excel | `openpyxl` / `xlrd` (para `.xls` viejos) / `pandas.read_excel` | AFAC usa formatos viejos |
| XBRL | `python-xbrl` / `arelle` / parseo directo de XML | XBRL de BMV usa taxonomías IFRS de CNBV |
| HTTP | `httpx` con reintentos y rate limiting | Async cuando convenga |
| Navegador headless | **Playwright** | Para sitios que bloquean requests |
| Computer use | Herramienta nativa de Claude Code | Último recurso, ver archivo 12 |
| Validación de datos | `pandera` o `pydantic` + checks SQL propios | Contratos de esquema explícitos |
| Testing | `pytest` | Fixtures con archivos bronze reales congelados |
| Orquestación | **GitHub Actions** con `cron` | Cadencia trimestral, gratis |
| Dashboard | **Streamlit** | Python puro, despliegue trivial, encaja con narrativa |
| Gráficas | **ECharts** (vía `streamlit-echarts`) + Plotly donde convenga | Open source real (Apache 2.0 / MIT) |
| Despliegue | Streamlit Community Cloud (gratis) | Portafolio público |

### Opción cloud (no obligatoria, decisión de Etapa 6)
BigQuery free tier (10 GB storage, 1 TB query/mes) como destino espejo de la capa gold.
El usuario ya lo domina. Se implementa **solo si** en la Etapa 6 se decide que aporta;
DuckDB local es suficiente para el volumen de este proyecto.

## 2. Modelo de capas: bronze / silver / gold

```
data/
├── bronze/              # CRUDO. INMUTABLE. Nunca se edita ni se borra.
│   ├── sec/
│   │   ├── submissions/
│   │   ├── filings/{accession_no}/     # documentos tal cual bajaron
│   │   └── companyfacts/
│   ├── bmv/xbrl/{ticker}/{periodo}/
│   ├── afac/{año}/{mes}/
│   ├── bts/t100/{año}/
│   ├── banxico/
│   ├── eia/
│   ├── market/
│   ├── airports/                        # ASUR, GAP, OMA
│   ├── reference/                       # OurAirports, OpenFlights
│   └── peers/{carrier}/
├── silver/              # Normalizado, tipado, una fila = un hecho atómico
│   └── *.parquet
├── gold/                # Tablas maestras dimensionales, listas para consumo
│   └── *.parquet
└── warehouse.duckdb     # Vistas y tablas sobre silver/gold
```

### Reglas de bronze
- Nombre de archivo: `{fuente}_{entidad}_{periodo}_{fecha_descarga}.{ext}`
- Cada archivo bronze tiene un `.meta.json` hermano con:
  ```json
  {
    "source_system": "sec_edgar",
    "source_url": "https://...",
    "downloaded_at": "2026-08-17T10:23:00Z",
    "sha256": "...",
    "http_status": 200,
    "content_type": "application/pdf",
    "bytes": 482911,
    "download_method": "httpx | playwright | computer_use",
    "notes": "..."
  }
  ```
- Si un archivo ya existe con el mismo sha256, **no se re-descarga**.
- Si existe con distinto sha256 (la fuente cambió/reexpresó), se guarda el nuevo con
  sufijo `_v2`, `_v3`, y se registra en `data/bronze/_restatements.jsonl`.

### Reglas de silver
- Un archivo Parquet por dominio-fuente (ej. `silver/sec_operating_metrics.parquet`).
- Todo tipado explícitamente. Sin `object`/`string` para números.
- Columnas de linaje obligatorias en toda tabla silver:
  `source_system`, `source_file`, `source_hash`, `ingested_at`, `parser_version`.
- Sin agregaciones ni cálculos de negocio. Silver = lo que dijo la fuente, limpio.

### Reglas de gold
- Modelo dimensional (ver archivo 08).
- Aquí sí viven los cálculos derivados, conversiones de unidad y normalizaciones.
- Toda métrica derivada lleva columna `is_derived = true` y su fórmula documentada
  en el diccionario de datos.

## 3. Estructura del repositorio

```
aeromexico-dashboard/
├── README.md
├── pyproject.toml
├── .env.example                  # nunca .env real en el repo
├── .gitignore                    # data/bronze/ y data/*.duckdb ignorados por defecto
├── docs/
│   ├── plan/                     # ESTE PLAN
│   ├── etapas/                   # reportes de cierre por etapa
│   ├── diccionario-datos.md      # generado/mantenido desde Etapa 6
│   └── decisiones/               # ADRs cortos: decision-001-xxx.md
├── src/
│   ├── config.py                 # rutas, constantes, tickers, CIKs
│   ├── common/
│   │   ├── http.py               # cliente con rate limit, retry, User-Agent
│   │   ├── storage.py            # escritura bronze + meta.json + hash
│   │   ├── logging.py            # logging estructurado
│   │   └── quality.py            # registro de issues de calidad
│   ├── ingest/
│   │   ├── sec/
│   │   ├── bmv/
│   │   ├── afac/
│   │   ├── bts/
│   │   ├── macro/
│   │   ├── market/
│   │   ├── airports/
│   │   └── peers/
│   ├── parse/                    # bronze → silver
│   ├── transform/                # silver → gold (SQL + Python)
│   ├── analytics/                # forecast, clustering, NLP
│   └── dashboard/                # app Streamlit
├── sql/
│   ├── silver/
│   └── gold/
├── tests/
│   ├── fixtures/                 # archivos bronze congelados para tests
│   └── test_*.py
├── notebooks/                    # exploración; nunca lógica productiva
└── .github/workflows/
    └── refresh.yml
```

## 4. Convenciones de nombres

### Columnas
- `snake_case`, en **inglés** (estándar de industria: `load_factor`, no `factor_ocupacion`).
  Las etiquetas en español van en el diccionario de datos y en el dashboard, no en el esquema.
- Fechas: `*_date` (tipo `date`), timestamps: `*_at` (tipo `timestamp`, UTC).
- Monedas: sufijo explícito → `revenue_usd`, `revenue_mxn`. **Nunca** una columna
  `revenue` sin moneda.
- Unidades: sufijo explícito → `ask_km`, `ask_miles`, `casm_usd_cents`.
- Booleanos: prefijo `is_` / `has_`.
- Porcentajes: guardar como **fracción decimal** (0.844), no como 84.4. Columna `*_pct`.

### Períodos
- `period_id`: `2026Q1`, `2026M03`, `2026`.
- `period_type`: `quarter` | `month` | `year` | `ttm`.
- `period_start_date`, `period_end_date` siempre presentes.
- **Cuidado con los años fiscales**: Ryanair cierra en marzo. Toda tabla lleva
  `fiscal_period_id` **y** `calendar_period_id`. Las comparaciones del dashboard usan
  el calendario, siempre.

### Entidades
- `carrier_key`: clave interna estable, ej. `AEROMEXICO`, `VOLARIS`, `VIVA_AEROBUS`,
  `RYANAIR`, `DELTA`, `IAG`.
- Junto a ella siempre: `iata_code`, `icao_code`, `source_carrier_name` (el nombre literal
  que usó la fuente, para auditar el crosswalk).

## 5. Manejo de secretos

- Ninguna credencial en el repo. Todo vía `.env` (git-ignored) y `os.environ`.
- Secretos necesarios:
  - `SEC_USER_AGENT` — ej. `"AeroMexico Dashboard salva@ejemplo.com"` (obligatorio, la SEC lo exige)
  - `BANXICO_TOKEN` — token gratuito del SIE
  - `EIA_API_KEY` — key gratuita (o usar FRED en su lugar)
  - `FRED_API_KEY` — opcional
- `.env.example` documenta cada variable sin valores reales.

## 6. Logging y calidad de datos

### Logging
`structlog` o `logging` con formato JSON. Cada evento de ingesta registra:
`source`, `url`, `status`, `bytes`, `duration_ms`, `attempt`.

### Registro de calidad
Tabla `data_quality_issues` (Parquet append-only) con:
```
issue_id, detected_at, layer, table_name, source_file, severity,
issue_type, description, affected_rows, resolved
```
Tipos de issue mínimos a detectar:
- `missing_period` — hueco en una serie temporal
- `schema_drift` — columna nueva/faltante/renombrada en la fuente
- `value_out_of_range` — load factor fuera de [0,1], CASM negativo, etc.
- `restatement` — el mismo periodo cambió de valor entre descargas
- `unmapped_entity` — nombre de aerolínea que no está en el crosswalk
- `unit_ambiguity` — no se pudo determinar si una cifra está en km o millas
- `parse_failure` — tabla no encontrada en el documento

**Regla:** el dashboard debe mostrar un panel de "salud de los datos" alimentado por
esta tabla. La honestidad sobre los datos es parte del entregable.

## 7. Manejo de restatements y datos preliminares

Muchas fuentes (AFAC en particular, y los comunicados de resultados) publican cifras
**preliminares sujetas a revisión**.

Solución: **SCD tipo 2 en la capa gold** para tablas de hechos.
```
carrier_key, period_id, metric_key, value,
valid_from,          -- fecha de la descarga que trajo este valor
valid_to,            -- NULL si es el valor vigente
is_current,          -- boolean
is_preliminary,      -- lo declaró la fuente
restatement_count    -- cuántas veces cambió este valor
```
Vistas de conveniencia:
- `v_facts_current` — solo `is_current = true` (uso por defecto del dashboard)
- `v_facts_as_reported` — el valor tal como se reportó por primera vez
- `v_restatements` — histórico de cambios (dato interesante por sí mismo para el dashboard)

## 8. Rate limiting y buena conducta

| Fuente | Límite | Configuración |
|---|---|---|
| SEC (data.sec.gov, www.sec.gov) | 10 req/s máx | Usar **5 req/s**, `User-Agent` obligatorio con contacto |
| Banxico SIE | ~40,000 consultas/día | Holgado, pero cachear |
| EIA / FRED | Generoso | Cachear |
| BMV | No documentado | 1 req cada 2s, respetar |
| gob.mx / AFAC | No documentado + anti-bot | 1 req cada 3s; probablemente requiera Playwright/computer use |
| BTS TranStats | No documentado | 1 req cada 2s, archivos grandes |
| yfinance | Informal | 1 llamada por ticker por corrida, cachear |

Implementar un decorador `@rate_limited(source)` en `src/common/http.py` que lea estos
límites de `config.py`. Backoff exponencial con jitter ante 429/503, máximo 5 intentos.

## 9. Estrategia de tests

Nivel mínimo por etapa:
1. **Tests de parser con fixtures congelados.** Copiar un archivo bronze real a
   `tests/fixtures/` y assertar las cifras que debe extraer. Estos son los tests que
   realmente protegen el proyecto.
2. **Tests de contrato de esquema.** Cada tabla silver/gold tiene un esquema declarado;
   el test falla si cambia.
3. **Tests de invariantes de negocio.**
   - `0 <= load_factor <= 1`
   - `rpk <= ask` siempre
   - `load_factor ≈ rpk / ask` (tolerancia 0.5 pp)
   - `casm_ex_fuel < casm`
   - suma de pasajeros por segmento = total reportado (tolerancia declarada)
4. **Test de idempotencia.** Correr el pipeline dos veces → mismo conteo de filas.

## 10. Reproducibilidad

- `pyproject.toml` con versiones pinneadas.
- Un comando único que reconstruye todo desde bronze: `python -m src.rebuild`
- Un `Makefile` o `justfile` con targets: `ingest`, `parse`, `transform`, `test`,
  `dashboard`, `rebuild`.
- El pipeline debe poder correr **sin red** partiendo de bronze. Esto es un requisito
  de diseño, no un extra.
