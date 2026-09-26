# 00 — Contexto y Principios

## 1. Qué se está construyendo

Un sistema end-to-end que:

1. **Extrae** información pública de Aeroméxico y su entorno competitivo desde múltiples
   fuentes heterogéneas (APIs, XBRL, PDFs, Excel de gobierno, CSVs, web).
2. **Normaliza y consolida** todo en un conjunto de **tablas maestras** con esquema
   estable, comparables entre aerolíneas y a través del tiempo.
3. **Analiza**: forecast de métricas clave, clustering de trimestres/rutas/aerolíneas,
   análisis del lenguaje de los reportes trimestrales, detección de anomalías.
4. **Presenta**: un dashboard interactivo con **narrativa de negocio**, donde cada KPI
   viene acompañado de su interpretación (qué significa que suba o baje, y por qué
   le importa al negocio).

## 2. Por qué existe

El usuario es analista de datos y quiere un proyecto de portafolio que demuestre
capacidad end-to-end: ingesta difícil (fuentes sucias y protegidas), modelado de datos
serio, analítica no trivial y comunicación de negocio. **El valor diferenciador está
en la narrativa de negocio y en la calidad del pipeline, no en la cantidad de gráficas.**

## 3. Contexto del sujeto de análisis

### Grupo Aeroméxico — situación actual

- **Ticker**: AERO. Cotiza simultáneamente en **NYSE** (ADS) y **BMV** desde el
  **6 de noviembre de 2025**. Cada ADS = 10 acciones ordinarias.
- **CIK EDGAR**: `1561861`. Commission File Number `001-42931`. SIC 4512.
- **Cierre fiscal**: 31 de diciembre.
- **Régimen de reporte**: **foreign private issuer (FPI)** → presenta **20-F** anual
  y **6-K** para información intermedia. **NO presenta 10-Q ni 10-K.**
- **Norma contable**: IFRS. **Moneda de reporte: USD.**
- **Accionistas relevantes**: Delta Air Lines ~20% (lock-up 4 años, no vendió en el IPO);
  Apollo Global Management pasó de 22.4% a ~19.1%.
- **Historia reciente**: Capítulo 11 en EE.UU. (2020-2022), delisting de BMV en 2022,
  relisting con IPO dual en noviembre de 2025. Esto significa que **las series históricas
  largas de datos financieros son limitadas** — un motivo más para depender de AFAC,
  BTS y grupos aeroportuarios para profundidad histórica.
- **Modelo de negocio**: network carrier / full service, hub en MEX (AICM), único
  operador mexicano de largo alcance con widebody, joint venture con inmunidad
  antimonopolio con Delta en el mercado transfronterizo México-EE.UU.
- **Marcas**: Aeroméxico (mainline), Aeroméxico Connect (regional), Aeroméxico Contigo.

### Contexto regulatorio material

- FAA degradó a México a **Categoría 2 el 25 de mayo de 2021**.
- FAA restauró **Categoría 1 el 14 de septiembre de 2023** (~28 meses en Cat 2),
  permitiendo nuevas rutas y codeshares a EE.UU.
- **Riesgo vigente**: en octubre de 2025 el DOT de EE.UU. revocó 13 rutas y en agosto
  de 2026 hubo una nueva auditoría IASA con la Categoría 1 potencialmente en riesgo.
  → **El agente debe verificar el estatus actual durante la Etapa 4** y modelarlo como
  variable de contexto/riesgo en el dashboard, no como dato consumado.

### Cifras ancla conocidas (para validar el pipeline)

Del comunicado 1Q26 (publicado ~21 de abril de 2026):

| Métrica | Valor 1Q26 |
|---|---|
| Ingreso total | 1,341 mdd (+13.3% YoY) |
| EBITDAR ajustado | 335.8 mdd (margen 25.0%) |
| Utilidad operativa | 141.8 mdd (margen 10.6%) |
| CASM ex-fuel | 10.2 ¢ |
| TRASM | 15.6 ¢ |
| ASMs | -1.2% YoY |
| Factor de ocupación | 84.4% (vs 82.3% en 1Q25) |
| Flota | 166 aviones |
| Pasajeros | ~5.8 millones |

Otro ancla: `dei:EntityCommonStockSharesOutstanding` = **1,459,034,090** al 2025-12-31
(del 20-F FY2025, único dato presente en el `companyfacts` de la SEC).

