# Etapa 7 — Analítica: Forecast, Clustering, NLP y Anomalías

**Objetivo:** construir la capa analítica sobre las tablas maestras. Todo lo que se
produzca aquí debe (a) ser reproducible, (b) tener validación honesta de desempeño, y
(c) traducirse a una conclusión de negocio comprensible.

**Advertencia de rigor:** con historia trimestral corta para Aeroméxico (relisting
noviembre 2025), **cualquier modelo entrenado solo con datos trimestrales post-IPO va a
estar sobreajustado**. La solución es apoyarse en las series mensuales largas
(AFAC desde 1992, BTS T-100 desde 1990, tráfico aeroportuario) y modelar a nivel mensual,
no trimestral, donde haya suficiente historia.

---

## 1. Análisis exploratorio (obligatorio antes de modelar)

**Módulo:** `src/analytics/eda.py` + `notebooks/01_eda.ipynb`

1. **Cobertura**: para cada métrica y aerolínea, cuántos periodos hay, dónde están los
   huecos. Producir un heatmap de disponibilidad.
2. **Descriptivos**: media, mediana, desviación, min/max, por métrica y aerolínea.
3. **Estacionalidad**: descomposición STL de pasajeros mensuales de Aeroméxico (AFAC).
   Cuantificar la amplitud estacional. Identificar el efecto de Semana Santa.
4. **Correlaciones**: matriz entre métricas de Aeroméxico y variables exógenas
   (jet fuel, FX, turismo, IGAE). Con rezagos de 0 a 6 meses.
5. **Quiebres estructurales**: test de Chow o CUSUM sobre las series largas. Debería
   detectar COVID (2020), quiebra de Interjet (2020), Categoría 2 de la FAA (2021-2023).
6. **Régimen COVID**: decidir explícitamente cómo tratarlo. Recomendación: **no eliminarlo**,
   sino modelarlo con variables dummy, porque la recuperación es parte de la historia.

**Entregable:** `docs/analytics/eda-hallazgos.md` con las 10 observaciones más
importantes, escritas en lenguaje de negocio.

## 2. Forecast

**Módulo:** `src/analytics/forecast.py`

### Qué pronosticar (en orden de valor)
1. **Pasajeros mensuales de Aeroméxico** (AFAC, serie larga) — el más viable
2. **ASK/ASM trimestral** — la compañía da guidance, comparar el modelo contra ella
3. **Load factor trimestral**
4. **TRASM y CASM ex-fuel trimestral** — los más difíciles y los más valiosos
5. **Participación de mercado doméstico**

### Metodología obligatoria

```
1. Split temporal estricto. NUNCA aleatorio.
   Train: hasta T-8 trimestres (o T-24 meses)
   Validation: T-8 a T-4
   Test: últimos 4 periodos (nunca tocado hasta el final)

2. Baselines primero (esto NO es opcional):
   - Naive: y_t = y_{t-1}
   - Seasonal naive: y_t = y_{t-12} (mensual) o y_{t-4} (trimestral)
   - Drift
   Cualquier modelo que no supere el seasonal naive NO va al dashboard.

3. Modelos candidatos, de simple a complejo:
   - SARIMA / auto-ARIMA
   - ETS / Holt-Winters
   - Prophet o StatsForecast (AutoETS, AutoARIMA, AutoTheta)
   - SARIMAX con exógenas (jet fuel, FX, turismo, dummies de eventos)
   - Gradient boosting con features de rezago (solo si hay suficiente historia)

4. Validación: rolling-origin / walk-forward. No un solo split.

5. Métricas: MAPE, sMAPE, MAE, RMSE, y MASE (relativo al naive estacional).
   Reportar TODAS. MAPE solo es engañoso con valores pequeños.

6. Intervalos de predicción SIEMPRE. Un forecast sin banda de incertidumbre
   es desinformación. El dashboard debe mostrar la banda, no solo la línea.
```

### Reglas anti-autoengaño
- **Prohibido** entrenar con datos posteriores al periodo de predicción (leakage)
- **Prohibido** usar exógenas que no estarían disponibles en el momento de predecir
  (ej. no usar el jet fuel del mismo trimestre; usar el rezagado o un forward)
- Documentar el **desempeño del modelo en el conjunto de test** en el propio dashboard.
  Si el MAPE es 12%, decirlo. Un forecast presentado sin su error es una mentira elegante.
- Si ningún modelo supera al baseline, **decirlo y no publicar forecast** para esa
  métrica. Es un resultado legítimo.

