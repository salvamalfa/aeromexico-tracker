# Etapa 0 — Setup

**Objetivo:** dejar un entorno reproducible, el esqueleto del repositorio, y todas las
autorizaciones de instalación resueltas, antes de tocar una sola fuente de datos.

**Criterio de éxito:** el usuario puede clonar el repo en otra máquina, correr un comando
y tener el entorno listo. Los tests pasan (aunque todavía no haya datos).

---

## Paso 0.1 — Inventario de la máquina

Antes de instalar nada, el agente inspecciona qué hay:

```bash
python3 --version
pip --version
which uv
node --version
git --version
df -h .                    # espacio en disco disponible
python3 -c "import duckdb" 2>&1
python3 -c "import polars" 2>&1
python3 -c "import playwright" 2>&1
```

Reportar al usuario:
- Versión de Python disponible
- Qué ya está instalado
- Espacio en disco (el proyecto puede llegar a varios GB por BTS T-100)
- Sistema operativo

## Paso 0.2 — Solicitud de autorizaciones (BLOQUEANTE)

El agente presenta una **única lista consolidada** de lo que necesita instalar, con
justificación por ítem, y espera aprobación. Formato:

```
Necesito instalar lo siguiente. ¿Autorizas? (puedes aprobar todo o ítem por ítem)

GESTOR DE ENTORNO
  [ ] uv — gestor de paquetes rápido y reproducible
      Alternativa si prefieres: venv + pip (más lento pero sin instalar nada nuevo)
      Comando: curl -LsSf https://astral.sh/uv/install.sh | sh

CORE DE DATOS
  [ ] duckdb        — motor analítico embebido, es el warehouse del proyecto
  [ ] polars        — dataframes
  [ ] pyarrow       — lectura/escritura Parquet
  [ ] pandas        — compatibilidad con librerías que lo requieren

INGESTA
  [ ] httpx         — cliente HTTP con retry
  [ ] tenacity      — backoff exponencial
  [ ] beautifulsoup4 + lxml — parseo HTML de EDGAR
  [ ] pdfplumber    — extracción de tablas de los comunicados en PDF
  [ ] pypdf         — texto y metadata de PDF
  [ ] openpyxl      — Excel moderno (AFAC, IR de peers)
  [ ] xlrd          — Excel .xls legado (AFAC años viejos)
  [ ] yfinance      — precios de AERO y peers

NAVEGADOR (para fuentes con anti-bot: AFAC/gob.mx, BMV)
  [ ] playwright + chromium
      Comando extra: playwright install chromium
      Descarga ~150 MB de navegador

CALIDAD Y TESTS
  [ ] pytest
  [ ] pandera       — contratos de esquema

ANALÍTICA (se puede diferir a Etapa 7 si prefieres)
  [ ] statsmodels, scikit-learn, prophet (o statsforecast)
  [ ] spacy + modelo es_core_news_sm (NLP de reportes)

DASHBOARD (se puede diferir a Etapa 8)
  [ ] streamlit
  [ ] streamlit-echarts
  [ ] plotly
```

**El agente NO instala nada hasta recibir el sí.** Si el usuario aprueba parcialmente,
el agente ajusta el plan y lo dice.

> Nota: se recomienda diferir analítica y dashboard a sus etapas para no cargar el
> entorno con dependencias que no se usan todavía. Pero conviene preguntar todo de una
> vez para no interrumpir al usuario cinco veces.

## Paso 0.3 — Crear la estructura del repositorio

Crear exactamente el árbol de `01-arquitectura-y-convenciones.md` sección 3.
Cada directorio de `src/` lleva su `__init__.py`.

Crear también:

**`.gitignore`**
```
.env
__pycache__/
*.pyc
.venv/
data/bronze/
data/silver/
data/gold/
data/*.duckdb
data/*.duckdb.wal
.pytest_cache/
.ipynb_checkpoints/
```

> **Decisión a consultar con el usuario:** ¿bronze se versiona en git o no?
> Recomendación: **no** (puede pesar GB). Alternativa: versionar solo los fixtures
> de test y un `bronze/_manifest.jsonl` con hashes y URLs, de modo que el bronze sea
> reconstruible. Presentar esta opción y dejar que el usuario decida.

**`.env.example`**
```bash
# Obligatorio: la SEC exige User-Agent identificable con contacto real
SEC_USER_AGENT="AeroMexico Dashboard tu-correo@ejemplo.com"

# Token gratuito: https://www.banxico.org.mx/SieAPIRest/service/v1/token
BANXICO_TOKEN=""

# Opcional (alternativa: usar FRED)
EIA_API_KEY=""
FRED_API_KEY=""
```

**`pyproject.toml`** con dependencias pinneadas y grupos opcionales
(`[project.optional-dependencies]` para `analytics` y `dashboard`).

**`justfile`** (o `Makefile`) con targets:
```
setup      # instala deps y playwright
ingest     # corre toda la ingesta
parse      # bronze -> silver
transform  # silver -> gold
test       # pytest
rebuild    # parse + transform desde bronze, sin red
dashboard  # levanta streamlit
```

## Paso 0.4 — Módulos comunes

Implementar y testear (con tests reales, no placeholders):

