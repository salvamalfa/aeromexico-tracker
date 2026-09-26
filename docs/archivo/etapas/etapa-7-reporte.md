# Etapa 7 — Analítica

Fecha de cierre: 2026-08-23  
Estado: COMPLETA

## Qué se construyó

- EDA reproducible de cobertura, descriptivos, estacionalidad, correlaciones con rezagos y quiebres estructurales.
- Notebook ejecutado de punta a punta en `notebooks/01_eda.ipynb`; la lógica productiva permanece en módulos Python.
- Forecast mensual de pasajeros Aeroméxico con separación temporal estricta, validación rolling-origin, tres baselines y dos candidatos.
- Gate automático que impide publicar un modelo si no supera al ingenuo estacional en test.
- Bandas de predicción de 80% y 95% para backtest y futuro.
- Clustering de 407 observaciones ruta-año con estandarización, PCA, silueta y estabilidad entre semillas.
- NLP descriptivo de 11 reportes SEC con el diccionario oficial Loughran-McDonald preservado en bronze.
- Detección de anomalías de pasajeros, desacoplamiento contra Volaris y rutas atípicas, cruzada con `dim_events`.
- Los siete estudios de negocio previstos: spread unitario, FAA Categoría 2, Aeroméxico-Volaris, combustible, reacción a resultados, estacionalidad y concentración.
- Seis tablas analíticas gold, cinco vistas DuckDB y actualización automática del diccionario de datos.
- Metadata y estimador serializado bajo `models/stage7_3e164aa09ada33b1/`; el binario local no se versiona.

## Resultados del forecast

Objetivo publicado: pasajeros mensuales AFAC de Aeroméxico consolidado. La selección usó 12 meses de validación y el gate final usó exclusivamente los últimos 12 meses de test, julio de 2025 a junio de 2026.

| Modelo | sMAPE validación | sMAPE test | MAPE test | MASE test | Publicado |
|---|---:|---:|---:|---:|---:|
| Naive | 6.82% | 8.35% | 8.49% | 0.588 | No |
| Naive estacional | 2.87% | 3.36% | 3.45% | 0.243 | Baseline |
| Drift | 6.89% | 8.36% | 8.51% | 0.589 | No |
| ETS amortiguado | 4.71% | 4.98% | 5.05% | 0.348 | No |
| SARIMA | 3.87% | **2.50%** | **2.58%** | **0.174** | Sí |

SARIMA se eligió por validación y después superó al naive estacional en test. Se publicaron 12 backtests y 12 meses futuros, de julio de 2026 a junio de 2027. En los 12 backtests, la banda de 80% cubrió 11 observaciones y la de 95% cubrió las 12. Ninguna métrica de entrenamiento se presenta como desempeño.

No se publicaron forecasts trimestrales de ASK/ASM, load factor, TRASM o CASM ex fuel. Aeroméxico solo tiene ocho trimestres comparables en esas métricas y usarlos para aparentar precisión habría producido sobreajuste.

## Segmentación

| Ejercicio | Resultado |
|---|---|
| Aerolíneas | No publicado: falta etapa promedio global comparable y las métricas SLA son nulas. |
| Rutas | Publicado: 407 ruta-año, k=3, silueta 0.3252, estabilidad ARI 1.000. |
| Trimestres | No publicado: siete observaciones completas y todo k factible generó al menos un grupo unitario. |

Los clusters de ruta son:

| Nombre de negocio | Asignaciones |
|---|---:|
| Ocio estacional | 265 |
| Alta frecuencia | 134 |
| Conectividad equilibrada | 8 |

Se eligió k=3 como la mejor silueta entre k=2 y k=6 sujeta a un mínimo de cinco observaciones por cluster. Los nombres se seleccionaron bajo la autoridad de decisión delegada por el usuario para estas dos etapas y quedan visibles en el dashboard para revisión posterior.

## Lenguaje de reportes

