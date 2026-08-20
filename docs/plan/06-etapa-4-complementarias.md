# Etapa 4 — Fuentes Complementarias

**Objetivo:** incorporar las variables de contexto que explican y contextualizan el
desempeño de Aeroméxico: tipo de cambio, precio del combustible, mercado accionario,
demanda turística, tráfico aeroportuario, y las dimensiones de referencia (aeropuertos,
aerolíneas, rutas).

**Esta etapa es la más fácil del proyecto.** Casi todo es API limpia. Aprovecharla para
consolidar calidad y dejar el terreno listo para la Etapa 6.

---

## 1. Banxico — tipo de cambio e inflación

**Por qué importa:** Aeroméxico reporta en USD pero cobra buena parte de sus ingresos
en pesos y tiene costos en ambas monedas. El tipo de cambio es un driver directo de
márgenes. Además, para comparar con peers que reportan en EUR (Ryanair, IAG) hace falta
convertir todo a una moneda base.

### Acceso
- API SIE de Banxico: token gratuito en
  `https://www.banxico.org.mx/SieAPIRest/service/v1/token`
- Límite: ~40,000 consultas/día (holgadísimo)
- Librerías: `sie-banxico`, `banxico-sie` (evaluar; el endpoint REST es simple, puede
  implementarse directo)

### Series a traer
| Serie | ID | Uso |
|---|---|---|
| Tipo de cambio FIX USD/MXN | `SF43718` | Conversión principal |
| INPC (inflación) | buscar en el catálogo SIE | Deflactar series nominales |
| TIIE / tasa de referencia | buscar | Costo de deuda, contexto macro |

**Complementos:** FRED (para EUR/USD) y `exchangerate.host` como respaldo.

### Reglas de uso del FX (importante)
- Para **partidas de resultados** (P&L): usar el **promedio del periodo**
- Para **partidas de balance**: usar el **tipo de cambio de cierre**
- Guardar ambos en la tabla de FX y dejar que la capa gold elija según el tipo de métrica
- **Documentar siempre qué tipo de cambio se usó** en cada conversión

### Salida: `silver/fx_rates.parquet`
```
date, currency_pair, rate_close, source, series_id, ingested_at
```
Más una tabla derivada `gold/dim_fx_period` con `period_id, currency_pair,
rate_avg, rate_close, rate_min, rate_max`.

## 2. Combustible — EIA / FRED

**Por qué importa:** el combustible es típicamente 20–40% del costo operativo de una
aerolínea y es el principal driver exógeno de márgenes. Es la variable que hace útil
cualquier modelo de forecast de CASM.

### Series
| Fuente | Serie | Frecuencia |
|---|---|---|
| EIA | `EER_EPJK_PF4_RGC_DPG` — U.S. Gulf Coast Kerosene-Type Jet Fuel Spot Price FOB | Diaria desde 1990 |
| FRED | `DJFUELUSGULF` (diaria), `WJFUELUSGULF` (semanal), `AJFUELUSGULF` (anual) | Varias |

### Acceso
- EIA API v2 con key gratuita, o descarga directa de `.xls` desde eia.gov
- FRED con API key gratuita, o `pandas_datareader`

**Recomendación:** usar FRED como fuente principal (más simple, muy estable) y EIA
como validación. Ambos son la misma serie subyacente.

### Salida: `silver/fuel_prices.parquet`
```
date, series_id, price_usd_per_gallon, source, ingested_at
```
Derivar `gold/dim_fuel_period` con promedio, cierre, min, max y **variación YoY** por
periodo — la variación YoY es lo que se cruza con el CASM.

## 3. Mercado accionario — yfinance

**Por qué importa:** permite superponer la reacción del mercado a los resultados
trimestrales y calcular métricas de valuación básicas.

### Tickers
`AERO` (Aeroméxico), `VLRS` (Volaris), `RYAAY` (Ryanair), `DAL` (Delta), `ICAGY` (IAG ADR).