### Salida: `gold/fact_forecasts.parquet`
```
model_run_id, model_name, carrier_key, metric_key, period_id,
forecast_value, lower_80, upper_80, lower_95, upper_95,
is_backtest, actual_value, error, abs_pct_error,
trained_through_period, features_used, trained_at
```

Y `gold/dim_model_performance.parquet` con las métricas de evaluación por modelo.

## 3. Clustering

**Módulo:** `src/analytics/clustering.py`

### Tres ejercicios de clustering, cada uno con una pregunta de negocio detrás

#### 3.1 Clustering de aerolíneas — "¿qué tipo de aerolínea es cada una?"
- **Unidad:** aerolínea × periodo
- **Features:** CASK ajustado por stage length, RASK ajustado, load factor,
  stage length, ancillary share, fuel cost share, utilización de flota
- **Pregunta:** ¿los datos separan solos a los network carriers de los ULCC?
  ¿Aeroméxico se mueve hacia el cluster ULCC con el tiempo?
- **Método:** k-means sobre features estandarizadas + PCA para visualizar en 2D.
  Elegir k con silueta y codo, y **justificar la elección**.

#### 3.2 Clustering de rutas — "¿qué tipos de ruta opera Aeroméxico?" (desde T-100)
- **Unidad:** ruta × año
- **Features:** distancia, frecuencia, asientos, load factor, estacionalidad
  (coeficiente de variación mensual), número de competidores, tipo de avión
- **Pregunta:** ¿hay rutas de negocio de alta frecuencia vs rutas de ocio estacionales
  vs rutas de largo alcance? ¿cómo se comporta cada grupo?
- **Aplicación:** identificar rutas atípicas (alto load factor y baja frecuencia → ¿oportunidad?)

#### 3.3 Clustering de trimestres — "¿qué tipo de trimestre fue este?"
- **Unidad:** trimestre de Aeroméxico
- **Features:** crecimiento de capacidad, load factor, spread RASK-CASK, precio del
  combustible, FX
- **Pregunta:** ¿los trimestres se agrupan en regímenes reconocibles (expansión,
  crisis, recuperación, disciplina de capacidad)? ¿en qué régimen estamos hoy?
- **Muy vistoso para el dashboard** y fácil de narrar.

### Reglas
- Estandarizar siempre (las escalas son incomparables)
- Reportar la silueta y justificar k
- **Cada cluster debe recibir un nombre de negocio interpretable**, no "Cluster 0".
  Ej: "Trimestres de disciplina de capacidad", "Rutas de ocio estacional".
  El agente propone los nombres y **los presenta al usuario para validación**.
- Evaluar estabilidad: bootstrap o re-run con semillas distintas. Si los clusters
  cambian radicalmente, decirlo.

## 4. NLP de los reportes trimestrales

El usuario pidió explícitamente analizar "las palabras que se están utilizando en el
reporte trimestral". Insumo: `silver/sec_report_text.parquet` (Etapa 1).

**Módulo:** `src/analytics/nlp_reports.py`

### 4.1 Métricas de texto por trimestre
- Longitud del reporte (palabras) — los reportes se alargan cuando hay malas noticias
- Legibilidad (Flesch adaptado, o índice Fernández Huerta para español)
- Ratio de voz pasiva
- Densidad de números vs prosa

### 4.2 Léxico de tono financiero
- Usar el diccionario **Loughran-McDonald** (específico de finanzas, de dominio público,
  en inglés) para clasificar palabras: positivas, negativas, de incertidumbre,
  litigiosas, de restricción
- Los reportes de Aeroméxico existen en inglés (EDGAR) — usar esa versión para L-M
- Producir por trimestre: `positive_ratio`, `negative_ratio`, `uncertainty_ratio`
- **Graficar el tono contra el desempeño real.** ¿La administración suena optimista
  cuando los números son malos?

### 4.3 Análisis de vocabulario
- Términos más frecuentes por trimestre (TF-IDF contra el corpus completo) → revela
  el tema dominante de cada trimestre
- Palabras que **aparecen** o **desaparecen** entre trimestres consecutivos → señal
  de cambio de foco estratégico
- Frecuencia de términos clave a lo largo del tiempo: "capacity discipline", "premium",
  "cargo", "fleet", "ancillary", "Category 1", "joint venture", "AIFA"

### 4.4 Comparación con peers
El mismo análisis sobre los reportes de Volaris y Delta. ¿Cómo difiere el lenguaje de
un network carrier del de un ULCC?

### Advertencias de honestidad
- El tamaño del corpus es pequeño (pocos trimestres). **Cualquier conclusión es
  indicativa, no estadística.** Decirlo en el dashboard.
