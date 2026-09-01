# Plan de Implementación — Dashboard Analítico de Grupo Aeroméxico

Este directorio contiene el plan completo de implementación de un dashboard analítico
trimestral sobre Grupo Aeroméxico (ticker **AERO**, NYSE + BMV), pensado para ser
ejecutado por un agente de código (Claude Code) con acceso a terminal, sistema de
archivos y computer use.

**Este plan NO es un one-shot.** Está dividido en etapas con gate humano. Al final de cada etapa el
agente se detiene, presenta entregables y espera aprobación explícita del usuario.

---

## Cómo usar este plan

1. Copiar todo este directorio a la raíz del repositorio del proyecto, en `docs/plan/`.
2. Abrir Claude Code en la raíz del repo.
3. Ejecutar `/goal` y pegar el contenido de `GOAL.md`.
4. El agente leerá `README.md` → `00-contexto-y-principios.md` → `01-arquitectura-y-convenciones.md`
   y luego la etapa que corresponda.

---

## Índice de archivos

| Archivo | Qué contiene | Cuándo leerlo |
|---|---|---|
| `GOAL.md` | El prompt exacto para `/goal` | Al arrancar |
| `00-contexto-y-principios.md` | Contexto de negocio, quién es el usuario, principios de trabajo no negociables | Siempre, primero |
| `01-arquitectura-y-convenciones.md` | Arquitectura bronze/silver/gold, estructura de carpetas, convenciones de nombres, logging, manejo de secretos | Siempre, segundo |
| `02-etapa-0-setup.md` | Etapa 0 — entorno, dependencias, autorizaciones, esqueleto del repo | Etapa 0 |
| `03-etapa-1-sec-edgar.md` | Etapa 1 — SEC EDGAR: descubrimiento de filings, descarga de 6-K/20-F, parseo de métricas operativas del comunicado trimestral | Etapa 1 |
| `04-etapa-2-bmv-xbrl.md` | Etapa 2 — BMV/CNBV: XBRL trimestral estructurado (estados financieros) | Etapa 2 |
| `05-etapa-3-afac.md` | Etapa 3 — AFAC: estadística mensual por aerolínea (requiere computer use) | Etapa 3 |
| `06-etapa-4-complementarias.md` | Etapa 4 — Banxico, EIA/FRED, yfinance, OurAirports/OpenFlights, grupos aeroportuarios, DATATUR | Etapa 4 |
| `07-etapa-5-peers.md` | Etapa 5 — Volaris, Viva Aerobus, Ryanair, Delta, IAG + BTS T-100 | Etapa 5 |
| `08-etapa-6-tablas-maestras.md` | Etapa 6 — modelo dimensional, conciliación de entidades, normalizaciones, SCD2, capa gold | Etapa 6 |
| `09-etapa-7-analitica.md` | Etapa 7 — forecast, clustering, análisis de lenguaje de los reportes, detección de anomalías | Etapa 7 |
| `10-etapa-8-dashboard.md` | Etapa 8 — Streamlit + ECharts, narrativa de negocio, despliegue | Etapa 8 |
| `14-etapa-9-saneamiento-backend.md` | Etapa 9 — orquestación, linaje, calidad y contratos | Etapa 9 |
| `11-glosario-kpis.md` | Glosario completo de KPIs con fórmula, fuente e interpretación de negocio. **Es el insumo de texto del dashboard.** | Etapas 1, 6, 7, 8 |
| `12-computer-use-playbook.md` | Cómo y cuándo usar computer use, reglas de seguridad, procedimientos por sitio | Etapas 1, 3, 5, 7 |
| `13-criterios-de-aceptacion.md` | Definition of Done por etapa, checklist de validación, cifras ancla para verificar | Al cerrar cada etapa |

---

## Protocolo de etapas (obligatorio)

```
Para cada etapa N:
  1. Leer 00, 01 y el archivo de la etapa N completos antes de escribir código.
  2. Escribir un plan de ataque corto (10-20 líneas) y mostrarlo.
  3. Implementar.
  4. Ejecutar la suite de validación de la etapa (ver 13-criterios-de-aceptacion.md).
  5. Escribir docs/etapas/etapa-N-reporte.md con:
     - qué se construyó
     - qué se descargó (conteos, rangos de fechas, tamaños)
     - qué se validó y contra qué cifra ancla
     - qué NO funcionó y por qué
     - decisiones tomadas y supuestos
     - riesgos abiertos para la siguiente etapa
  6. Presentar al usuario un resumen ejecutivo en el chat.
  7. DETENERSE. Esperar la palabra "go" (o equivalente) del usuario.
  8. No empezar la etapa N+1 sin esa aprobación.
```

**Regla de oro:** la Etapa 0 y la Etapa 1 deben quedar impecables antes de avanzar.
Si algo de la Etapa 1 queda a medias, no se avanza; se reporta y se pide instrucción.

---

## Mapa de etapas

| Etapa | Nombre | Objetivo | Duración estimada |
|---|---|---|---|
| 0 | Setup | Entorno reproducible, repo, deps, secretos | 1 sesión |
| 1 | SEC EDGAR | Filings + métricas operativas trimestrales de AERO | 2-3 sesiones |
| 2 | BMV XBRL | Estados financieros estructurados | 1-2 sesiones |
| 3 | AFAC | Estadística mensual por aerolínea (México) | 2-3 sesiones |
| 4 | Complementarias | FX, combustible, bolsa, dimensiones, aeropuertos | 1-2 sesiones |
| 5 | Peers | Volaris, Viva, Ryanair, Delta, IAG + BTS T-100 | 2-3 sesiones |
| 6 | Tablas maestras | Capa gold, normalización, comparabilidad | 2-3 sesiones |
| 7 | Analítica | Forecast, clustering, NLP de reportes | 2-3 sesiones |
| 8 | Dashboard | Streamlit + ECharts + narrativa | 3-4 sesiones |
| 9 | Saneamiento backend | Orquestación, linaje, calidad, contratos y modelo Gold | 2-3 sesiones |

---

## Advertencia sobre datos

Toda cifra que este plan cita como "ancla de validación" proviene de una investigación
previa y **debe reverificarse contra la fuente primaria** durante la ejecución. Si una
cifra ancla no coincide con lo que el agente descarga, eso es una señal de que la fuente
cambió, no de que el agente deba forzar el resultado. Reportarlo, no ajustarlo.
