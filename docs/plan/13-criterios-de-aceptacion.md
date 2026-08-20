# 13 — Criterios de Aceptación (Definition of Done)

Este documento define, para cada etapa, **exactamente** qué debe cumplirse antes de
presentar resultados al usuario y pedir el "go".

**Regla:** el agente no declara una etapa terminada si algún ítem obligatorio está sin
cumplir. Si algo no se pudo lograr, se reporta como incompleto con su razón — no se
declara terminado.

---

## Formato del reporte de cierre de etapa

Cada etapa produce `docs/etapas/etapa-N-reporte.md`:

```markdown
# Etapa N — {nombre}
Fecha de cierre: {fecha}
Estado: COMPLETA | COMPLETA CON EXCEPCIONES | INCOMPLETA

## Qué se construyó
{lista de módulos, tablas, artefactos}

## Datos obtenidos
| Fuente | Periodos | Filas | Tamaño | Método de acceso |

## Validaciones ejecutadas
| Check | Resultado | Detalle |

## Cifras ancla verificadas
| Métrica | Esperado | Obtenido | ¿Coincide? |

## Qué NO funcionó y por qué
{honesto y específico}

## Decisiones tomadas
{cada una con su justificación}

## Supuestos hechos
{explícitos, para que el usuario pueda corregirlos}

## Preguntas para el usuario
{decisiones de negocio que el agente no debe tomar solo}

## Riesgos para la siguiente etapa
{qué puede salir mal}

## Comandos para reproducir
{copiables}
```

---

## Etapa 0 — Setup

**Obligatorio:**
- [ ] `pytest` pasa en verde
- [ ] `python -m src.smoke_test` corre completo sin excepciones no manejadas
- [ ] Matriz de conectividad completa para las 8 fuentes en `docs/etapas/etapa-0-conectividad.md`
- [ ] `src/common/{http,storage,quality,logging}.py` implementados **y testeados**
- [ ] `save_bronze()` demostrado: guarda archivo + `.meta.json` con hash correcto,
      y no re-escribe si el hash coincide
- [ ] Rate limiter demostrado: un test verifica que no se exceden N req/s
- [ ] `.env.example` completo; `.env` local configurado con `SEC_USER_AGENT` real
- [ ] `just` (o `make`) con todos los targets funcionando
- [ ] Commit inicial en git
- [ ] Todas las instalaciones fueron autorizadas por el usuario

**Preguntas obligatorias al usuario antes de cerrar:**
- ¿Se versiona `data/bronze/` en git o solo el manifiesto?
- ¿Correo para el `SEC_USER_AGENT`?

---

## Etapa 1 — SEC EDGAR

**Obligatorio:**
- [ ] Estado del `companyfacts` de AERO verificado y reportado
- [ ] `silver/sec_filings_index.parquet` con todos los filings clasificados por tipo
- [ ] Todos los 6-K de resultados y de tráfico descargados a bronze
- [ ] 20-F FY2025 y F-1/A del IPO descargados
- [ ] `silver/sec_operating_metrics.parquet` poblada
- [ ] **Cifras ancla de 1Q26 verificadas** (ver `00-contexto-y-principios.md` §3):
      revenue 1,341 M, EBITDAR 335.8 M, margen 25.0%, op. income 141.8 M, margen 10.6%,
      CASM ex-fuel 10.2¢, TRASM 15.6¢, load factor 84.4%, flota 166
- [ ] Load factor de 1Q25 = 82.3% verificado
- [ ] Invariantes en verde: `rpk <= ask`, `load_factor ≈ rpk/ask` (±0.5pp),
      `casm_ex_fuel < casm`
- [ ] **Tests de parser con al menos 3 trimestres congelados en fixtures**, en verde
- [ ] Ninguna métrica tiene `unit_normalized` nulo sin su `log_issue` correspondiente
- [ ] `silver/sec_report_text.parquet` con el texto completo de cada comunicado
- [ ] La fórmula de ajuste por stage length extraída del F-1 y documentada
- [ ] `silver/sec_crosscheck.parquet` con la comparación API vs documento
- [ ] Salida visual: serie de load factor, TRASM y CASM ex-fuel por trimestre, impresa

**No se cierra la etapa si:** los tests de parser no existen, o las cifras ancla no
coinciden sin explicación.