> **Ojo:** AERO cotiza desde el 6 de noviembre de 2025. La serie es corta. También hay
> otros instrumentos con ticker "AERO" en algunos mercados — **verificar que el ticker
> resuelve a Grupo Aeroméxico** antes de dar la serie por buena.

### Salida: `silver/market_prices.parquet`
```
date, ticker, carrier_key, open, high, low, close, adj_close, volume, currency,
source, ingested_at
```

Derivados para el dashboard (capa gold): retorno acumulado desde IPO, volatilidad
30d, retorno en los 5 días alrededor de cada fecha de publicación de resultados
(**event study** — cruzar con `sec_filings_index`).

## 4. Grupos aeroportuarios — ASUR, GAP, OMA

**Por qué importa:** publican tráfico mensual de pasajeros por aeropuerto de forma
**limpia, oportuna y estructurada**. Es el mejor proxy de demanda por hub y sirve para
validar AFAC. Además son FPI ante la SEC (presentan 20-F), así que su información es
accesible por los mismos caminos de la Etapa 1.

### Aeropuertos relevantes
- **GAP**: Guadalajara, Tijuana, Los Cabos, Puerto Vallarta, Bajío…
- **ASUR**: Cancún, Mérida, Cozumel, Villahermosa…
- **OMA**: Monterrey, Culiacán, Chihuahua…
- **AICM (Ciudad de México)**: **no pertenece a ningún grupo cotizado** — es operado por
  el gobierno. Su información viene del AICM "en Cifras" y de la AFAC. Dado que MEX es
  el hub principal de Aeroméxico, **este dato importa mucho y hay que conseguirlo aparte**.
- **AIFA (Felipe Ángeles)**: también gubernamental; relevante por el desvío de operaciones.

### Acceso
Cada grupo publica un comunicado mensual de tráfico en su sitio de IR y/o vía 6-K.
Preferir el 6-K de EDGAR (formato estable, ya se tiene la infraestructura de la Etapa 1).

### Salida: `silver/airport_traffic.parquet`
```
period_id, airport_iata, airport_name, operator_group, country,
passengers_domestic, passengers_international, passengers_total,
cargo_tons, operations, source, ingested_at
```

## 5. DATATUR / Sectur / INEGI — demanda

**Por qué importa:** variables explicativas para el forecast. La demanda aérea mexicana
está fuertemente ligada al turismo y a la actividad económica.

| Fuente | Datos | Uso |
|---|---|---|
| DATATUR (Sectur) | Llegadas de turistas internacionales, pasajeros aéreos por país de residencia, divisas por turismo | Variables exógenas del forecast |
| INEGI | IGAE (actividad económica), indicadores de turismo | Contexto macro |
| Banxico | Ya cubierto arriba | |

**Prioridad: media.** Traer al menos llegadas de turistas internacionales mensuales.
Si el acceso es complicado, diferir a la Etapa 7 cuando se sepa qué variables realmente
mejoran el modelo.

## 6. Dimensiones de referencia — OurAirports / OpenFlights

**Por qué importa:** son los datasets que permiten conciliar entidades entre fuentes
(códigos IATA/ICAO de aerolíneas y aeropuertos), y geolocalizar rutas para el mapa
del dashboard.

| Dataset | URL | Contenido |
|---|---|---|
| OurAirports | `ourairports.com/data/` | ~80k aeropuertos con IATA, ICAO, lat/lon, país, tipo |
| OpenFlights | `openflights.org/data.html` | Aerolíneas con IATA/ICAO, aeropuertos, rutas |

> OpenFlights está **desactualizado** (rutas de ~2014). Usarlo solo para el mapeo de
> códigos de aerolínea, no para rutas actuales. Las rutas reales salen de BTS T-100
> (Etapa 5) y de los filings.

### Salida
- `gold/dim_airport.parquet` — `airport_iata, airport_icao, name, city, country,
  latitude, longitude, elevation, type, operator_group`
- Alimenta el `carrier_crosswalk.csv` con códigos IATA/ICAO canónicos

## 7. Contexto regulatorio — FAA IASA

