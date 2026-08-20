# Etapa 5 — Peers Competitivos + BTS T-100

**Objetivo:** obtener los datos de las aerolíneas de comparación (Volaris, Viva Aerobus,
Ryanair, Delta, IAG) e incorporar la base BTS T-100, que da granularidad ruta-nivel
independiente para el mercado transfronterizo México–EE.UU.

**Principio rector de esta etapa:** *reutilizar, no reinventar*. Los parsers de la Etapa 1
(EDGAR) y la Etapa 2 (XBRL) deben generalizarse por `carrier_key`, no duplicarse.

---

## 1. Refactor previo (hacerlo primero)

Antes de agregar peers, generalizar:
- `src/ingest/sec/` debe aceptar cualquier CIK, no solo el de Aeroméxico
- `src/parse/sec/earnings_release.py` debe aceptar un **perfil de parseo por aerolínea**
  (`src/parse/profiles/{carrier_key}.yaml`) que defina los patrones de métrica de esa
  compañía, sin tocar el código

Ejemplo de perfil:
```yaml
carrier_key: VOLARIS
cik: "0001520504"
reporting_currency: USD
unit_system: imperial        # usa ASM/RPM
fiscal_year_end_month: 12
metric_patterns:
  load_factor_total: ["load factor", "factor de ocupación"]
  casm_ex_fuel: ["CASM ex fuel", "CASM excluding fuel"]
  trasm: ["TRASM", "total revenue per ASM"]
  ancillary_revenue: ["other passenger revenue", "ancillary"]
```

Esto es lo que hace escalable el proyecto. Sin esto, cada peer es código nuevo.

## 2. Peers, uno por uno

### 2.1 Volaris (VLRS / VOLAR) — el peer más importante

| Atributo | Valor |
|---|---|
| Modelo | ULCC (ultra low cost) |
| Listado | NYSE (ADR) + BMV |
| Régimen SEC | **FPI** → 20-F + 6-K |
| CIK | `0001520504` (**verificar** contra `company_tickers.json`) |
| Norma | IFRS |
| Moneda | USD |
| Unidades | ASM/RPM (imperial) |

**Fuentes:**
1. EDGAR: 20-F y 6-K con comunicados trimestrales (mismo pipeline que Etapa 1)
2. XBRL de BMV (Etapa 2) — emisor continuo, debería tener historia desde ~2016
3. IR propio para reportes de tráfico mensual

**Por qué es el peer clave:** misma jurisdicción, misma norma contable, misma moneda,
compiten directamente en el mercado doméstico mexicano. Es la comparación más limpia
del proyecto y donde el contraste **network vs ULCC** se ve mejor.

**Dato de contexto valioso:** según el IdeaWorksCompany 2025 Yearbook (FY2024), Volaris
obtuvo **55.3%** de sus ingresos totales de fuentes auxiliares (ancillary). Comparar
eso contra Aeroméxico ilustra dos modelos de negocio distintos.

### 2.2 Viva Aerobus — privada pero con reportes públicos

| Atributo | Valor |
|---|---|
| Modelo | ULCC |
| Listado | **No cotiza acciones.** Emisor de deuda (Cebures) en BMV/BIVA |
| Régimen SEC | Ninguno |
| Norma | IFRS |
| Moneda | **USD** (cambió su moneda funcional para cumplir con la CNBV) |

**Fuentes:**
- `https://ri.vivaaerobus.com/es/resultados_trimestrales` — reportes trimestrales PDF
  y un "XBRL Report"
- CDN de reportes: `https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/{año}-{trimestre}-{es|en}.pdf`
  (patrón observado: `2025-4T25-en.pdf`)
- XBRL vía BMV/BIVA como emisor de deuda

**Métricas que publica:** TRASM, EBITDAR, y las operativas estándar.

**Nota de acceso:** el CDN de investorcloud suele ser accesible con `httpx`. Probar ahí
primero antes de complicarse.

### 2.3 Ryanair (RYAAY) — el benchmark ULCC global

| Atributo | Valor |
|---|---|
| Modelo | ULCC |
| Régimen SEC | **FPI** → 20-F |
| Norma | IFRS |
| Moneda | **EUR** |
| **Año fiscal** | **Cierra el 31 de marzo** ← ojo |
| Unidades | ASK/RPK (métrico) |

**Fuentes:**
- EDGAR (20-F, 6-K)
- `https://corporate.ryanair.com/facts-figures/key-stats/`
- `https://investor.ryanair.com/traffic/` — **estadísticas mensuales de tráfico**
  (guests y load factor), muy limpias

**El reto del año fiscal:** Ryanair FY2026 = abril 2025 a marzo 2026. **Nunca** comparar
"FY2026 de Ryanair" con "2026 de Aeroméxico". Toda comparación en el dashboard usa
**periodos calendario**. Por eso el esquema exige `fiscal_period_id` **y**
`calendar_period_id` (ver `01-arquitectura-y-convenciones.md` §4).