> **Importante:** estas cifras vienen de una investigación previa y pueden haber sido
> reexpresadas. Sirven como *smoke test*: si el parser saca 84.4% de load factor para
> 1Q26, el parser funciona. Si saca algo muy distinto, hay que investigar — no ajustar.

## 4. Hallazgo crítico que define la arquitectura

**El endpoint `companyfacts` de la SEC para Aeroméxico está prácticamente vacío.**
Solo devuelve el bloque `dei` con acciones en circulación. No hay `us-gaap` ni
`ifrs-full` poblados, porque:

- Los 6-K (donde vienen los resultados trimestrales) se "furnish" **sin XBRL financiero**.
- El XBRL del 20-F aún no aparece agregado en el endpoint.

**Consecuencia:** la arquitectura **no puede depender del XBRL de la SEC**. La estrategia
correcta es híbrida:

| Necesidad | Fuente correcta |
|---|---|
| Métricas operativas (ASK, RPK, load factor, RASM, CASM, flota, pax) | **Comunicado de resultados** (exhibit 99.1 del 6-K / PDF de IR) — única fuente |
| Estados financieros estructurados y trazables | **XBRL de la BMV** (portal gratuito) |
| Descubrimiento y descarga automática de filings | **API `submissions` de la SEC** |
| Validación independiente de tráfico | **BTS T-100**, **AFAC**, grupos aeroportuarios |

El agente debe verificar por sí mismo el estado del `companyfacts` en la Etapa 1 —
si para entonces ya está poblado, eso cambia la estrategia para mejor y debe reportarse.

## 5. Principios de trabajo

### 5.1 Completitud sobre velocidad
El usuario lo dijo explícitamente. No se optimiza por "terminar rápido". Se optimiza
por "cuando esto termine, funciona y está documentado".

### 5.2 Inmutabilidad de la capa cruda
Todo lo descargado se guarda tal cual, con timestamp y hash, y **nunca se modifica**.
Si un parser falla, se corrige el parser y se reprocesa desde bronze; jamás se re-descarga
"para arreglar" ni se edita un archivo bronze a mano.

### 5.3 Idempotencia
Correr un script dos veces con los mismos insumos produce el mismo resultado y no
duplica registros. Toda carga usa claves naturales y upsert.

### 5.4 Trazabilidad total
Cada fila de la capa gold debe poder rastrearse hasta el archivo bronze del que salió,
vía columnas `source_system`, `source_file`, `source_hash`, `ingested_at`.

### 5.5 Fallar ruidosamente
Si un parser encuentra un formato inesperado, **falla con un error claro**. No devuelve
`None`, no rellena con ceros, no adivina. Los datos silenciosamente incorrectos son
peores que la ausencia de datos.

### 5.6 Nada de datos inventados
Prohibido: estimar cifras faltantes sin marcarlas, interpolar sin declararlo,
"redondear" para que cuadre con un ancla. Si algo no se pudo obtener, la columna es
`NULL` y hay una fila en el log de calidad de datos.

### 5.7 Legalidad y buena ciudadanía
- Respetar `robots.txt` y términos de servicio.
- Rate limiting estricto (SEC: máx 10 req/s; en la práctica usar 5 req/s).
- `User-Agent` descriptivo con contacto real en toda petición a la SEC.
- **Prohibido** el scraping de reseñas de usuarios (Skytrax, TripAdvisor, redes sociales):
  riesgo legal y de ToS. El análisis de sentimiento se limita a titulares vía RSS/GDELT.
- Computer use se usa para acceder a información pública que un humano vería en su
  navegador, no para evadir autenticación ni paywalls.

### 5.8 Autorización antes de instalar
El agente **pregunta antes** de instalar cualquier cosa. Formato de la pregunta:
> "Necesito instalar X porque Y. El comando sería `Z`. ¿Autorizas?"

### 5.9 Documentar los "no"
Las cosas que se intentaron y no funcionaron son tan valiosas como las que sí. Cada
reporte de etapa incluye una sección "Qué no funcionó y por qué".

## 6. Alcance explícito: qué NO se hace

- No se compran datos. Solo fuentes gratuitas y abiertas.
- No se usa Highcharts (licencia gratuita solo para uso personal/no comercial, y el
  EULA 2025 endureció las definiciones; se usa ECharts/Plotly para evitar ambigüedad).
- No se scrapea reseñas de usuarios ni redes sociales.
- No se construye infraestructura de streaming ni orquestación pesada: la cadencia real
  es trimestral/mensual, GitHub Actions con cron es suficiente.
- No se hace trading ni recomendaciones de inversión. Es un dashboard analítico.
