# Etapa 1 — SEC EDGAR + Comunicados Trimestrales de Aeroméxico

**Esta es la etapa más importante del proyecto.** Es la fuente de todas las métricas
operativas de aerolínea (ASK, RPK, load factor, RASM, CASM, flota, pasajeros), que no
existen en ningún otro lado en forma estructurada. Debe quedar impecable.

**Objetivo:** un pipeline que descubre, descarga, versiona y parsea todos los filings
de Aeroméxico ante la SEC, produciendo tablas silver con métricas financieras y
operativas trimestrales.

---

## 1. Entendiendo la fuente

### 1.1 Régimen de reporte de Aeroméxico
- Es **foreign private issuer**: presenta **20-F** (anual) y **6-K** (intermedio).
- **No hay 10-Q.** Los resultados trimestrales van como **exhibit 99.1 de un 6-K**.
- Los reportes de tráfico mensual también se presentan vía 6-K.
- Contabilidad IFRS, moneda de reporte **USD**.

### 1.2 El problema del XBRL
`https://data.sec.gov/api/xbrl/companyfacts/CIK0001561861.json` devuelve prácticamente
solo `dei:EntityCommonStockSharesOutstanding`. **No hay us-gaap ni ifrs-full poblados.**

**Primera tarea de la etapa:** verificar si esto sigue siendo cierto.
```bash
curl -H "User-Agent: $SEC_USER_AGENT" \
  https://data.sec.gov/api/xbrl/companyfacts/CIK0001561861.json | jq 'keys, .facts | keys'
```
- Si sigue vacío → seguir el plan tal cual (parseo de documentos).
- Si ahora tiene `ifrs-full` poblado → **reportarlo al usuario inmediatamente**, porque
  cambia la estrategia: el XBRL de la SEC pasaría a ser fuente primaria de financieros
  y la Etapa 2 (BMV) se vuelve redundancia/validación en lugar de fuente principal.

## 2. APIs de la SEC — referencia técnica

### Endpoints
| Endpoint | Uso |
|---|---|
| `https://data.sec.gov/submissions/CIK##########.json` | **Catálogo de todos los filings.** Base del descubrimiento. |
| `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | Todos los hechos XBRL (vacío para AERO) |
| `https://data.sec.gov/api/xbrl/companyconcept/CIK########/{taxonomy}/{tag}.json` | Serie de un concepto |
| `https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/CY####Q#.json` | Un concepto, todas las empresas |
| `https://www.sec.gov/Archives/edgar/data/{cik_sin_ceros}/{accession_sin_guiones}/` | Directorio de documentos de un filing |
| `https://efts.sec.gov/LATEST/search-index?q=...&forms=...` | Full-text search |
| `https://www.sec.gov/files/company_tickers.json` | Mapeo ticker → CIK (para peers) |

### Reglas de acceso
- **Sin API key.**
- **`User-Agent` obligatorio** y descriptivo con contacto real. Sin él → 403.
- Máximo **10 req/s por IP**. Usar 5 req/s. Exceder → 429 y bloqueo temporal (~10 min).
- Sin límites diarios.
- Existe `companyfacts.zip` masivo actualizado cada noche (~3 a.m. ET) si alguna vez
  se necesita bulk.

### Formato de `submissions`
```json
{
  "cik": "1561861",
  "name": "Grupo Aeromexico, S.A.B. de C.V.",
  "tickers": ["AERO"],
  "filings": {
    "recent": {
      "accessionNumber": [...], "filingDate": [...], "form": [...],
      "primaryDocument": [...], "items": [...], "reportDate": [...]
    },
    "files": [ /* archivos adicionales si hay más de 1000 filings */ ]
  }
}
```
Es **columnar**: arrays paralelos. Hay que zippearlos en filas.

## 3. Sub-etapa 1A — Descubrimiento de filings

**Módulo:** `src/ingest/sec/discover.py`

1. Descargar `submissions/CIK0001561861.json` → bronze.
2. Si `filings.files` no está vacío, descargar también esos archivos y concatenar
   (paginación histórica).
3. Normalizar a una tabla `silver/sec_filings_index.parquet`:

```
cik, company_name, carrier_key, accession_number, form_type,
filing_date, report_date, primary_document, primary_doc_url,
filing_index_url, items, is_downloaded, document_count
```

