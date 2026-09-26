# Etapa 8 — Dashboard

**Objetivo:** construir el producto final: un dashboard interactivo que cuente la
historia de Aeroméxico con datos, donde **cada KPI viene acompañado de su interpretación
de negocio**.

**Principio rector:** este no es un tablero de métricas. Es un **argumento con datos**.
Un usuario de negocio debe poder recorrerlo y salir entendiendo cómo le va a Aeroméxico
y por qué, sin saber qué es un ASK cuando entró.

---

## 1. Decisiones de stack (ya tomadas, con justificación)

| Decisión | Elección | Por qué |
|---|---|---|
| Framework | **Streamlit** | Python puro, despliegue trivial, encaja con el perfil del usuario, cubre el 80% de lo necesario |
| Gráficas | **ECharts** (vía `streamlit-echarts`) + Plotly donde convenga | Open source real (Apache 2.0 / MIT). ECharts para lo interactivo y vistoso; Plotly para lo estadístico |
| **NO Highcharts** | — | Su EULA (endurecido en 2025) da uso gratuito solo personal/no comercial; el uso interno de negocio y prototipos requiere licencia. Aunque este proyecto califica hoy, la ambigüedad no compensa cuando ECharts es igual de bueno y Apache 2.0 |
| Datos | Lee `gold/*.parquet` o `warehouse.duckdb` directo | Sin backend, sin API |
| Despliegue | Streamlit Community Cloud | Gratis, URL pública para portafolio |

### Alternativa a considerar si el usuario prefiere SQL-first
**Evidence.dev** (BI-as-code: SQL + Markdown → sitio estático, deploy en Vercel/Netlify).
Encaja muy bien con el perfil BigQuery del usuario y produce algo que se lee como
reporte narrativo. **Presentar la opción al inicio de la etapa** y dejar que decida.
Si elige Evidence, la estructura de contenido de este documento sigue aplicando.

## 2. Arquitectura del dashboard

```
src/dashboard/
├── app.py                      # entrypoint, navegación
├── data.py                     # capa de acceso a datos, con @st.cache_data
├── components/
│   ├── kpi_card.py             # tarjeta de KPI CON su explicación de negocio
│   ├── metric_chart.py         # gráfica de serie con anotaciones de eventos
│   ├── comparison_chart.py     # comparación entre aerolíneas
│   ├── waterfall.py            # descomposición de contribuciones
│   ├── narrative.py            # bloques de texto explicativo
│   └── data_health.py          # panel de calidad de datos
├── pages/
│   ├── 1_resumen.py
│   ├── 2_economia_unitaria.py
│   ├── 3_capacidad_y_demanda.py
│   ├── 4_competencia.py
│   ├── 5_red_y_rutas.py
│   ├── 6_finanzas.py
│   ├── 7_forecast.py
│   ├── 8_lenguaje_reportes.py
│   ├── 9_salud_de_datos.py
│   └── 10_glosario.py
└── assets/
    └── style.css
```

### Regla de caché
```python
@st.cache_data(ttl=3600)
def load_gold_table(name: str) -> pl.DataFrame: ...
```
El dashboard **nunca** ejecuta ingesta ni entrena modelos. Solo lee gold.

## 3. El componente que define el proyecto: `kpi_card`

El usuario pidió explícitamente que cada KPI tenga explicación de negocio. Este
componente es donde eso vive. **Toda la información viene de `dim_metric`, no está
hardcodeada.**

```python
def kpi_card(metric_key: str, carrier_key: str, period_id: str):
    """
    Renderiza:
    ┌──────────────────────────────────────────────┐
    │ CASM ex-fuel                              ⓘ  │
    │ 10.2 ¢/ASM                                   │
    │ ▼ -3.2% vs 1Q25    ▲ +1.1% vs 4Q25          │
    │                                              │
    │ Costo de operar un asiento por milla,        │
    │ sin combustible.                             │
    │                                              │
    │ [Al expandir ⓘ:]                             │
    │ Qué significa: mide la eficiencia            │
    │ estructural de la aerolínea, aislada del     │
    │ precio del combustible que no controla.      │
    │                                              │
    │ Si baja: la aerolínea está operando más      │
    │ eficientemente — mejores contratos, mejor    │
    │ utilización de flota, o etapas más largas.   │
    │                                              │
    │ Si sube: presión de costos estructurales.    │
    │ Ojo: puede subir simplemente porque la       │
    │ aerolínea voló etapas más cortas.            │
    │                                              │
    │ Referencia: un network carrier típico opera  │
    │ arriba de un ULCC en esta métrica por        │
    │ diseño (más servicio, más hub, más conexión).│
    │                                              │
    │ Cuidado: no comparable entre aerolíneas sin  │
    │ ajustar por stage length.                    │
    │                                              │
    │ Fórmula: (gastos operativos − combustible)   │
    │          / ASM                               │
    │ Fuente: comunicado de resultados 1Q26        │
    └──────────────────────────────────────────────┘
    """
```

