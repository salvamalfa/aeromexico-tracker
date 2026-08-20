# Etapa 1 — SEC EDGAR

Fecha de cierre: 2026-08-20
Estado: COMPLETA

## Qué se construyó

- Descubrimiento completo de filings desde `submissions`, con validación de arrays
  columnares, URLs canónicas y reconstrucción offline desde bronze.
- Descarga inmutable de índices y documentos no gráficos para todos los 6-K, el
  20-F FY2025 y todas las versiones F-1/F-1/A.
- Clasificación de 6-K con tipo principal, tags múltiples y confianza. Esto evita
  perder que un mismo 6-K puede contener earnings y varios reportes de tráfico.
- Parser de earnings basado en etiquetas y encabezados de periodo, no posiciones.
- Parser de tráfico mensual por segmento doméstico, internacional y total.
- Extracción de P&L, KPIs no IFRS, métricas operativas, flota, texto completo,
  definiciones y evolución de la fórmula de stage length.
- Crosscheck entre `companyfacts` y el 20-F, y entre earnings trimestrales y la suma
  de reportes mensuales.
- Validador de cifras ancla, contratos, duplicados, linaje e invariantes.
- Serie imprimible de load factor, TRASM y CASM ex-fuel.
- Cinco fixtures SEC exactos: cuatro earnings trimestrales y un reporte mensual.

## Datos obtenidos

| Fuente | Periodos / cobertura | Filas o documentos | Tamaño | Método de acceso |
|---|---|---:|---:|---|
| SEC `submissions` | Snapshot 2026-08-20 | 62 filings | 11,107 bytes | httpx |
| SEC `companyfacts` | Snapshot 2026-08-20 | 1 concepto `dei` | 802 bytes | httpx |
| SEC Archives | 19 filings relevantes | 322 artefactos lógicos | 146,459,333 bytes | httpx |
| `sec_filings_index.parquet` | Todos los filings | 62 | 16,477 bytes | offline desde bronze |
| `sec_filing_documents.parquet` | 19 filings | 322 | 42,465 bytes | offline desde bronze |
| `sec_operating_metrics.parquet` | 2024Q3–2026Q2 + 14 meses observados | 261 | ~15 KB | parser HTML |
| `sec_financials.parquet` | 2024Q3–2026Q2 | 215 | ~22 KB | parser HTML/texto |
| `sec_report_text.parquet` | 4 earnings + 7 tráfico | 11 / 27,532 palabras | ~73 KB | BeautifulSoup |
| `sec_reference_text.parquet` | 6 prospectos + 20-F | 20 | ~4.3 MB | BeautifulSoup |
| `sec_crosscheck.parquet` | 2025, 2025Q1–2026Q2 | 17 | ~7 KB | cálculo offline |

La descarga SEC ocupa 147,247,265 bytes físicos en bronze. Hay 325 registros de
manifiesto en total: el catálogo de tickers de Etapa 0 y 324 registros añadidos en
esta etapa. No hubo restatements de bytes.

### Inventario de filings

- 12 formularios 6-K: 4 earnings, 4 governance y 4 material events.
- Tres 6-K de earnings también contienen reportes de tráfico; se preservan ambos
  tags. En total hay siete exhibits mensuales: octubre de 2025 y enero–junio de 2026.
- Un 20-F FY2025.
- Un F-1 y cinco F-1/A, incluidas todas las versiones del prospecto del IPO.
- 43 filings adicionales de propiedad, registro, listing y documentación relacionada.
- No existen páginas históricas adicionales en `filings.files` para este emisor.

### Cobertura de métricas

- 100% de los ocho trimestres para ASM, RPM, load factor, pasajeros, TRASM, PRASM,
  CASM, CASM ex-fuel, yield, combustible y puntualidad.
- Flota: cinco de ocho trimestres (62.5%); solo se publica en las tablas recientes.
- 25 líneas financieras reportadas para cada uno de los ocho trimestres. Nueve
  valores permanecen `NULL` porque la fuente muestra un guion largo, principalmente
  impairment/equity investees; no se convirtieron artificialmente en cero.
- Cinco métricas adicionales conservan por separado los valores que Aeroméxico
  etiqueta como `Normalized` en 3Q25/4Q25.

## Validaciones ejecutadas

| Check | Resultado | Detalle |
|---|---|---|
| Suite completa | PASS | 48 tests; 5 fixtures SEC reales |
| Companyfacts | PASS | Solo `dei`, 1 concepto; sin `ifrs-full` ni `us-gaap` |
| Clasificación | PASS | 62/62 filings con tipo; sin `unknown` |
| Filings requeridos | PASS | Todos los 6-K y todos los F-1/F-1/A/20-F descargados |
| Contrato silver | PASS | Tipos, unidades y linaje completos |
| Claves naturales | PASS | Cero duplicados en métricas operativas/financieras |
| Unidades | PASS | Cero `unit_normalized` nulos |
| Periodos trimestrales | PASS | Ocho trimestres continuos, 2024Q3–2026Q2 |
| RPM <= ASM | PASS | 8/8 observaciones |
| Load factor ≈ RPM/ASM | PASS | 8/8 dentro de ±0.5 pp |
| CASM ex-fuel < CASM | PASS | 8/8 observaciones |
| TRASM y CASM positivos | PASS | Cero fallos |
| Crosscheck | PASS | 17 comparaciones, cero diferencias materiales >1% |
| API vs documento | PASS | 1,459,034,090 acciones en ambos, diferencia cero |
| Idempotencia | PASS | Dos parseos offline; hashes idénticos en 7 Parquet |

