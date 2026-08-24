# Etapa 8 — Dashboard

Fecha de cierre técnico: 2026-08-24
Estado: IMPLEMENTACIÓN Y QA COMPLETAS; PUBLICACIÓN EN STREAMLIT PENDIENTE DE CONFIRMACIÓN EXTERNA

## Qué se construyó

- Dashboard Streamlit de diez páginas, con entrypoint estable en `streamlit_app.py`.
- Capa de acceso offline: Parquet gold registrado en DuckDB en memoria y cacheado por una hora.
- Componentes reutilizables para tarjetas KPI, series con eventos, comparaciones, waterfall, narrativa, estados no disponibles y salud de datos.
- Tarjetas alimentadas por `dim_metric`; si falta `why_it_matters`, interpretación al subir o interpretación al bajar, la vista falla de forma explícita.
- Paleta accesible y colores fijos para Aeroméxico, Volaris, Viva, Delta y Ryanair.
- Plotly para series, forecast, mapa y gráficas estadísticas; ECharts para rankings interactivos, fijado en la versión compatible `0.4.0`.
- Tres extractos gold limitados al dashboard y dos vistas DuckDB.
- Validator ejecutable de aceptación y siete pruebas nuevas.
- Workflow trimestral de validación/publicación con issue automático en fallas y recordatorio AFAC.
- README en español, dos capturas y recorrido narrado de diez páginas.

## Las diez páginas

| Página | Pregunta de negocio | Elementos principales |
|---|---|---|
| Resumen ejecutivo | ¿Cómo le fue este trimestre? | Narrativa condicional, seis KPI, spread con eventos. |
| Economía unitaria | ¿Gana o pierde por unidad de capacidad? | RASK, CASK, spread, waterfall y sensibilidad al combustible. |
| Capacidad y demanda | ¿Está creciendo bien? | ASM/RPM, ocupación, AFAC, segmentos y flota. |
| Competencia | ¿Cómo se posiciona? | Scatter unitario, cuota AFAC, clusters y advertencias contables. |
| Red y rutas | ¿Dónde vuela y qué tan concentrada está? | Mapa local, ranking ECharts, FAA, HHI y clusters. |
| Finanzas | ¿Cómo está la salud financiera? | P&L, costos, balance, acción y conciliación. |
| Forecast | ¿Qué sugiere la historia? | Observado, backtest, futuro, bandas, MAPE y escenario. |
| Lenguaje de reportes | ¿Cómo cambia el tono? | Loughran-McDonald, longitud y vocabulario. |
| Salud de datos | ¿Cuánto se puede confiar? | Frescura, cobertura, issues, restatements y faltantes. |
| Glosario | ¿Qué significa cada KPI? | `dim_metric` buscable con fórmula, lectura y advertencias. |

## Datos preparados para el dashboard

| Tabla gold | Filas | Cobertura / contenido |
|---|---:|---|
| `fact_route_traffic_summary` | 66,770 | Mercado bidireccional y mes, `2015M01`–`2026M05`; agregada desde T-100. |
| `fact_spread_decomposition` | 4 | Precio, combustible, residual estructural y FX no identificado. |
| `fact_dashboard_coverage` | 247 | Cobertura observada/esperada por aerolínea, métrica, segmento y frecuencia. |

Vistas: `v_dashboard_route_latest12` y `v_dashboard_source_freshness`.

El repositorio contiene 25 Parquet gold, 13.96 MiB en total. Bronze y silver permanecen fuera de Git; gold se versiona porque es la capa pública, compacta y validada que consume Streamlit Community Cloud.

## Cifras ancla

El validator consultó `2026Q1` desde las vistas consolidadas y verificó:

| Métrica | Esperado | Observado | Resultado |
|---|---:|---:|---|
| Ingreso total | US$1,341.0 M | US$1,341.0 M | PASS |
| Margen EBITDAR ajustado | 25.0% | 25.0% | PASS |
| Factor de ocupación reportado | 84.4% | 84.4% | PASS |
| TRASM | 15.6 ¢/ASM | 15.6 ¢/ASM | PASS |
| CASM | 13.8 ¢/ASM | 13.8 ¢/ASM | PASS |
| CASM ex combustible | 10.2 ¢/ASM | 10.2 ¢/ASM | PASS |

La página de resumen abre en el trimestre más reciente (`2026Q2`): ingreso US$1,479.0 M, margen EBITDAR ajustado 17.9%, ocupación 84.9% y spread 0.43 centavos por ASK-km.

## Validaciones ejecutadas