---

## Etapa 2 — BMV XBRL

**Obligatorio:**
- [ ] Mecanismo de acceso al portal BMV documentado en `docs/decisiones/`
- [ ] Todos los paquetes XBRL disponibles de AERO descargados (mínimo desde Q3 2025)
- [ ] Cobertura real de VOLAR verificada y documentada
- [ ] `silver/bmv_financials.parquet` poblada
- [ ] P&L cuadra internamente (±0.1%)
- [ ] `Assets = Liabilities + Equity` (±0.1%)
- [ ] Trimestres derivados de YTD suman el anual (±0.1%)
- [ ] Conciliación BMV ↔ SEC para al menos un trimestre común, con diferencias <1%
      o explicadas
- [ ] Catálogo completo de conceptos XBRL (incluyendo extensiones del emisor) en
      `docs/diccionario-conceptos-xbrl.md`
- [ ] Test con paquete XBRL congelado

---

## Etapa 3 — AFAC

**Obligatorio:**
- [ ] Nivel de escalada que funcionó, documentado
- [ ] `docs/afac-inventario.md` con inventario completo y familias de formato
- [ ] Cobertura mínima: **2015 a la fecha** (la historia previa es deseable, no obligatoria)
- [ ] `silver/afac_monthly_stats.parquet` poblada
- [ ] `data/reference/carrier_crosswalk.csv` versionado en git
- [ ] Suma de aerolíneas = fila TOTAL del archivo (±0.1%) en todos los periodos
- [ ] Correlación AFAC vs reportes de tráfico SEC de Aeroméxico **> 0.95**, con la
      diferencia sistemática cuantificada y explicada
- [ ] Lista de nombres sin mapear presentada al usuario
- [ ] Tests con al menos **2 familias de formato** distintas
- [ ] `docs/decisiones/decision-00X-acceso-afac.md` con instrucciones de actualización

**Pregunta obligatoria al usuario:**
- ¿"Aeroméxico" en el dashboard consolida Aeroméxico + Aeroméxico Connect, o los
  reporta por separado?

---

## Etapa 4 — Complementarias

**Obligatorio:**
- [ ] FX sin huecos en días hábiles desde 2015
- [ ] Jet fuel sin huecos en días hábiles desde 2015
- [ ] Precio de AERO desde 2025-11-06, **verificado que el ticker resuelve a Grupo
      Aeroméxico** y no a otro instrumento
- [ ] `gold/dim_airport.parquet` cubre el 100% de los aeropuertos que aparecen en
      fuentes de Aeroméxico y AFAC (excepciones documentadas)
- [ ] Tráfico de grupos aeroportuarios correlaciona >0.9 con el total AFAC
- [ ] `gold/dim_events.parquet` con **mínimo 15 eventos verificados con URL de fuente**
- [ ] **Estatus actual de la Categoría 1/2 de la FAA verificado en fuente primaria**
      (faa.gov / transportation.gov) y documentado con fecha de verificación
- [ ] Recolección de titulares funcionando, con sus limitaciones declaradas

---

## Etapa 5 — Peers

**Obligatorio:**
- [ ] Pipeline SEC generalizado por `carrier_key` con perfiles YAML
- [ ] CIKs de todos los peers **verificados** contra `company_tickers.json`
- [ ] Mínimo 8 trimestres de métricas operativas por peer implementado
- [ ] Ryanair: trimestres calendario reconstruidos cuadran con los fiscales (±1%)
- [ ] Delta: `companyfacts` XBRL cuadra con el 10-Q parseado (±0.1%)
- [ ] `silver/bts_t100_segment.parquet` con datos México–EE.UU. desde 2015
- [ ] **Validación T-100**: la proporción de ASM de Aeroméxico en rutas EE.UU. sobre
      sus ASM internacionales totales es estable trimestre a trimestre
- [ ] Todos los `carrier` de T-100 relevantes mapeados en el crosswalk
- [ ] `docs/peers-comparabilidad.md` con la matriz y las definiciones literales de
      cada aerolínea, extraídas de sus propios filings
- [ ] Recomendación explícita sobre incluir IAG y sobre agregar Copa/LATAM/Gol/Azul

---

## Etapa 6 — Tablas maestras