## Cifras ancla verificadas

| Métrica | Esperado | Obtenido | ¿Coincide? |
|---|---:|---:|---:|
| Ingreso total 1Q26 | 1,341 M USD | 1,341.0 M USD | Sí |
| EBITDAR ajustado 1Q26 | 335.8 M USD | 335.8 M USD | Sí |
| Margen EBITDAR 1Q26 | 25.0% | 25.0% | Sí |
| Utilidad operativa 1Q26 | 141.8 M USD | 141.8 M USD | Sí |
| Margen operativo 1Q26 | 10.6% | 10.6% | Sí |
| CASM ex-fuel 1Q26 | 10.2 ¢/ASM | 10.2 ¢/ASM | Sí |
| TRASM 1Q26 | 15.6 ¢/ASM | 15.6 ¢/ASM | Sí |
| Load factor 1Q26 | 84.4% | 84.4% | Sí |
| Flota 1Q26 | 166 | 166 | Sí |
| Pasajeros 1Q26 | ~5.8 M | 5.791 M | Sí |
| Load factor 1Q25 | 82.3% | 82.3% | Sí |
| Acciones al 2025-12-31 | 1,459,034,090 | 1,459,034,090 | Sí |

## Qué NO funcionó y por qué

- `companyfacts` sigue prácticamente vacío. Aunque el 20-F contiene inline XBRL,
  el agregador solo expone `dei:EntityCommonStockSharesOutstanding`. Por ello no es
  fuente primaria de financieros trimestrales.
- La primera clasificación concatenó HTML completos antes de extraer texto; el
  parser HTML solo veía el primer árbol y los 12 6-K quedaban como material events.
  Se corrigió extrayendo cada documento por separado y se añadió cobertura de tests.
- Hubo un error transitorio de transporte durante la descarga. El retry autorizado
  lo resolvió sin pérdida ni descarga manual.
- El 4Q25 mezcla valores reportados y `Normalized`. Una primera regex seleccionó el
  operating income normalizado de 236.4 M USD. Se corrigió para conservar el valor
  reportado de 303.1 M USD y guardar las métricas normalizadas con claves separadas.
- SEC no contiene exhibits mensuales separados para noviembre y diciembre de 2025.
  Se dejaron ausentes; no se estimaron ni se rellenaron.
- La primera salida de `sec-series` usaba el formato tabular Unicode de Polars y
  fallaba en consolas Windows CP-1252. Se cambió a CSV ASCII y se añadió una prueba.
- El plan citaba 1,834 km como referencia de stage length. Eso es correcto para el
  F-1 original, pero no para el prospecto final; ver la decisión 003.

No se necesitó Playwright, navegador visible ni computer use en esta etapa.

## Decisiones tomadas

- Descargar todos los documentos HTML/PDF/XML/TXT/JSON de los 19 filings relevantes,
  excluyendo únicamente gráficos.
- Conservar todas las versiones del F-1/F-1/A para auditar cambios de definición.
- Usar tags múltiples a nivel filing porque earnings y tráfico comparten 6-K.
- Preservar ASM/RPM en millas, tal como lo declara SEC; la conversión va en gold.
- Mantener guiones de la fuente como `NULL`, nunca como cero inferido.
- Separar métricas `company_normalized` de las cifras reportadas.
- Registrar en el manifiesto URLs alternativas cuando dos fuentes entregan bytes
  idénticos, sin duplicar el archivo físico.
- Usar 1,982 km para reproducir el F-1/A final, con vigencia y accession explícitos.

## Supuestos hechos

- `Total revenue / ASM` se modela como `trasm`; `Total cost / ASM` como `casm`.
- Los estados trimestrales marcados `Unaudited` conservan `is_preliminary = true`.
- Los comparativos del mismo trimestre del año anterior son niveles, no variaciones;
  por ello `is_yoy_comparison = false`.
- Un guion largo en una línea financiera significa “sin valor numérico publicado”,
  no necesariamente cero.

## Preguntas para el usuario

Ninguna pendiente para cerrar la Etapa 1.

## Riesgos para la siguiente etapa

- BMV deberá validar las líneas financieras SEC y explicar diferencias por redondeo,
  normalizaciones no IFRS o presentación acumulada YTD.
- La descarga de la página BMV probada en Etapa 0 no garantiza todavía acceso a sus
  paquetes XBRL.
- Las extensiones XBRL del emisor pueden requerir parseo directo si una herramienta
  general no resuelve la taxonomía CNBV.
- Las métricas de flota anteriores a 2Q25 siguen incompletas en los earnings SEC.

## Comandos para reproducir

```powershell
just ingest          # red: refresca SEC y preserva bronze
just parse           # sin red: bronze -> silver
just sec-validate    # anclas, invariantes, contratos y crosscheck
just sec-series      # load factor, TRASM y CASM ex-fuel
just test
just rebuild         # parse SEC offline + transformaciones registradas
```