**Requisito no negociable:** ninguna métrica se muestra en el dashboard si no tiene su
`business_interpretation_up`, `business_interpretation_down` y `why_it_matters`
poblados en `dim_metric`. Si falta, el componente falla ruidosamente en desarrollo.

## 4. Estructura de páginas y narrativa

### Página 1 — Resumen ejecutivo
**Pregunta que responde:** ¿cómo le fue a Aeroméxico este trimestre?

- Bloque de narrativa generado desde los datos (no LLM en runtime; texto con plantillas
  y condicionales): "En 1Q26 Aeroméxico creció ingresos 13.3% con capacidad casi plana,
  lo que indica una estrategia de precio sobre volumen…"
- 6 KPI cards: Ingreso total, Margen EBITDAR, Load factor, TRASM, CASM ex-fuel,
  Spread unitario
- Gráfica principal: **spread RASK−CASK** por trimestre, con anotaciones de eventos
- Selector de trimestre (por defecto: el más reciente)

### Página 2 — Economía unitaria (la más importante)
**Pregunta:** ¿está ganando o perdiendo dinero por asiento, y por qué?

- RASK, CASK y su spread en una sola gráfica, versión cruda y ajustada por stage length
  (toggle)
- **Waterfall de descomposición del cambio en el spread**: precio, combustible,
  eficiencia estructural, FX, mix
- Break-even load factor vs load factor real → colchón de seguridad
- Sensibilidad al combustible (de la Etapa 7)
- Explicación narrativa: por qué el spread importa más que RASK o CASK por separado

### Página 3 — Capacidad y demanda
**Pregunta:** ¿está creciendo bien, o creciendo mal?

- ASK vs RPK con load factor superpuesto
- Crecimiento YoY de capacidad vs de demanda (si capacidad crece más rápido que demanda,
  el load factor cae y probablemente el yield también → explicarlo)
- Desglose doméstico vs internacional
- Serie mensual (AFAC) con desestacionalización opcional
- Flota y utilización

### Página 4 — Competencia
**Pregunta:** ¿cómo se compara con quienes compiten con él?

- **Mapa de posicionamiento**: scatter de CASK ajustado (x) vs RASK ajustado (y),
  una burbuja por aerolínea-periodo, tamaño = ASK. La diagonal es el break-even.
  **Es la gráfica más elocuente del proyecto.**
- Participación de mercado en México (AFAC), serie mensual apilada
- Tabla comparativa de KPIs con las advertencias de comparabilidad visibles
- Los clusters de la Etapa 7 visualizados
- **Advertencia obligatoria y visible**: diferencias de norma contable (Delta en US-GAAP),
  año fiscal (Ryanair cierra en marzo), y stage length

### Página 5 — Red y rutas
**Pregunta:** ¿dónde vuela y qué tan bien le va en cada mercado?

- Mapa de rutas México-EE.UU. (desde T-100) con líneas ponderadas por asientos
- Top rutas por ASM, por load factor, por crecimiento
- Participación por ruta vs competidores
- **Análisis del impacto de la Categoría 2 de la FAA** (el diff-in-diff de la Etapa 7)
- Clusters de rutas
- Concentración de la red (HHI)

### Página 6 — Finanzas
**Pregunta:** ¿cómo está la salud financiera?

- P&L trimestral (desde XBRL de BMV)
- Estructura de costos: composición y evolución (combustible como % del total)
- Balance: deuda, pasivos por arrendamiento (IFRS 16), efectivo
- Flujo de efectivo
- Precio de la acción con marcadores de fechas de resultados (event study)
- Conciliación de fuentes visible (BMV vs comunicado)

### Página 7 — Forecast
**Pregunta:** ¿qué se espera hacia adelante?

- Proyecciones con **bandas de incertidumbre siempre visibles**
- Backtest mostrado junto al forecast (para que el usuario juzgue la confiabilidad)
- **Desempeño del modelo declarado explícitamente**: "MAPE en test: 6.4%"
- Comparación contra el guidance de la compañía si existe
- Escenarios: qué pasa con el margen si el jet fuel sube 20%

### Página 8 — Lenguaje de los reportes
**Pregunta:** ¿cómo habla la administración de su propio desempeño?

- Tono (positivo/negativo/incertidumbre) por trimestre vs desempeño real
- Términos dominantes por trimestre (nube o barras, no una nube fea)
- Términos que aparecen y desaparecen
- Longitud y legibilidad del reporte
- **Advertencias de limitación visibles** (corpus pequeño, léxico calibrado para otro
  contexto)

### Página 9 — Salud de los datos
**Pregunta:** ¿qué tan confiable es todo lo anterior?

Esta página es lo que separa un proyecto serio de uno bonito.

- Última actualización por fuente
- Cobertura: % de periodos con dato, por métrica y aerolínea (heatmap)
- Issues de calidad abiertos, por severidad
- Historial de restatements
- Conciliación entre fuentes (SEC vs BMV vs AFAC vs T-100)
- Qué métricas son reportadas vs derivadas
- **Ser explícito sobre lo que no se sabe.** La honestidad epistémica es parte del
  entregable.