4. Clasificar cada 6-K por **tipo de contenido** (crítico, porque hay 6-K de resultados,
   de tráfico mensual, de gobierno corporativo, de hechos relevantes):
   - Descargar el documento principal del 6-K (es corto, típicamente 1-2 páginas)
   - Clasificar por keywords en el texto y en el nombre de los exhibits:
     - `earnings` — "results", "resultados", "fourth quarter", "EBITDAR"
     - `traffic` — "traffic", "tráfico", "monthly", "passengers carried"
     - `governance` — "shareholders meeting", "asamblea", "board"
     - `material_event` — resto
   - Guardar la clasificación con su nivel de confianza; los `unknown` se listan para
     revisión manual del usuario.

**Entregable parcial:** una tabla que responda "¿qué filings existen y de qué tipo son?"

## 4. Sub-etapa 1B — Descarga de documentos

**Módulo:** `src/ingest/sec/download.py`

Para cada filing relevante (`20-F`, `6-K` de tipo `earnings` o `traffic`, y `F-1`/`F-1/A`
del IPO que contienen datos históricos valiosos):

1. Obtener el índice del filing:
   `https://www.sec.gov/Archives/edgar/data/1561861/{accession_no_dashes}/index.json`
2. Descargar **todos** los documentos del filing (HTML, PDF, XML, gráficos no).
   Los comunicados suelen estar como `ex-99_1.htm` o `d######dex991.htm`.
3. Guardar en `data/bronze/sec/filings/{accession_number}/` con su `.meta.json`.

**Atención al F-1/A del IPO** (`d11281df1a.htm` y similares, de 2025): contiene el
prospecto completo con series históricas de métricas operativas, definiciones de KPIs
de la propia compañía, y la fórmula de ajuste por stage length. **Es oro.** Descargarlo
y tratarlo como documento de referencia (ver sub-etapa 1E).

### Si `www.sec.gov` bloquea la descarga
Los `Archives` a veces devuelven 403 con clientes automatizados aunque `data.sec.gov`
funcione. Escalada:
1. Verificar `User-Agent` y agregar `Accept-Encoding: gzip, deflate`
2. Bajar el rate a 2 req/s
3. Playwright headless
4. Computer use (ver archivo 12)

## 5. Sub-etapa 1C — Parseo del comunicado de resultados (EL CORAZÓN)

**Módulo:** `src/parse/sec/earnings_release.py`

Los comunicados de resultados de Aeroméxico contienen tablas con:

**Financieras:**
- Total revenue / Ingreso total
- Passenger revenue, Cargo revenue, Other revenue
- Operating expenses (desglosado: fuel, salarios, mantenimiento, aeroportuarios, etc.)
- Operating income y margen
- EBITDAR ajustado y margen
- Net income
- Reconciliaciones no-IFRS (típicamente en un "Annex A")

**Operativas:**
- ASMs / ASKs (capacidad) — doméstico, internacional, total
- RPMs / RPKs (demanda) — doméstico, internacional, total
- Load factor — doméstico, internacional, total
- TRASM, PRASM, RASM
- CASM, CASM ex-fuel
- Yield
- Pasajeros transportados
- Flota (número de aviones, por tipo si está disponible)
- Average stage length
- Utilización de flota (block hours)
- Puntualidad (OTP) si aparece
- Destinos / rutas

### Estrategia de parseo (en orden de preferencia)

1. **Si el exhibit es HTML** (lo más común en EDGAR): parsear con `BeautifulSoup` +
   `pandas.read_html`. Es mucho más confiable que PDF. **Preferir siempre el HTML de
   EDGAR sobre el PDF de la página de IR.**
2. **Si solo hay PDF**: `pdfplumber.extract_tables()` con configuración de estrategia
   de líneas; fallback a `camelot` (flavor `lattice` y `stream`).
3. **Fallback final**: extracción por regex sobre el texto plano, con patrones anclados
   a los nombres de las métricas.

### Diseño del parser — requisito clave: robustez ante cambios de formato

**No hardcodear posiciones de celda.** Diseñar así:

```python
METRIC_PATTERNS = {
    "load_factor_total": [
        r"load\s+factor",
        r"factor\s+de\s+ocupaci[óo]n",
    ],
    "casm_ex_fuel": [
        r"CASM\s*[-–]?\s*ex[\s-]*fuel",
        r"CASM\s+excluding\s+fuel",
    ],
    # ...
}
```