Sus datos mensuales de tráfico permiten reconstruir trimestres calendario, lo que
resuelve el problema para las métricas operativas. Para los financieros, la
reconstrucción calendario **no es posible** — hay que declarar la limitación y comparar
solo en base fiscal, con una advertencia visible en el dashboard.

### 2.4 Delta (DAL) — el peer con XBRL rico

| Atributo | Valor |
|---|---|
| Modelo | Network carrier / full service |
| Régimen SEC | **Emisor doméstico** → 10-K + 10-Q |
| Norma | **US-GAAP** |
| Moneda | USD |
| Unidades | ASM/RPM |

**Contraste clave:** el `companyfacts` de Delta **sí está poblado y es rico**. Es el
único peer donde la API de XBRL de la SEC funciona plenamente. Aprovecharlo — y usarlo
en el dashboard como ejemplo didáctico de la diferencia entre regímenes de reporte.

**Relevancia especial:** Delta posee ~20% de Aeroméxico y opera un joint venture con
inmunidad antimonopolio en el mercado transfronterizo. No es solo un peer: es socio.
Eso merece su propia sección narrativa en el dashboard.

### 2.5 IAG (ICAGY) — el más difícil de obtener

| Atributo | Valor |
|---|---|
| Modelo | Grupo de network carriers (BA, Iberia, Vueling, Aer Lingus, LEVEL) |
| Régimen SEC | **Ninguno.** No presenta 20-F. Solo ADR nivel 1 OTC (ICAGY, Deutsche Bank) |
| Cotiza | Londres y bolsas españolas |
| Norma | IFRS |
| Moneda | EUR |

**Fuentes:** solo `iairgroup.com` → annual reports, quarterly reporting, traffic stats.
No hay atajo por EDGAR.

**Evaluación honesta:** IAG es el peer con peor relación esfuerzo/beneficio. Es un grupo
multi-aerolínea, lo que hace la comparación conceptualmente turbia (¿comparar Aeroméxico
contra el grupo entero o contra Iberia sola?). **Recomendación: implementarlo al final
de la etapa, y si el tiempo aprieta, dejarlo fuera del MVP.** Consultar con el usuario.

### 2.6 Peers adicionales opcionales
Si el pipeline generalizado funciona bien, agregar peers es barato. Candidatos naturales
de LatAm (todos FPI ante la SEC): **Copa Holdings (CPA)**, **LATAM (LTM)**, **Gol (GOL)**,
**Azul (AZUL)**. Copa en particular es un excelente comparable: network carrier con hub,
mercado latinoamericano, alta rentabilidad. **Sugerirlo al usuario**, no implementarlo
sin preguntar.

## 3. BTS T-100 — la joya independiente

**Por qué importa:** es la única fuente que da datos de tráfico **verificados por un
regulador**, a nivel **ruta × aerolínea × mes × tipo de avión**, para el mercado
México–EE.UU., que es el mercado más importante de Aeroméxico. Permite hacer análisis
que ninguna otra fuente habilita: participación por ruta, evolución de la red, respuesta
competitiva ruta por ruta, medición del impacto de la Categoría 2 de la FAA.

### La fuente
- **Bureau of Transportation Statistics**, `https://transtats.bts.gov/`
- Bancos relevantes:
  - **28IS — International Segment (All Carriers)**: aerolíneas de EE.UU. y **extranjeras**
    con tráfico hacia/desde EE.UU. Reportado bajo Schedule T-100(f), 14 CFR Part 217.
    **Aeroméxico aparece aquí.**
  - **28IM — International Market**
  - **T-100 Domestic Segment**: solo mercado doméstico de EE.UU.; útil para Delta,
    no para Aeroméxico
  - **DB1B**: muestra 10% de boletos con O&D y tarifas; solo doméstico de EE.UU.
- **Historia**: desde 1990
- **Formato**: CSV descargable (a través de un formulario con checkboxes de columnas)
- **Latencia**: ~2 meses para doméstico; **internacional con más rezago**, y los datos
  internacionales tienen una **restricción de 6 meses** antes de publicarse

### Campos clave de T-100 Segment
```
carrier, carrier_name, carrier_group, unique_carrier_entity,
origin, origin_city_name, origin_country, dest, dest_city_name, dest_country,
aircraft_type, aircraft_config, service_class,
departures_scheduled, departures_performed,
seats, passengers, freight, mail,
ramp_to_ramp_time, air_time, distance,
year, month
```

De aquí se derivan directamente: **ASM = seats × distance**,
**RPM = passengers × distance**, **load factor = passengers / seats**.
Es decir, **T-100 permite reconstruir las métricas de aerolínea desde cero**, de forma
independiente a lo que reporta la compañía. Eso es enormemente valioso para validación.