### `src/config.py`
```python
# Constantes del proyecto. Nada de magic strings dispersos.
CIK_AEROMEXICO = "0001561861"
TICKER_AEROMEXICO = "AERO"

CARRIERS = {
    "AEROMEXICO":   {"iata": "AM",  "icao": "AMX", "cik": "0001561861", "ticker": "AERO"},
    "VOLARIS":      {"iata": "Y4",  "icao": "VOI", "cik": "0001520504", "ticker": "VLRS"},
    "VIVA_AEROBUS": {"iata": "VB",  "icao": "VIV", "cik": None,          "ticker": None},
    "RYANAIR":      {"iata": "FR",  "icao": "RYR", "cik": None,          "ticker": "RYAAY"},
    "DELTA":        {"iata": "DL",  "icao": "DAL", "cik": None,          "ticker": "DAL"},
    "IAG":          {"iata": None,  "icao": None,  "cik": None,          "ticker": "ICAGY"},
}
# NOTA: los CIK de peers marcados como None deben resolverse en la Etapa 5
# usando la API de company_tickers de la SEC. No hardcodear a ciegas.

RATE_LIMITS = {"sec": 5.0, "bmv": 0.5, "afac": 0.33, "bts": 0.5, ...}
```

> El agente debe **verificar** cada CIK contra
> `https://www.sec.gov/files/company_tickers.json` antes de darlos por buenos.
> Los valores arriba son punto de partida, no verdad.

### `src/common/http.py`
Cliente `httpx` con:
- `User-Agent` desde env (falla ruidosamente si no está definido para llamadas a la SEC)
- Rate limiting por fuente (token bucket)
- Retry con backoff exponencial + jitter (tenacity), máx 5 intentos, sobre 429/500/502/503/504
- Timeout de 60s
- Logging estructurado de cada request

### `src/common/storage.py`
```python
def save_bronze(content: bytes, source_system: str, entity: str,
                period: str, ext: str, source_url: str,
                download_method: str, notes: str = "") -> Path:
    """
    - Calcula sha256
    - Si ya existe un archivo con ese hash, NO reescribe, devuelve la ruta existente
    - Si existe el mismo nombre lógico con distinto hash -> versiona (_v2, _v3)
      y registra en _restatements.jsonl
    - Escribe el .meta.json hermano
    """
```

### `src/common/quality.py`
```python
def log_issue(layer, table_name, source_file, severity,
              issue_type, description, affected_rows=None): ...
```
Escribe append-only a `data/quality/issues.jsonl`.

### `src/common/logging.py`
Configuración de logging estructurado JSON a `logs/` + consola legible.

## Paso 0.5 — Smoke test de conectividad

Un script `src/smoke_test.py` que verifica acceso a cada fuente **sin descargar nada
pesado**, y reporta una tabla:

| Fuente | URL de prueba | ¿Accesible con httpx? | ¿Requiere Playwright? | ¿Requiere computer use? |
|---|---|---|---|---|
| SEC submissions | `https://data.sec.gov/submissions/CIK0001561861.json` | | | |
| SEC companyfacts | `https://data.sec.gov/api/xbrl/companyfacts/CIK0001561861.json` | | | |
| Aeroméxico IR | `https://ir.aeromexico.com/financial-information/quarterly-results` | | | |
| BMV XBRL | `https://www.bmv.com.mx/es/emisoras/archivos-estadar-xbrl` | | | |
| AFAC estadística | `https://www.gob.mx/afac/acciones-y-programas/estadistica-mensual-por-aerolinea-monthly-airline-statistics` | | | |
| BTS TranStats | `https://transtats.bts.gov/` | | | |
| Banxico SIE | endpoint de token | | | |
| EIA / FRED | endpoint de serie | | | |

**Este resultado es un entregable de la Etapa 0** y determina dónde se necesitará
computer use en etapas posteriores. Guardarlo en `docs/etapas/etapa-0-conectividad.md`.

Expectativa según la investigación previa: **gob.mx/AFAC bloqueará httpx** (anti-bot).
Si eso se confirma, queda documentado desde el día uno.

## Paso 0.6 — README del proyecto

Escribir el `README.md` raíz del repo: qué es, cómo instalar, cómo correr, estructura
de carpetas, estado actual (Etapa 0 completada).

---

## Entregables de la Etapa 0

1. Repo con estructura completa y `__init__.py` en su lugar
2. `pyproject.toml` con deps instaladas y pinneadas
3. `.env.example` + `.env` local configurado (usuario provee su correo para el User-Agent)
4. `src/config.py`, `src/common/{http,storage,quality,logging}.py` implementados
5. Tests de los módulos comunes pasando (`pytest` verde)
6. `docs/etapas/etapa-0-conectividad.md` con la matriz de accesibilidad
7. `docs/etapas/etapa-0-reporte.md`
8. `justfile` funcional
9. Commit inicial en git

## Validación antes de cerrar

```bash
just test                              # verde
python -m src.smoke_test               # matriz completa, sin excepciones no manejadas
python -c "import duckdb; duckdb.connect('data/warehouse.duckdb')"   # ok
git log --oneline                      # al menos un commit
```

**Detenerse y esperar "go".**