**Obligatorio:**
- [ ] Todas las tablas gold con contrato de esquema declarado y validado
- [ ] Cero `carrier_key` nulos en fuentes principales (o excepciones documentadas)
- [ ] Invariantes de negocio en verde sobre **toda** la tabla gold
- [ ] Load factor derivado vs reportado: diferencia <0.5 pp en **>95%** de las filas
- [ ] Suma de trimestres = anual (±0.1%)
- [ ] Ajuste por stage length implementado con la fórmula del prospecto
- [ ] Conversiones de moneda con el tipo correcto (promedio para P&L, cierre para balance)
      y `fx_rate_used` registrado en cada fila
- [ ] `dim_metric` con interpretación de negocio poblada al **100%** para toda métrica
      que el dashboard mostrará
- [ ] Todas las vistas de consumo creadas y documentadas
- [ ] `docs/diccionario-datos.md` generado automáticamente, sin errores
- [ ] **`just rebuild` reconstruye todo desde bronze SIN RED y produce resultados
      idénticos** (verificado con hash de las tablas gold)
- [ ] La cifra ancla de 1Q26 se consulta correctamente desde `v_aeromexico_quarterly`
- [ ] Decisión sobre BigQuery documentada

---

## Etapa 7 — Analítica

**Obligatorio:**
- [ ] EDA completo con `docs/analytics/eda-hallazgos.md`
- [ ] **Todo modelo publicado supera a su baseline** (naive estacional) en test
- [ ] Ninguna métrica de desempeño reportada sobre el conjunto de entrenamiento
- [ ] **Todos los forecasts tienen intervalos de predicción**
- [ ] Sin data leakage: verificado que ninguna feature usa información futura
- [ ] Cada cluster tiene nombre de negocio **validado por el usuario**
- [ ] Silueta reportada y elección de k justificada
- [ ] Análisis de lenguaje con sus advertencias de limitación explícitas
- [ ] Los **7 análisis de alto valor** de `09-etapa-7-analitica.md` §6 implementados,
      cada uno con un hallazgo escrito en lenguaje de negocio
- [ ] Reproducibilidad: semillas fijas, `model_run_id`, metadata guardada
- [ ] `docs/analytics/hallazgos.md` en español, sin jerga

**Si ningún modelo supera al baseline para una métrica:** eso se reporta y esa métrica
**no** lleva forecast en el dashboard. Es un resultado válido.

---

## Etapa 8 — Dashboard

**Obligatorio:**
- [ ] Las 10 páginas implementadas
- [ ] **Toda métrica mostrada tiene su interpretación de negocio visible** (requisito
      explícito del usuario)
- [ ] Ningún forecast se muestra sin banda de incertidumbre **y sin su MAPE de test**
- [ ] Advertencias de comparabilidad visibles en la página de competencia
      (IFRS vs US-GAAP, año fiscal de Ryanair, stage length)
- [ ] Página de salud de datos refleja el estado real de `data_quality_issues`
- [ ] Anotaciones de eventos funcionando en las series temporales
- [ ] **El dashboard carga y funciona sin conexión a internet**
- [ ] Carga inicial <3s, cambio de página <1s
- [ ] Contraste de color AA verificado
- [ ] Colores consistentes por aerolínea en todo el dashboard
- [ ] Semántica de color respeta `dim_metric.higher_is_better`
- [ ] Disclaimer de "no es consejo de inversión" y "proyecto independiente, no oficial"
      en el pie
- [ ] `.github/workflows/refresh.yml` funcionando, con apertura de issue si la
      validación falla
- [ ] El workflow detecta y avisa cuando una fuente manual (AFAC) está desactualizada
- [ ] Deploy público funcionando, URL en el README
- [ ] Recorrido narrado del dashboard como pieza de portafolio

---

## Checklist transversal (aplica a todas las etapas)

- [ ] Ningún dato inventado, estimado sin marcar, o rellenado para que cuadre
- [ ] Todo lo que falló está documentado con su razón
- [ ] Todo supuesto está explícito
- [ ] Las decisiones de negocio se consultaron con el usuario, no se tomaron solas
- [ ] El código nuevo tiene tests
- [ ] `git commit` con mensaje descriptivo al cerrar la etapa
- [ ] El reporte de etapa está escrito **antes** de presentar al usuario