- Loughran-McDonald está calibrado para 10-K de empresas estadounidenses; aplicarlo a
  comunicados de un FPI mexicano tiene limitaciones. Declararlo.
- **No** usar esto para inferir intenciones de la administración. Es descripción de
  lenguaje, no lectura de mentes.

### Salida: `gold/fact_report_language.parquet`
```
carrier_key, period_id, accession_number, section,
word_count, readability_score, passive_ratio,
lm_positive_ratio, lm_negative_ratio, lm_uncertainty_ratio,
top_terms_json, new_terms_json, dropped_terms_json
```

## 5. Detección de anomalías

**Módulo:** `src/analytics/anomalies.py`

Dos usos distintos:

### 5.1 Anomalías de calidad de datos (alimenta el panel de salud)
- Valores fuera de rango histórico (z-score > 3 sobre la serie desestacionalizada)
- Rupturas de invariantes (ver Etapa 6)
- Cambios abruptos entre versiones de un mismo dato (restatements grandes)

### 5.2 Anomalías de negocio (alimenta la narrativa)
- Trimestres donde el desempeño se desvía mucho de lo que predice el modelo
- Rutas con comportamiento atípico
- Momentos donde Aeroméxico se desacopla de sus peers

**Cada anomalía detectada debe cruzarse con `dim_events`** para ver si hay una
explicación conocida. Las anomalías **sin** explicación conocida son las interesantes
y deben listarse para investigación.

## 6. Análisis específicos de alto valor (los que dan la narrativa)

Estos son los análisis que convierten el dashboard en algo que alguien quiere leer:

1. **Descomposición del spread RASK−CASK**: ¿cuánto del cambio en el margen unitario
   vino de precio, de costo de combustible, de eficiencia estructural, de FX?
   Un waterfall de contribuciones. **Es el análisis más valioso del proyecto.**
2. **Impacto de la Categoría 2 de la FAA**: usar T-100 para medir ASM de Aeroméxico
   hacia EE.UU. antes (pre 2021-05), durante (2021-05 a 2023-09) y después.
   Comparar contra Delta y las estadounidenses como grupo de control.
   Esto es un **diff-in-diff** natural y muy demostrativo.
3. **Aeroméxico vs Volaris**: la comparación network vs ULCC en el mismo mercado.
   Spread unitario, load factor, ancillary share, participación de mercado.
4. **Sensibilidad al combustible**: elasticidad del CASM al precio del jet fuel.
   Regresión simple con rezagos. Cuantifica el riesgo de la aerolínea.
5. **Event study de resultados**: retorno de AERO en la ventana ±5 días alrededor de
   cada publicación. ¿El mercado reacciona a sorpresas en qué métrica?
6. **Estacionalidad de la red**: qué rutas cargan el verano, cuáles el invierno,
   y qué tan bien está balanceada la red.
7. **Concentración de la red**: índice HHI sobre rutas y aeropuertos. ¿Qué tan
   dependiente es Aeroméxico de MEX?

## 7. Reproducibilidad de los modelos

- Semillas fijas en todo
- Cada corrida de modelo genera un `model_run_id` y guarda: hiperparámetros, features,
  ventana de entrenamiento, métricas, versión del código (`git rev-parse HEAD`)
- Los modelos entrenados se serializan a `models/{model_run_id}/`
- El dashboard consume `fact_forecasts`, **nunca** entrena en tiempo real

## 8. Validación de la Etapa 7

- Todo modelo publicado supera a su baseline en el conjunto de test
- Ninguna métrica de desempeño se reporta sobre el conjunto de entrenamiento
- Todos los forecasts tienen intervalos de predicción
- Cada cluster tiene un nombre de negocio validado por el usuario
- El análisis de lenguaje incluye sus advertencias de limitación
- Los siete análisis de la sección 6 están implementados y producen un hallazgo escrito
- `docs/analytics/hallazgos.md` con las conclusiones de negocio, en español, sin jerga

---

## Entregables de la Etapa 7

1. `src/analytics/{eda,forecast,clustering,nlp_reports,anomalies}.py`
2. `src/analytics/studies/` con los siete análisis de la sección 6
3. `gold/fact_forecasts.parquet`, `gold/dim_model_performance.parquet`,
   `gold/fact_report_language.parquet`, `gold/fact_anomalies.parquet`,
   `gold/dim_cluster_assignments.parquet`
4. Notebooks de exploración en `notebooks/` (exploración, no lógica productiva)
5. `docs/analytics/eda-hallazgos.md` y `docs/analytics/hallazgos.md`
6. Modelos serializados con su metadata
7. `docs/etapas/etapa-7-reporte.md`

**Detenerse y esperar "go".**
