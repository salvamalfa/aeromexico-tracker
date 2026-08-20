# Etapa 3 — AFAC

Fecha de cierre: 2026-08-20
Estado: COMPLETA

## Qué se construyó

- Ingesta AFAC/DATATUR con validación estricta de host, extensión, magic bytes,
  tamaño y seguridad del ZIP; toda respuesta inesperada se conserva antes de fallar.
- Escalada reproducible desde HTTP hacia navegador integrado para los adjuntos de
  gob.mx protegidos por challenge.
- Serie anual oficial completa 1992–2025 y boletines DATATUR 2024M01–2026M06 en
  bronze inmutable.
- Parser multi-formato para libros BIFF `.xls`, OOXML `.xlsx`, boletines PDF y la
  base larga DATATUR.
- `afac_monthly_stats.parquet` con pasajeros mensuales 2015M01–2026M06 y linaje por
  fila hasta el archivo y hash de origen.
- Crosswalk versionado con entidades separadas para Aeroméxico, Connect, Volaris,
  Viva, Mexicana histórica/nueva y otros operadores mexicanos relevantes.
- Vista de negocio predeterminada consolidada **Aeroméxico + Aeroméxico Connect**,
  sin perder el desglose individual en silver.
- Inventario completo, ADR de acceso, reconciliación AFAC–SEC, cola de nombres sin
  mapear, validador offline y fixtures reales de dos familias Excel.

## Datos obtenidos

| Fuente | Periodos | Archivos / filas | Tamaño | Método |
|---|---|---:|---:|---|
| Libros anuales AFAC | 1992–2025 | 34 archivos | 6,873,654 bytes | HTTP + computer use |
| Boletines DATATUR/AFAC | 2024M01–2026M06 | 30 PDF | 8,111,561 bytes | HTTP |
| Base DATATUR | 2016M01–2026M06 | ZIP + XLSX | 1,516,581 bytes | HTTP |
| Descubrimiento, catálogos y respuestas preservadas | varios | 12 archivos | 773,002 bytes | HTTP + Playwright |
| Bronze AFAC total | 1992–2026M06 | 78 archivos físicos | 17,274,798 bytes | Mixto |
| `afac_monthly_stats.parquet` | 2015M01–2026M06 | 14,962 filas | 84,113 bytes | Parser offline |

La tabla silver cubre 138 meses consecutivos: 14,322 filas provienen de libros
anuales, 450 de boletines 2026 y 190 de fletamento en la base larga. No se concatenan
fuentes solapadas.

## Validaciones ejecutadas

| Check | Resultado | Detalle |
|---|---|---|
| Suite completa | PASS | 59 tests en 2.63 s |
| Familias de fixture | PASS | Libro oficial 1992 `.xls` y 2015 `.xlsx`, byte-identical |
| Integridad bronze AFAC | PASS | 78/78 archivos físicos coinciden con SHA-256 del manifiesto |
| Cobertura analítica | PASS | 138/138 meses, 2015M01–2026M06; cero huecos |
| TOTAL de fuente | PASS | 684/684 bloques-mes; diferencia relativa máxima 0.0000% |
| Clave natural silver | PASS | Cero duplicados |
| Valores | PASS | Cero negativos y cero nulos en `value` |
| Notas de estimación | PASS | Dos filas marcadas y ambas con texto de fuente |
| AFAC ↔ SEC | PASS | 14 meses; correlación 0.999303 > 0.95 |
| Diferencia sistemática | Documentada | AFAC -28,895 pasajeros/mes; -1.4497% promedio |
| Reconstrucción offline | PASS | Dos parseos; SHA-256 silver idéntico `124de950…bb98f` |

Los 672 controles de libros 2015–2025 y los 12 controles de PDF 2026 comparan la
suma de aerolíneas con la fila TOTAL de **ese mismo archivo**. No se ajustó el parser
para hacer coincidir cifras externas.