- Corpus: 11 documentos de Aeroméxico, cuatro de resultados y siete de tráfico.
- Métricas: longitud, Flesch aproximado, voz pasiva aproximada, densidad numérica y cinco categorías Loughran-McDonald.
- Vocabulario: TF-IDF, términos nuevos y términos ausentes frente al reporte anterior del mismo tipo.
- Fuente léxica: versión marzo de 2026 del [Software Repository for Accounting and Finance de Notre Dame](https://sraf.nd.edu/loughranmcdonald-master-dictionary/), preservada cruda con hash.
- Comparación con peers: no disponible. Hay hechos operativos de Volaris y Delta, pero no textos de sus reportes en silver; no se sustituyeron ni inventaron.

Las conclusiones son indicativas: el corpus es pequeño, el léxico fue calibrado principalmente para 10-K estadounidenses y el análisis describe lenguaje sin inferir intenciones.

## Siete estudios y hallazgos

1. **Spread RASK-CASK:** cayó 0.68 centavos por ASK-km entre 1Q26 y 2Q26. Precio aportó +0.25, el proxy de combustible -1.04 y el residual estructural +0.11. FX no pudo aislarse y no se estimó.
2. **FAA Categoría 2:** frente a Delta, la razón de ASM Aeroméxico/Delta cambió -17.8% durante Categoría 2 contra el periodo previo y +16.4% después de Categoría 1. Es un experimento natural descriptivo, no una afirmación causal estricta.
3. **Aeroméxico vs Volaris:** en junio de 2026, la participación total AFAC fue 19.1% contra 26.2%; brecha Aeroméxico menos Volaris de -7.1 puntos.
4. **Combustible:** elasticidad descriptiva de CASK de +0.62 ante combustible rezagado, con solo siete trimestres; confianza baja y resultado no concluyente.
5. **Resultados y bolsa:** en dos publicaciones posteriores al relisting con ventana completa, el retorno bruto promedio en ±5 sesiones fue -7.7%. No hay benchmark de mercado en gold, por lo que no se llama retorno anormal.
6. **Estacionalidad de rutas:** MEX-SEA tuvo el mayor sesgo de verano entre rutas con al menos 24 meses, con índice 1.45 contra su mes promedio.
7. **Concentración:** HHI por mercado de 0.061 y 83.5% de las salidas T-100 observadas tocando MEX en los últimos 12 meses.

## Anomalías

Se generaron 23 anomalías:

- 15 residuales estacionales de pasajeros; cuatro coinciden con un evento conocido.
- 2 desacoplamientos de participación Aeroméxico-Volaris; uno coincide con evento.
- 6 rutas-año en el extremo de su cluster; una coincide con evento.
- 17 quedan sin explicación temporal cercana y se presentan como lista de investigación, no como errores confirmados.

## Tablas y vistas nuevas

| Tabla gold | Filas | Contenido |
|---|---:|---|
| `fact_forecasts` | 24 | 12 backtests y 12 pronósticos con intervalos. |
| `dim_model_performance` | 5 | Métricas de test de baselines y candidatos. |
| `fact_report_language` | 11 | Métricas NLP por documento. |
| `fact_anomalies` | 23 | Anomalías y evento cercano, si existe. |
| `dim_cluster_assignments` | 407 | Cluster, PCA, silueta, estabilidad y features por ruta-año. |
| `fact_study_results` | 7 | Un hallazgo escrito por estudio de alto valor. |

Vistas nuevas: `v_forecast_published`, `v_latest_business_findings`, `v_cluster_summary`, `v_report_language` y `v_anomaly_investigation`.

## Validaciones ejecutadas

| Check | Resultado |
|---|---|
| Suite completa | PASS — 95 tests |
| Definición de aceptación Etapa 7 | PASS — 18/18 controles |
| Contratos gold | PASS — 22/22 tablas, seis de Etapa 7 |
| Baseline gate | PASS — todo modelo publicado supera naive estacional en test |
| Split de desempeño | PASS — solo `test`, nunca `train` |
| Intervalos | PASS — 100% de forecasts con bandas 80% y 95% ordenadas |
| Leakage temporal | PASS — cada backtest fue entrenado solo hasta el periodo anterior |
| Clusters | PASS — nombres de negocio, silueta, k y estabilidad documentados |
| NLP | PASS — ratios válidos y cuatro limitaciones explícitas |
| Estudios | PASS — 7/7 con hallazgo escrito |
| Notebook | PASS — ejecutado de principio a fin |
| Rebuild offline | PASS — ejecución completa sin red |
| Idempotencia | PASS — 22/22 hashes gold idénticos tras ejecuciones repetidas |

## Instalaciones realizadas

Se añadieron al grupo de desarrollo `nbformat`, `nbclient` e `ipykernel` para construir y ejecutar el notebook. No se añadió ninguna dependencia de producción nueva para los modelos; `statsmodels`, `scikit-learn`, Streamlit y Plotly ya estaban instalados por las etapas previas.

## Decisiones tomadas

- Solo pasajeros mensuales superaron el umbral de historia y desempeño para forecast.
- El gate usa sMAPE contra naive estacional; MAPE, MAE, RMSE y MASE se conservan para auditoría.
- COVID permanece en la historia.
- Los clusters inestables o basados en features faltantes no se publican.
- El modelo binario queda local e ignorado por Git; metadata y resultados de evaluación sí se versionan.
- Los nombres de cluster son decisiones de negocio explícitas, no etiquetas técnicas disfrazadas.

## Preguntas para el usuario

Ninguna bloquea el cierre. Los tres nombres de cluster de ruta quedan listos para revisión cuando el usuario despierte; fueron elegidos bajo su autorización delegada.

## Riesgos para la siguiente etapa

- El dashboard debe distinguir con claridad los estudios de confianza alta, media y baja.
- No debe mostrar páginas vacías como si fueran fallas: clustering de aerolíneas/trimestres y NLP de peers necesitan estados explicativos.
- El forecast debe mostrar su sMAPE de test y ambas bandas de incertidumbre.
- El despliegue público puede requerir una cuenta o credencial externa; la app local puede completarse y validarse sin ella.

## Comandos para reproducir

```powershell
uv run python -m src.analytics
uv run python -m src.analytics.validate_stage7
uv run python -m src.rebuild
uv run pytest -q
```

La Etapa 8 continúa inmediatamente por el `go` anticipado del usuario.
