# Etapa 2 — BMV / CNBV: XBRL Financiero Estructurado

**Objetivo:** obtener los estados financieros trimestrales de Aeroméxico (y Volaris) en
formato XBRL estructurado, gratuito, desde la Bolsa Mexicana de Valores. Esta es la
fuente **trazable y auditable** de financieros, que compensa el vacío del XBRL de la SEC.

---

## 1. La fuente

### Portal BMV
`https://www.bmv.com.mx/es/emisoras/archivos-estadar-xbrl`

- Tabla filtrable por **clave de emisora**, **periodicidad** y **año**
- Cada fila tiene un enlace de descarga → un `.zip` con el paquete XBRL
- XBRL obligatorio para emisoras BMV desde **Q1 2016**, bajo taxonomías **IFRS de la CNBV**

### Cobertura confirmada para AERO
| Periodo | Fecha de presentación |
|---|---|
| Q3 2025 | 12/11/2025 |
| Q4 2025 | — |
| Reporte Anual XBRL 2025 | — |
| Q1 2026 | 21/04/2026 |
| Q2 2026 | 13/07/2026 |

> La historia empieza en **Q3 2025** porque Aeroméxico fue delistado de BMV en 2022 y
> relistado en noviembre de 2025. **No esperes historia larga aquí.** La profundidad
> histórica viene del F-1 del IPO (Etapa 1) y de AFAC/BTS (Etapas 3 y 5).

### Volaris (VOLAR)
Emisor continuo, por lo que debería tener historia desde 2016. **Verificar fila por fila** —
la investigación previa no lo confirmó exhaustivamente. Si está, es una serie larga y
valiosa para comparación.

### Viva Aerobus
No cotiza acciones pero es emisor de deuda (Cebures) en BMV/BIVA. Reporta trimestralmente
bajo IFRS y **cambió su moneda funcional a USD** para cumplir con la CNBV. Sus reportes
están en `https://ri.vivaaerobus.com` (incluyendo un "XBRL Report"). Ver Etapa 5.

### CNBV STIV-2 (alternativa/respaldo)
`https://stivconsultasexternas.cnbv.gob.mx/` — tiene un "Visor de Información Financiera
XBRL". Los emisores presentan simultáneamente a BMV (vía Emisnet) y a CNBV (vía STIV-2),
así que es la misma información por otro canal. Usar como fallback si BMV bloquea.

> **No confundir:** el "Portafolio de Información" de la CNBV
> (`portafolioinfo.cnbv.gob.mx`) es **solo para instituciones financieras reguladas**
> (bancos). NO contiene emisoras como AERO o VOLAR. No perder tiempo ahí.

### Referencia de implementación existente
`https://github.com/emhlaos/bmv-scrapper` — proyecto Python con `XbrlZipDownloader`,
`XbrlParser`, `XbrlReader`. **Leerlo antes de escribir código propio.** Puede servir
como referencia de la estructura del zip y de los nombres de taxonomía, aunque
probablemente convenga escribir una implementación propia y mantenida.

## 2. Sub-etapa 2A — Acceso al portal

**Módulo:** `src/ingest/bmv/download.py`

1. Intentar acceso con `httpx`. El portal es probablemente una app con POST/AJAX para
   filtrar la tabla; inspeccionar la petición real.
2. Si hay anti-bot o la tabla se renderiza con JavaScript → **Playwright**.
3. Si Playwright falla → **computer use** (ver archivo 12, procedimiento BMV).

**Rate limit:** 1 request cada 2 segundos. No martillar el portal.

### Lo que hay que descubrir y documentar
- ¿Cuál es el endpoint real que alimenta la tabla?
- ¿Cómo se construye la URL de descarga de cada zip?
- ¿Hay un patrón de URL predecible por (clave, año, trimestre)?

Si hay un patrón predecible, la ingesta futura se vuelve trivial. **Documentarlo en
`docs/decisiones/decision-00X-acceso-bmv.md`.**

## 3. Sub-etapa 2B — Estructura del paquete XBRL

Un paquete XBRL de la CNBV típicamente contiene:
- Un **instance document** (`.xml`) con los hechos
- **Schemas** (`.xsd`) de la extensión del emisor
- **Linkbases** (presentation, calculation, label, definition)

Tareas:
1. Descomprimir a `data/bronze/bmv/xbrl/{ticker}/{periodo}/` preservando el zip original
2. Identificar el instance document
3. Extraer el **linkbase de etiquetas en español e inglés** — esto da los nombres
   legibles de cada concepto, que sirven directo para el dashboard
4. Extraer el **linkbase de presentación** — da la jerarquía de los estados financieros
   (qué es subtotal de qué), esencial para reconstruir el P&L correctamente

## 4. Sub-etapa 2C — Parseo del XBRL

**Módulo:** `src/parse/bmv/xbrl.py`

Opciones, en orden de preferencia:
1. **Parseo directo del XML** con `lxml` — el instance document es plano y manejable
2. `arelle` — completo pero pesado; usarlo si se necesita validación formal de la
   taxonomía o resolución compleja de dimensiones