El parser:
1. Localiza la fila por patrón de nombre (regex, case-insensitive, tolerante a acentos).
2. Identifica las columnas de periodo leyendo los encabezados (`1Q26`, `Q1 2026`,
   `1T26`, `Three months ended March 31, 2026`).
3. Extrae el valor, **detecta su unidad y escala** (millones vs miles, ¢ vs USD,
   % vs fracción, km vs millas).
4. Emite una fila larga por métrica-periodo, no una tabla ancha.

### Detección de unidades — regla crítica

Aeroméxico usa **ambos sistemas**: define ASK/RPK en métrico pero reporta CASM/RASM en
centavos por ASM (millas). El parser **debe** capturar la unidad literal del documento
y guardarla, nunca asumirla.

```
metric_key, value_raw, unit_raw, scale_raw, value_normalized, unit_normalized
```
La normalización (km ↔ millas) se hace en **gold**, no en silver. Silver preserva
lo que dijo la fuente. Factor: `1 milla = 1.609344 km`.

Si el parser no puede determinar la unidad → `log_issue(issue_type="unit_ambiguity")`
y `value_normalized = NULL`. **Nunca adivinar.**

### Esquema de salida: `silver/sec_operating_metrics.parquet`

```
carrier_key            str    # 'AEROMEXICO'
accession_number       str
period_id              str    # '2026Q1'
period_type            str    # 'quarter' | 'month' | 'year'
period_start_date      date
period_end_date        date
metric_key             str    # 'load_factor_total', 'casm_ex_fuel', ...
segment                str    # 'total' | 'domestic' | 'international' | NULL
value_raw              float
unit_raw               str    # tal como aparece: '¢', '%', 'US$ millions', 'ASMs (000s)'
scale_multiplier       float  # 1, 1e3, 1e6
value_normalized       float
unit_normalized        str    # 'usd', 'usd_cents', 'fraction', 'km', 'miles', 'count'
is_preliminary         bool
is_yoy_comparison      bool   # si la celda es un % de variación, no un nivel
extraction_method      str    # 'html_table' | 'pdf_table' | 'regex_text'
extraction_confidence  float  # 0-1
source_system, source_file, source_hash, ingested_at, parser_version
```

### Esquema de salida: `silver/sec_financials.parquet`
Misma forma, con `metric_key` de línea de P&L y `statement_type`
(`income_statement` | `balance_sheet` | `cash_flow` | `non_ifrs`).

## 6. Sub-etapa 1D — Parseo de reportes de tráfico mensual

**Módulo:** `src/parse/sec/traffic_report.py`

Los 6-K de tráfico mensual traen pasajeros, ASK, RPK y load factor mensuales.
Mismo enfoque, `period_type = 'month'`. Estos son valiosos porque dan **granularidad
mensual** cuando los financieros son trimestrales, y permiten cruzar con AFAC.

## 7. Sub-etapa 1E — Extracción de definiciones y contexto (el F-1 y el 20-F)

**Módulo:** `src/parse/sec/definitions.py`

Del F-1/A del IPO y del 20-F, extraer y guardar como **documentos de referencia**
(no como datos numéricos):

1. **Definiciones oficiales de KPIs de la compañía.** Aeroméxico define sus propias
   métricas en el prospecto. Estas definiciones deben alimentar el glosario del
   dashboard, porque son la interpretación autorizada.
2. **La fórmula de ajuste por stage length**, que la compañía publica:
   ```
   SLA RASK = RASK × (stage_length_carrier / 1834)^0.5
   ```
   donde 1,834 km es la etapa de referencia usada por la compañía.
   **Esta fórmula es esencial para la Etapa 6** (comparabilidad entre peers).
3. **Series históricas** de métricas operativas que aparecen en el prospecto (dan
   profundidad pre-IPO que no existe en los 6-K).
4. **Factores de riesgo** — texto que alimenta el análisis cualitativo de la Etapa 7.
5. **Descripción de flota, red y hubs** — insumo de dimensiones.

Guardar en `data/bronze/sec/reference/` y extraer texto a
`silver/sec_reference_text.parquet` con `document_type`, `section`, `text`.

## 8. Sub-etapa 1F — Texto completo de reportes para NLP (Etapa 7)

Extraer el **texto completo** de cada comunicado de resultados a
`silver/sec_report_text.parquet`:

```
carrier_key, accession_number, period_id, section,
text, word_count, extracted_at
```

Secciones a intentar separar: carta del CEO / mensaje directivo, resumen financiero,
comentario operativo, outlook/guidance, factores de riesgo.