| Check | Resultado |
|---|---|
| Suite completa | PASS — 102 pruebas |
| Aceptación Etapa 8 | PASS — 18/18 controles locales |
| Contratos gold | PASS — 25/25 tablas |
| Páginas | PASS — 10/10 sin excepciones |
| Interpretación KPI | PASS — campos obligatorios presentes para toda métrica de dashboard |
| Forecast | PASS — 24 filas, bandas 80/95 completas y MAPE de test visible |
| Comparabilidad | PASS — IFRS/US-GAAP, Ryanair-marzo y stage length visibles |
| Salud de datos | PASS — 23 issues reales y 66 restatements visibles |
| Eventos | PASS — líneas y etiquetas integradas en series temporales |
| Offline | PASS — sin cliente HTTP ni llamada de red en `src/dashboard/data.py` |
| Rendimiento | PASS — inicial 0.19–0.60 s; rerun 0.01–0.08 s |
| Contraste | PASS — texto ≥4.5:1 y marcas gráficas ≥3:1 contra blanco |
| Navegación real | PASS — navegación y deep link `/forecast` verificados en navegador local |
| Workflow remoto | PASS — ejecución manual en GitHub Actions, sin issues ni cambios gold |

La inspección visual encontró y corrigió dos defectos que el test programático no veía:

1. ejecutar `src/dashboard/app.py` directamente hacía que Streamlit confundiera la carpeta `pages/` con su sistema antiguo en enlaces profundos; `streamlit_app.py` lo evita;
2. la leyenda del forecast se superponía al subtítulo; se movió debajo del área gráfica y se amplió el margen.

## Calidad y honestidad epistémica

- El dashboard muestra que no existe etapa promedio global comparable; no publica clustering de aerolíneas ni RASK/CASK ajustados ficticios.
- NLP de peers aparece como no disponible porque no hay textos ingeridos.
- Guidance estructurado aparece como no disponible.
- FX permanece no identificado en la descomposición del spread.
- El escenario de combustible se etiqueta como ilustrativo y de confianza baja.
- Un registro T-100 de mercado pequeño contiene 11 pasajeros sobre 10 asientos (110%). Se conserva como observación de fuente; no se recortó para que “cuadrara”.

## Workflow de actualización

`.github/workflows/refresh.yml` corre el 5 de febrero, mayo, agosto y noviembre, o manualmente. Hace lo siguiente:

1. instala el lock;
2. revisa la antigüedad de AFAC;
3. abre un issue de fuente manual si rebasa 62 días;
4. ejecuta pruebas y validación de Etapa 8;
5. abre un issue `validation-failed` y se detiene antes del commit si algo falla;
6. commitea cambios gold solo si todo pasa.

Limitación explícita: como bronze no se versiona, GitHub Actions no puede reconstruir desde descargas históricas que no existen en el runner. La ingesta y reconstrucción con crudos nuevos sigue siendo local; el workflow remoto valida y publica gold ya reconstruido. Automatizarlo completamente requeriría autorizar un almacenamiento externo de bronze, decisión fuera del alcance confirmado.

## Decisiones tomadas

- Se mantuvo Streamlit, conforme al stack ya decidido en el plan.
- ECharts `0.7.0` no declaró sus assets de forma portable bajo este proyecto; se fijó `0.4.0`, que funciona offline y conserva licencia abierta.
- No se usan mapas o fuentes tipográficas externas; la vista de rutas es esquemática y local.
- Los gold se versionan; bronze, silver, warehouse y modelos binarios siguen locales.
- El `model_run_id` de Etapa 7 dejó de depender de tablas downstream de Etapa 8, evitando que una reconstrucción generara identificadores circulares.
- Se eligieron textos condicionales deterministas, no un LLM en runtime.

## Qué no funcionó y por qué

- El repositorio público quedó disponible en `https://github.com/salvamalfa/aeromexico-tracker`. El deploy final en Streamlit Community Cloud no se ejecutó: el flujo llegó al inicio de sesión OAuth de GitHub, pero el navegador integrado no tiene una sesión autenticada. Iniciar sesión y crear una publicación web requieren intervención/confirmación inmediata; el usuario estaba dormido. El entrypoint, gold, lock, README y enlace de deploy quedaron listos.
- La documentación oficial vigente confirma que el alta y deploy se realizan desde el workspace autenticado, sin CLI/API de creación. `docs/deploy-streamlit.md` deja resueltos repositorio, rama, entrypoint, ausencia de secretos y Python 3.13; este último debe elegirse en Advanced settings porque el default documentado es 3.12.
- No se implementó ingesta cloud completa: contradice la decisión de no versionar bronze y no existe almacenamiento externo autorizado.

## Riesgos abiertos

- Streamlit Community Cloud debe probarse una vez contra el repositorio público; cualquier diferencia de entorno se resolverá antes de declarar la URL definitiva.
- AFAC llega a 62 días de antigüedad antes que otras fuentes; el workflow ya lo trata como recordatorio manual, no como dato cero.
- El tamaño actual de gold (13.96 MiB) es adecuado; si T-100 crece materialmente, habrá que revisar el extracto de rutas.

## Comandos para reproducir

```powershell
uv sync --all-extras --all-groups --locked
uv run pytest -q
uv run python -m src.dashboard.validate_stage8
uv run streamlit run streamlit_app.py
```

## Gate final

La implementación, validación, documentación y QA visual de Etapa 8 están cerradas. Falta la confirmación del usuario para publicar externamente en Streamlit Community Cloud y sustituir el texto pendiente del README por la URL pública verificada.