**Por qué importa:** el estatus de Categoría 1/2 de la FAA para México condiciona
directamente la capacidad de Aeroméxico de agregar rutas y codeshares a EE.UU.
Es una **variable de evento** que el dashboard debe mostrar como anotación en las
series temporales.

### Eventos conocidos (verificar y actualizar)
| Fecha | Evento |
|---|---|
| 2021-05-25 | FAA degrada a México a **Categoría 2** |
| 2023-09-14 | FAA restaura **Categoría 1** (~28 meses después) |
| 2025-10 | DOT de EE.UU. revoca 13 rutas |
| 2026-08 | Nueva auditoría IASA; Categoría 1 potencialmente en riesgo |

**Tarea del agente:** verificar el estatus actual en `faa.gov` (programa IASA) y en
`transportation.gov` (DOT), y actualizar la tabla. **No dar por hecho el último punto** —
la investigación previa lo marcó como situación en desarrollo.

### Salida: `gold/dim_events.parquet` (tabla curada, semi-manual)
```
event_date, event_type, event_category, title, description,
affected_carriers, impact_direction, source_url, confidence
```
Categorías: `regulatory`, `corporate`, `market`, `operational`, `macro`.
Incluir también: IPO (2025-11-06), salida de Capítulo 11, entregas de flota anunciadas,
apertura/cierre de rutas relevantes.

**Esta tabla es la que convierte gráficas en narrativa.** Cada línea de tiempo del
dashboard debe poder anotar sus eventos.

## 8. Noticias — RSS y GDELT (alcance limitado, deliberadamente)

**Postura del plan:** el análisis de sentimiento de marca con fuentes gratuitas es
**ruidoso y de valor limitado**. Se implementa con alcance acotado:

### Lo que SÍ se hace
- Recolectar titulares vía **Google News RSS** (query: "Aeroméxico", "Aeromexico airline")
  y RSS de medios mexicanos de negocios (El Economista, El Financiero, Expansión)
- **GDELT Project** para volumen de cobertura y tono agregado a lo largo del tiempo
- Construir una **línea de tiempo de eventos** que alimente `dim_events`
- Métricas: volumen de menciones por mes, tono promedio GDELT, temas dominantes

### Lo que NO se hace (regla firme)
- **No** scrapear reseñas de usuarios (Skytrax, TripAdvisor) — restricciones de ToS
  y riesgo legal
- **No** scrapear redes sociales
- **No** presentar el sentimiento de noticias como si midiera satisfacción del cliente.
  Mide cobertura mediática, que es otra cosa. **El dashboard debe decirlo explícitamente.**

### Salida: `silver/news_headlines.parquet`
```
published_at, source_name, title, url, language, query_term,
gdelt_tone, gdelt_theme, ingested_at
```

## 9. Validación de la Etapa 4

- Serie FX completa sin huecos en días hábiles desde 2015
- Serie de jet fuel completa sin huecos en días hábiles
- Precio de AERO desde 2025-11-06 sin huecos en días hábiles
- `dim_airport` cubre el 100% de los aeropuertos que aparecen en las tablas de
  Aeroméxico y AFAC (los que falten se documentan)
- Tráfico de grupos aeroportuarios correlaciona >0.9 con el total de pasajeros de AFAC
- `dim_events` tiene al menos 15 eventos verificados con URL de fuente

---

## Entregables de la Etapa 4

1. `src/ingest/macro/{banxico,fuel}.py`, `src/ingest/market/prices.py`,
   `src/ingest/airports/{groups,reference}.py`, `src/ingest/news/rss_gdelt.py`
2. `silver/fx_rates.parquet`, `silver/fuel_prices.parquet`,
   `silver/market_prices.parquet`, `silver/airport_traffic.parquet`,
   `silver/news_headlines.parquet`
3. `gold/dim_airport.parquet`, `gold/dim_events.parquet`
4. `carrier_crosswalk.csv` enriquecido con IATA/ICAO canónicos
5. Verificación documentada del estatus actual FAA Categoría 1/2
6. `docs/etapas/etapa-4-reporte.md`

**Detenerse y esperar "go".**