Esto habilita el análisis de lenguaje que el usuario pidió: cómo cambia el tono y el
vocabulario de la administración trimestre a trimestre.

## 9. Sub-etapa 1G — Validación cruzada API vs documento

El usuario pidió explícitamente comparar la información extraída del API contra la
del PDF. Implementar `src/parse/sec/crosscheck.py`:

1. Para cada métrica presente **tanto** en el XBRL (si aparece algo) **como** en el
   documento parseado, comparar valores.
2. Para métricas presentes en dos documentos distintos (ej. una cifra de 1Q26 aparece
   en el comunicado 1Q26 y como comparativo en el comunicado 1Q27), comparar y
   **detectar restatements**.
3. Emitir `silver/sec_crosscheck.parquet`:
   ```
   metric_key, period_id, source_a, value_a, source_b, value_b,
   abs_diff, pct_diff, is_material (>1%), flagged_at
   ```
4. Toda discrepancia material → `log_issue(issue_type="restatement" | "source_conflict")`.

**Este cruce es un entregable de valor por sí mismo** y debe tener su propia vista en
el dashboard: "coherencia entre fuentes".

## 10. Validación de la Etapa 1

### Cifras ancla (1Q26)
El pipeline debe extraer, para `period_id = '2026Q1'`, `carrier_key = 'AEROMEXICO'`:

| metric_key | valor esperado | tolerancia |
|---|---|---|
| `total_revenue` | 1,341 M USD | ±1% |
| `ebitdar_adjusted` | 335.8 M USD | ±1% |
| `ebitdar_margin` | 0.250 | ±0.5 pp |
| `operating_income` | 141.8 M USD | ±1% |
| `operating_margin` | 0.106 | ±0.5 pp |
| `casm_ex_fuel` | 10.2 ¢/ASM | ±1% |
| `trasm` | 15.6 ¢/ASM | ±1% |
| `load_factor_total` | 0.844 | ±0.5 pp |
| `fleet_size` | 166 | exacto |
| `passengers` | ~5.8 M | ±2% |

Y para 1Q25: `load_factor_total = 0.823`.

### Invariantes
- `rpk <= ask` en todos los periodos
- `load_factor ≈ rpk/ask` (±0.5 pp)
- `casm_ex_fuel < casm`
- `trasm > 0`, `casm > 0`
- No hay huecos en la serie trimestral desde el primer trimestre reportado

### Tests obligatorios
Congelar en `tests/fixtures/sec/` el exhibit 99.1 de al menos **tres** trimestres
distintos (idealmente de años distintos, para capturar cambios de formato) y assertar
las cifras arriba. **Sin estos tests la etapa no se cierra.**

## 11. Riesgos conocidos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Formato del comunicado cambia entre trimestres | Parser basado en patrones, no en posiciones; tests con múltiples trimestres |
| Historia corta (relisting nov-2025) | Complementar con el F-1 del IPO, que trae series pre-IPO |
| 403 de `www.sec.gov/Archives` | Escalada: headers → rate down → Playwright → computer use |
| Confusión ASM/ASK en el mismo documento | Capturar unidad literal obligatoriamente; `unit_ambiguity` si no se determina |
| El comunicado presenta % de variación en vez de niveles | Columna `is_yoy_comparison`; no mezclar niveles con variaciones |
| Métricas no-IFRS sin definición estable | Extraer la definición del Annex A junto con el número |

---

## Entregables de la Etapa 1

1. `src/ingest/sec/{discover,download}.py` funcionando
2. `src/parse/sec/{earnings_release,traffic_report,definitions,crosscheck}.py`
3. `silver/sec_filings_index.parquet`
4. `silver/sec_operating_metrics.parquet`
5. `silver/sec_financials.parquet`
6. `silver/sec_report_text.parquet`
7. `silver/sec_reference_text.parquet`
8. `silver/sec_crosscheck.parquet`
9. Fixtures y tests de parser (mínimo 3 trimestres) en verde
10. `docs/etapas/etapa-1-reporte.md` con: cuántos filings, qué periodos cubiertos,
    qué métricas se lograron extraer y con qué cobertura (% de periodos con dato),
    qué no se pudo extraer y por qué
11. Un notebook o script que imprima la serie de load factor, TRASM y CASM ex-fuel
    trimestre a trimestre, para inspección visual del usuario

**Detenerse y esperar "go".**