### Página 10 — Glosario
Todo `dim_metric` renderizado como referencia navegable: fórmula, interpretación,
benchmarks, advertencias. Buscable.

## 5. Diseño visual

Leer `/mnt/skills/public/frontend-design/SKILL.md` si está disponible en el entorno,
antes de definir la estética.

Principios:
- **Paleta sobria y una identidad propia.** Evitar el look de plantilla por defecto.
  Aeroméxico tiene identidad visual (azul y rosa/magenta); usar una paleta inspirada
  sin copiar la marca (es un proyecto independiente, no oficial — **decirlo en el pie**).
- **Máximo 6 KPIs por vista.** Más es ruido.
- Tipografía: una sans para UI, tabular numbers para las cifras.
- **Colores con significado consistente**: un color para Aeroméxico en todo el dashboard,
  otro para cada peer. Verde/rojo solo cuando "mejor/peor" es inequívoco (ojo: un CASM
  bajo es bueno, un RASK bajo es malo — el color debe seguir `dim_metric.higher_is_better`).
- Accesibilidad: contraste AA, no depender solo del color para codificar información.
- Responsive: se va a ver en laptop, no en móvil, pero no debe romperse.

### Anotaciones de eventos
Toda serie temporal debe poder mostrar los eventos de `dim_events` como líneas
verticales con tooltip. **Esto es lo que convierte una gráfica en una historia.**

## 6. Textos y narrativa

- **Todo el texto de negocio en español**, en registro claro y directo.
- La narrativa se genera con **plantillas condicionales sobre los datos**, no con un LLM
  en tiempo de ejecución (el dashboard debe ser determinista y offline).
  ```python
  if capacity_growth < 0.02 and revenue_growth > 0.10:
      narrative = "Crecimiento de ingresos con capacidad casi plana: señal de..."
  ```
- Cada página abre con un párrafo que dice **qué pregunta responde**.
- **Prohibido** el lenguaje de recomendación de inversión. Es análisis, no consejo.
  Incluir un disclaimer en el pie.

## 7. Rendimiento

- Precalcular todo en gold. El dashboard no agrega ni modela.
- `@st.cache_data` en toda carga.
- Los datos completos deben pesar poco; si `bts_t100_segment` es enorme, crear un
  agregado `gold/fact_route_traffic_summary` para el dashboard y dejar el detalle
  solo para análisis offline.
- Objetivo: carga inicial <3 segundos, cambio de página <1 segundo.

## 8. Despliegue y actualización

### Despliegue
Streamlit Community Cloud, apuntando al repo de GitHub. Los datos gold **sí** se
versionan en el repo (son pequeños en Parquet) para que el deploy funcione sin
infraestructura de datos.

> Si los Parquet gold resultan pesados, alternativa: publicarlos como release assets
> de GitHub y que la app los descargue al arrancar, cacheados.

### Actualización — `.github/workflows/refresh.yml`
```yaml
on:
  schedule:
    - cron: "0 12 5 2,5,8,11 *"   # ~5 de feb/may/ago/nov: post-resultados trimestrales
  workflow_dispatch:               # disparo manual siempre disponible
```
El workflow:
1. Corre la ingesta de las fuentes automatizables (SEC, Banxico, FRED, yfinance, BTS)
2. Reprocesa silver y gold
3. Corre la suite de validación
4. **Si la validación falla, abre un issue en GitHub y NO hace commit**
5. Si pasa, commitea los Parquet gold actualizados

**Las fuentes que requieren computer use (probablemente AFAC, quizá BMV) no se
automatizan.** El workflow debe detectarlo y abrir un issue de recordatorio:
"AFAC no se ha actualizado desde {fecha}; requiere descarga manual".

Y el dashboard debe mostrar visiblemente la antigüedad de cada fuente.

## 9. Validación de la Etapa 8

- Toda métrica mostrada tiene su interpretación de negocio poblada
- La cifra ancla de 1Q26 aparece correctamente en la página de resumen
- Ningún forecast se muestra sin banda de incertidumbre y sin su MAPE de test
- Las advertencias de comparabilidad son visibles en la página de competencia
- La página de salud de datos refleja el estado real de `data_quality_issues`
- El dashboard carga y funciona **sin conexión a internet** (datos locales)
- Contraste de color AA verificado
- El deploy público funciona y la URL está en el README
- Un usuario que no sabe qué es un ASK puede recorrer el dashboard y entender la historia

---

## Entregables de la Etapa 8

1. App Streamlit completa con las 10 páginas
2. Componentes reutilizables, en particular `kpi_card` alimentado por `dim_metric`
3. Estilos y paleta definidos
4. `.github/workflows/refresh.yml` funcionando
5. Deploy público en Streamlit Community Cloud
6. README del repo actualizado con capturas y la URL
7. `docs/etapas/etapa-8-reporte.md`
8. **Un recorrido narrado del dashboard** (documento o video corto) que sirva como
   pieza de portafolio

**Fin del plan. Presentar el proyecto completo al usuario.**