## Crosswalk y nombres sin mapear

El crosswalk resuelve 11 entidades canónicas observadas mediante 16 alias/versiones.
Quedan **229 nombres de fuente sin mapear**: 10 de aerolíneas mexicanas y 219 de
aerolíneas extranjeras. Las 12,178 filas afectadas permanecen en silver con
`carrier_key = NULL`; ninguna se descartó. La lista completa, con primer/último
periodo y conteo, está en `data/quality/afac_unmapped_carriers.csv`.

Esta cola no impide calcular el mercado total ni la participación de Aeroméxico,
Volaris o Viva. Sí debe revisarse antes de análisis por grupo internacional o de
fusiones/rebrandings fuera del alcance de esta etapa.

## Qué NO funcionó y por qué

- gob.mx devolvió un HTML de Akamai `Challenge Validation` al pedir directamente
  algunos Excel, aun con HTTP 200. La respuesta se rechazó por magic bytes y se
  preservó cruda.
- Playwright headless no superó ese challenge. El flujo visible desde la página
  oficial sí permitió descargar mediante clic normal.
- La base DATATUR actual y algunos PDF mensuales 2026 no son la misma versión: la
  base ya contiene revisiones posteriores. Por eso se definió precedencia por tipo
  de servicio y no se mezclaron snapshots.
- El boletín gratuito no publica fletamento; ese segmento 2026 usa la base larga y
  conserva el `source_family` correspondiente.
- No se mapearon automáticamente 229 nombres: inventar consolidaciones corporativas
  habría sido peor que conservar nulos explícitos para revisión.

No fue necesario instalar paquetes adicionales.

## Decisiones tomadas

- Consolidar Aeroméxico + Connect solo en la vista analítica predeterminada; silver
  mantiene ambas entidades separadas.
- Tomar libros anuales 2015–2025, PDF contemporáneos para regular 2026 y base larga
  para fletamento 2026.
- Tratar 2025 y 2026 como preliminares; conservar como estimadas Magnicharters marzo
  2026 y Spirit abril 2026 con la nota exacta de la fuente.
- Sumar filas DATATUR que compartan clave natural y registrar `source_row_count` para
  no perder el hecho de que la fuente puede contener múltiples renglones subyacentes.
- Mantener bronze, silver y quality fuera de git; versionar código, documentación,
  crosswalk y fixtures mínimos.

## Supuestos hechos

- La página oficial visible 1992–2025 y el catálogo DATATUR representan el universo
  público disponible por esos puntos de acceso al 2026-08-20.
- La fila TOTAL del mismo archivo es el ancla primaria del parser; los solapes entre
  versiones sirven para QA, no para sobrescribir una publicación.
- La diferencia estable AFAC–SEC refleja perímetro y redondeo porque no hay evidencia
  de error de escala, mes o consolidación después de sumar AM + Connect.

## Preguntas para el usuario

Ninguna pendiente para cerrar la Etapa 3. La decisión obligatoria quedó resuelta:
la vista predeterminada consolida Aeroméxico + Connect y el dato base los conserva
por separado.

## Riesgos para la siguiente etapa

- Un nuevo libro anual de gob.mx puede requerir de nuevo navegador visible y una
  actualización explícita del inventario de URL/nombre.
- Los 229 nombres sin mapear limitan agrupaciones corporativas de aerolíneas no
  mexicanas hasta que se amplíe el crosswalk.
- Las cifras recientes son preliminares y pueden restatarse; el mecanismo bronze
  inmutable detectará hashes nuevos, pero el dashboard debe mostrar fecha de corte.
- La Etapa 4 deberá comparar totales de aeropuertos con AFAC sin asumir perímetros
  idénticos.

## Comandos para reproducir

```powershell
python -m src.ingest.afac.download
python -m src.parse.afac.monthly_stats
python -m src.parse.afac.validate
python -m pytest
```