3. `python-xbrl` — más simple, puede quedarse corto con dimensiones

### Conceptos clave a extraer (taxonomía `ifrs-full`)
| Concepto IFRS | Significado |
|---|---|
| `Revenue` | Ingresos totales |
| `RevenueFromRenderingOfServices` | Ingresos por servicios |
| `CostOfSales` | Costo de ventas |
| `GrossProfit` | Utilidad bruta |
| `ProfitLossFromOperatingActivities` | Utilidad operativa |
| `ProfitLoss` | Utilidad neta |
| `Assets`, `Liabilities`, `Equity` | Balance |
| `CashAndCashEquivalents` | Efectivo |
| `PropertyPlantAndEquipment` | Activo fijo (flota propia) |
| `RightofuseAssets` | Activos por derecho de uso (IFRS 16 — leasing de aviones, **crítico**) |
| `LeaseLiabilities` | Pasivos por arrendamiento |
| `CashFlowsFromUsedInOperatingActivities` | Flujo operativo |
| `DepreciationAndAmortisationExpense` | D&A |
| `FinanceCosts` | Costos financieros |

Más los **conceptos de extensión del emisor** (namespace propio de Aeroméxico), que
suelen contener el desglose específico de aerolínea (combustible, gastos aeroportuarios,
mantenimiento). **Enumerarlos todos y documentarlos**, no asumir cuáles existen.

### Manejo de dimensiones XBRL
Los hechos pueden estar dimensionados (por segmento, por moneda, por tipo). Extraer los
ejes y miembros y guardarlos:
```
concept, dimension_axis, dimension_member, value, unit, decimals,
context_period_type, period_start, period_end, is_consolidated
```

### Manejo de contextos
Cada hecho tiene un contexto que define **periodo** (instant vs duration) y **entidad**.
Crítico distinguir:
- `duration` con periodo trimestral → el trimestre en sí
- `duration` con periodo acumulado (YTD) → **no confundir con el trimestre**
- `instant` → saldos de balance

**Regla:** derivar el trimestre puro cuando la fuente solo publica acumulado
(`Q2 = YTD_H1 - Q1`) y marcar la fila con `is_derived = true`.

### Esquema de salida: `silver/bmv_financials.parquet`
```
carrier_key, ticker, period_id, period_type, period_start_date, period_end_date,
taxonomy, concept, concept_label_es, concept_label_en,
dimension_axis, dimension_member,
value, unit, currency, decimals, scale,
statement_type, presentation_order, parent_concept,
is_derived, is_ytd,
source_system, source_file, source_hash, ingested_at, parser_version
```

## 5. Sub-etapa 2D — Conciliación BMV ↔ SEC

Comparar, para los mismos periodos, las cifras de `silver/bmv_financials.parquet`
contra `silver/sec_financials.parquet` (parseadas del comunicado en la Etapa 1).

**Deberían coincidir** (misma compañía, mismo IFRS, misma moneda USD). Si no coinciden:
- Verificar si una es consolidada y la otra no
- Verificar si una es YTD y la otra trimestral
- Verificar si hay reexpresión entre la fecha de publicación del comunicado y la
  presentación regulatoria

Toda diferencia material (>1%) → `log_issue` + fila en `silver/bmv_sec_reconciliation.parquet`.

**Esta reconciliación es un entregable en sí mismo.** Demuestra rigor y alimenta el
panel de "salud de datos" del dashboard.

## 6. Validación de la Etapa 2

- Se descargaron todos los paquetes XBRL disponibles para AERO (mínimo: Q3 2025 en adelante)
- Se verificó y documentó la cobertura real de VOLAR
- El P&L reconstruido del XBRL cuadra internamente:
  `ingresos - costos - gastos = utilidad operativa` (±0.1%)
- `Assets = Liabilities + Equity` (±0.1%)
- La conciliación BMV ↔ SEC para al menos un trimestre común muestra diferencias <1%,
  o las diferencias están explicadas y documentadas
- Test con un paquete XBRL congelado en fixtures

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| Portal BMV con anti-bot | Playwright → computer use |
| Cambio de taxonomía entre años | Guardar el `.xsd` de cada paquete; mapear conceptos por año |
| Conceptos de extensión sin etiqueta legible | Extraer del label linkbase; si falta, documentar como desconocido |
| Confusión trimestre vs YTD | Validar que la suma de trimestres = anual |
| Historia muy corta para AERO | Aceptado; se compensa con F-1, AFAC y BTS |

---

## Entregables de la Etapa 2

1. `src/ingest/bmv/download.py` + `src/parse/bmv/xbrl.py`
2. Paquetes XBRL en bronze, descomprimidos y con meta
3. `silver/bmv_financials.parquet`
4. `silver/bmv_sec_reconciliation.parquet`
5. `docs/decisiones/decision-00X-acceso-bmv.md` con el mecanismo de acceso descubierto
6. Catálogo completo de conceptos encontrados (incluyendo extensiones del emisor) en
   `docs/diccionario-conceptos-xbrl.md`
7. Tests con fixture
8. `docs/etapas/etapa-2-reporte.md`

**Detenerse y esperar "go".**