### Acceso
El formulario de TranStats genera un POST con la selección de columnas. Escalada:
1. Reproducir el POST con `httpx` (inspeccionar la petición del formulario)
2. Playwright para llenar el formulario y disparar la descarga
3. Computer use si hay bloqueo

**Volumen:** los archivos son grandes (cientos de MB por año en algunos bancos).
Descargar solo lo necesario:
- Banco 28IS, filtrando por `origin_country = 'MX'` **o** `dest_country = 'MX'`
- Rango: desde 2015 (suficiente para capturar pre-COVID, COVID, Cat 2, recuperación)
- Verificar espacio en disco antes de empezar

### Salida: `silver/bts_t100_segment.parquet`
Esquema con los campos arriba + `carrier_key` mapeado vía crosswalk + linaje.

### Análisis que habilita (para Etapas 7 y 8)
- Participación de Aeroméxico vs Delta vs United vs American en cada ruta México-EE.UU.
- Evolución de la red: rutas abiertas y cerradas por trimestre
- Impacto medible de la Categoría 2 de la FAA (2021-05 a 2023-09) en la capacidad ofrecida
- Load factor por ruta (más granular que el consolidado de los reportes)
- Tipo de avión por ruta → eficiencia de la asignación de flota

## 4. Normalización entre peers (preparación para Etapa 6)

Esta etapa **produce los insumos**; la normalización se ejecuta en la Etapa 6. Pero aquí
hay que **documentar exhaustivamente** las diferencias encontradas:

`docs/peers-comparabilidad.md` con una matriz:

| Aerolínea | Norma | Moneda | Unidades | FY end | ¿Define yield? | ¿CASM ex-fuel? | ¿Ancillary separado? | Stage length publicado |
|---|---|---|---|---|---|---|---|---|
| Aeroméxico | IFRS | USD | ASM+ASK | Dic | | | | Sí |
| Volaris | IFRS | USD | ASM | Dic | | | | |
| Viva Aerobus | IFRS | USD | ASM | Dic | | | | |
| Ryanair | IFRS | EUR | ASK | **Mar** | | | | |
| Delta | US-GAAP | USD | ASM | Dic | | | | |
| IAG | IFRS | EUR | ASK | Dic | | | | |

Y para cada aerolínea, **la definición literal** que la compañía da de cada métrica,
extraída de sus propios filings. Estas diferencias de definición son la razón principal
por la que las comparaciones de aerolíneas suelen estar mal hechas.

### Diferencias contables a documentar
- **IFRS 16 vs ASC 842** (leasing): afecta EBITDAR, deuda reportada y estructura de
  costos. Delta (US-GAAP) no es directamente comparable con el resto en estas partidas.
- **Mantenimiento**: distintos tratamientos de capitalización.
- **Ingresos por programa de lealtad**: distintos criterios de reconocimiento.

**Recomendación para el dashboard:** privilegiar métricas **unitarias y de margen**
(RASM, CASM, spread, load factor, yield) sobre valores absolutos, porque son más
robustas a las diferencias contables. Y siempre acompañar con la advertencia
correspondiente.

## 5. Validación de la Etapa 5

- Para cada peer: al menos 8 trimestres de métricas operativas extraídas
- Ryanair: los trimestres calendario reconstruidos de datos mensuales cuadran con los
  fiscales reportados (±1%)
- Delta: las cifras del `companyfacts` XBRL cuadran con las del 10-Q parseado (±0.1%)
- **BTS T-100 vs reportes de Aeroméxico**: los ASM de Aeroméxico en rutas EE.UU. según
  T-100 deben ser una fracción coherente y estable de sus ASM internacionales totales
  reportados. Calcular esa proporción por trimestre y verificar que sea estable.
  Si oscila violentamente, hay un error de parseo o de mapeo de carrier.
- Todos los `carrier` de T-100 relevantes están mapeados en el crosswalk

---

## Entregables de la Etapa 5

1. Refactor: pipeline SEC generalizado por `carrier_key` + perfiles YAML
2. `src/ingest/peers/`, `src/ingest/bts/t100.py`
3. `silver/sec_operating_metrics.parquet` extendido con todos los peers
4. `silver/peer_financials.parquet`
5. `silver/bts_t100_segment.parquet`
6. `docs/peers-comparabilidad.md` — la matriz + definiciones literales por aerolínea
7. `carrier_crosswalk.csv` con todos los códigos de T-100 mapeados
8. Reporte de validación T-100 vs reportes de la compañía
9. `docs/etapas/etapa-5-reporte.md` con recomendación explícita sobre si incluir IAG
   y si vale agregar Copa/LATAM/Gol/Azul

**Detenerse y esperar "go".**
