# Etapa 9 — Saneamiento del backend

Fecha de cierre: 2026-09-01
Estado: COMPLETA

## Resumen técnico

La Etapa 9 cerró las brechas P0 y P1 de orquestación, reproducibilidad, contratos,
SCD2, calidad y linaje sin cambiar las cifras de negocio. El pipeline se reconstruyó
dos veces en checkouts aislados desde el mismo Bronze: ambas corridas completaron sus
19 pasos y produjeron exactamente los mismos 28 Parquet Silver, 31 Gold y fingerprints
de linaje.

Se conserva la arquitectura Bronze/Silver/Gold con Parquet y DuckDB. La trazabilidad
ahora cubre 277,805 registros y la calidad operativa y analítica vive en un único
ledger canónico.

## Qué se construyó

- Registro central de 32 pasos: 13 de ingesta, 7 de parsing, 6 de transformación, 2
  de analítica y 4 de preparación o validación del producto.
- Entradas, salidas, dependencias, obligatoriedad y estado explícito por paso.
- Rebuild offline desde checkout limpio, sin reutilizar Silver, Gold, warehouse,
  modelos, notebooks ejecutados o analítica anterior.
- Huella SHA-256 determinista de código para checkouts sin metadata Git.
- Promoción local atómica con staging, validación previa y rollback completo.
- Contratos `stage9_v1.0.0` para 28 datasets Silver y 31 tablas Gold.
- `record_id` estable y separado del grano natural en hechos y resultados analíticos.
- `dim_source`, `dim_source_artifact`, `dim_source_priority` y
  `bridge_record_lineage`.
- SCD2 homogéneo para SEC, AFAC y BMV, con excepción documentada para el backfill
  histórico BMV.
- `fact_data_quality_issues` como ledger canónico de calidad.
- `dim_airport_group` y `fact_airport_group_traffic` para separar agregados de
  operadores de aeropuertos físicos.
- `consolidation_method` en las 99 métricas y rechazo de consolidaciones inválidas.
- Salud de datos ampliada a 7 dominios y 15 datasets.
- Diccionario de datos regenerado, informe independiente y ADR de arquitectura.

## Datos obtenidos y materializados

La etapa no descargó archivos nuevos ni accedió a internet. Reutilizó el snapshot
Bronze inmutable y verificó cada artefacto contra su hash.

| Capa / catálogo | Cobertura | Filas o archivos | Tamaño local | Método |
|---|---|---:|---:|---|
| Bronze | Snapshot histórico existente | 1,506 archivos; 752 artefactos de negocio | 845.72 MiB | Copia local inmutable y verificación SHA-256 |
| Catálogo de fuentes | Fuentes públicas, curadas y derivadas | 23 fuentes | Incluido en Gold | Catálogo declarativo validado |
| Silver | 28 datasets físicos | 28 Parquet | 14.63 MiB | Parsing offline desde Bronze |
| Gold | Dimensiones, hechos, calidad y linaje | 31 Parquet | 89.85 MiB | Transformación y validación offline |
| `bridge_record_lineage` | Registros, artefactos y padres contribuyentes | 412,139 relaciones | Incluido en Gold | Linaje directo, heredado o declarado |
| `fact_data_quality_issues` | Incidencias operativas y derivadas | 287 incidencias canónicas | Incluido en Gold | Firma estable y reconciliación |

El manifiesto contiene 752 artefactos únicos. Los 1,506 archivos del árbol Bronze
incluyen artefactos, metadata lateral y archivos de control; no se interpretan como
1,506 descargas de negocio.

## Linaje y catálogo

| Medida | Resultado |
|---|---:|
| Registros esperados | 277,805 |
| Registros con declaración de linaje | 277,805 |
| Cobertura | 100% |
| Registros resueltos directamente a artefactos | 208,909 |
| Registros resueltos mediante padres | 68,429 |
| Curaciones/derivaciones con declaración explícita sin enlace exacto | 467 |
| Artefactos desconocidos | 0 |
| Registros padre desconocidos | 0 |

`artifact_sha256` identifica únicamente el archivo original.
`lineage_fingerprint` identifica la combinación de contribuyentes de un registro.
No se fabricaron enlaces para curaciones sin un artefacto público directo.

## Calidad y contratos

- Las 499 filas operativas crudas contienen 264 incidencias únicas y 235 repeticiones
  de ejecución. Las 264 operativas únicas más 23 discrepancias derivadas producen 287
  incidencias canónicas con firma única.
- Las 27 relaciones declaradas entre Silver y Gold tienen cero claves huérfanas.
- El grano AFAC incluye archivo, fila, métrica, región, periodo, aerolínea, tipo de
  servicio y mercado; programado y chárter permanecen como componentes, no revisiones.
- El grano BTS T-100 distingue archivo, aerolínea, entidad, origen, destino, aeronave,
  configuración, año, mes y clase.
- Los 47 totales `ALL_ASUR`, `ALL_GAP` y `ALL_OMA` quedaron fuera de `dim_airport` y
  se conservaron en las tablas de grupo aeroportuario.
- Las 99 métricas declaran consolidación: 39 `sum`, 5 `latest` y 55 `non_additive`.
  No hay ratios, márgenes, factores de ocupación ni métricas unitarias sumables.
- La salud de datos cubre carrier metrics, rutas BTS, aeropuertos, grupos
  aeroportuarios, mercado, macro y analítica mediante 25 filas de salud/frescura.

## Historial SCD2 y precedencia

| Fuente | Versiones materializadas | Versiones posteriores a la base | Filas corrientes | Resultado |
|---|---:|---:|---:|---|
| SEC | 641 | 0 | 641 | PASS |
| AFAC | 3,642 | 0 | 3,642 | PASS |
| BMV XBRL | 293 | 40 | 253 | PASS |

Los fixtures congelados verifican que una observación idéntica no crea revisión y que
un cambio de valor incrementa `restatement_count`, cierra la versión anterior y deja
una única fila corriente.

BMV requiere una excepción explícita: su backfill inicial contiene varios periodos
históricos descargados dentro de un lote corto. Dentro de ese lote se usa el periodo
del paquete para reconstruir la secuencia; las revisiones posteriores vuelven al orden
de ingesta. Los contratos impiden intervalos invertidos, huecos, traslapes y contadores
que cambian sin cambio de valor.

La precedencia central tiene 9 reglas. SQL y Python produjeron la misma selección para
5,739 filas usando prioridad, estado definitivo, confianza y fecha de ingesta.

## Validaciones ejecutadas

| Check | Resultado | Detalle |
|---|---|---|
| Suite completa | PASS | 142/142 pruebas |
| Contratos Etapa 6 | PASS | 25/25 controles |
| Analítica Etapa 7 | PASS | 18/18 controles |
| Dashboard Etapa 8 | PASS | 18/18 controles; diez páginas sin excepciones |
| Aceptación Etapa 9 | PASS | 12/12 controles |
| Registro central | PASS | 32/32 callables importables; distribución 13/7/6/2/4 |
| Relaciones | PASS | 27/27 con cero huérfanas |
| Rebuild A | PASS | 19/19 pasos desde checkout limpio |
| Rebuild B | PASS | 19/19 pasos desde checkout limpio |
| Idempotencia Silver | PASS | 28/28 archivos, hashes y filas idénticos |
| Idempotencia Gold | PASS | 31/31 archivos, hashes y filas idénticos |
| Fingerprints | PASS | Digest de linaje idéntico en ambas corridas |
| Integridad Bronze | PASS | Misma huella de 1,506 archivos en origen, A y B |
| SCD2 | PASS | SEC, AFAC, BMV y fixtures congelados |
| Precedencia | PASS | 5,739 selecciones idénticas en SQL y Python |
| Consolidación | PASS | Métricas sin regla o no aditivas no pueden sumarse |
| Publicación/rollback local | PASS | Solo se intercambian salidas completas; falla simulada restaura destinos |

## Cifras ancla verificadas

| Periodo | Métrica | Esperado | Obtenido | ¿Coincide? |
|---|---|---:|---:|---|
| 2026Q1 | Ingreso total | US$1,341.0 M | US$1,341.0 M | Sí |
| 2026Q1 | EBITDAR ajustado | US$335.8 M | US$335.8 M | Sí |
| 2026Q1 | Margen EBITDAR | 25.0% | 25.0% | Sí |
| 2026Q1 | Ingreso operativo | US$141.8 M | US$141.8 M | Sí |
| 2026Q1 | Margen operativo | 10.6% | 10.6% | Sí |
| 2026Q1 | Pasajeros | 5.791 M | 5.791 M | Sí |
| 2026Q1 | Factor de ocupación | 84.4% | 84.4% | Sí |
| 2026Q1 | TRASM | 15.6 ¢/ASM | 15.6 ¢/ASM | Sí |
| 2026Q1 | Flota | 166 | 166 | Sí |
| 2026Q1 | CASM ex combustible | 10.2 ¢/ASM | 10.2 ¢/ASM | Sí |
| 2026Q2 | Ingreso total | US$1,479.0 M | US$1,479.0 M | Sí |
| 2026Q2 | Margen EBITDAR | 17.9% | 17.9% | Sí |
| 2026Q2 | Pasajeros | 6.014 M | 6.014 M | Sí |
| 2026Q2 | Factor de ocupación | 84.9% | 84.9% | Sí |
| 2026Q2 | Flota | 169 | 169 | Sí |
| 2026M06 | Pasajeros Aeroméxico AFAC | 1,481,477 | 1,481,477 | Sí |
| 2026M06 | Pasajeros Connect AFAC | 339,718 | 339,718 | Sí |
| 2026M06 | Grupo Aeroméxico AFAC | 1,821,195 | 1,821,195 | Sí |

## Qué NO funcionó y por qué

1. El primer rebuild aislado no encontró `data/reference/carrier_crosswalk.csv` porque
   el checkout limpio copiaba código y configuración, pero no referencias versionadas.
   Se corrigió el inventario de entrada y esa corrida no se promovió.
2. Un segundo intento falló antes de `transform.stage4`: una entrada única carecía de
   la coma que la convierte en tupla. Se corrigió la declaración y se añadió validación
   estructural del registro.
3. El bloqueo total de sockets impedía al notebook comunicarse con su kernel local.
   Se permitió únicamente loopback; las conexiones externas continúan bloqueadas.
4. La primera revisión SCD2 de BMV reveló intervalos invertidos por tratar un backfill
   histórico capturado en lote como si fuera una secuencia de revisiones normales. Se
   implementó y documentó la excepción de backfill descrita arriba.
5. La revisión independiente encontró que el gate original no cubría todas las
   relaciones ni invariantes nuevas. El cierre definitivo usa los 12 controles de
   aceptación y contratos temporales más estrictos.

Los checkouts fallidos se conservaron como evidencia diagnóstica y nunca se usaron para
promover resultados.

## Decisiones tomadas

- Mantener DuckDB, Parquet y Bronze/Silver/Gold; no introducir BigQuery ni dbt.
- Conservar `fact_carrier_metrics` largo y las vistas SQL como capa semántica.
- Separar `record_id`, grano natural, hash de artefacto y fingerprint de linaje.
- Tratar las fuentes opcionales ausentes como `not_available`, nunca como cero ni como
  una omisión silenciosa.
- Aplicar una única política de precedencia en SQL y Python.
- Bloquear cualquier consolidación sin regla y cualquier suma de una métrica no
  aditiva.
- Promover salidas únicamente después de completar todos los pasos y validar staging.

La justificación completa se registra en
`docs/decisiones/decision-008-saneamiento-backend.md`.

## Supuestos hechos

- El snapshot Bronze usado por ambos rebuilds representa el universo crudo disponible
  al cierre de la etapa.
- La ausencia de revisiones reales SEC y AFAC en ese snapshot no implica que nunca
  ocurran; por eso la conducta se cubre con fixtures congelados.
- Una declaración explícita de curación sin enlace exacto es trazabilidad válida cuando
  no existe un único archivo público responsable; no equivale a inventar una fuente.
- Las incidencias duplicadas por ejecución comparten firma y evidencia suficiente para
  consolidarse, pero su estado de resolución no cambia por deduplicarlas.

## Preguntas para el usuario

No hay decisiones de negocio pendientes para cerrar la Etapa 9. El gate humano sigue
vigente antes de comenzar cualquier trabajo posterior.

## Riesgos para el trabajo posterior

- Bronze no está en Git. Perder el snapshot local o su manifiesto impediría repetir
  exactamente esta reconstrucción.
- Las 467 declaraciones sin artefacto directo deben seguir visibles y no transformarse
  en enlaces ficticios durante futuras interfaces.
- Las 287 incidencias canónicas permanecen abiertas hasta que exista evidencia de
  resolución; la vista de salud debe conservar ese estado.
- Un futuro uso de consolidación `weighted` deberá declarar y validar el ponderador.
- Toda modificación a la lógica BMV debe conservar la diferencia entre backfill inicial
  y revisión posterior.

## Comandos para reproducir

```powershell
uv run pytest -q
uv run python -m src.transform.validate_stage6
uv run python -m src.analytics.validate_stage7
uv run python -m src.dashboard.validate_stage8
uv run python -m src.transform.validate_stage9
uv run python -m src.rebuild --no-publish --keep-workspace
```

La comparación de dos rebuilds requiere dos checkouts de destino distintos construidos
desde el mismo snapshot Bronze. El recibo canónico queda en
`data/quality/stage9_rebuild_comparison.json`.

## Gate final

Etapa 9 cerrada: contratos, SCD2, catálogo, linaje, calidad, grupos aeroportuarios,
precedencia, consolidación, salud, warehouse, rebuild aislado, regresión y documentación
cumplen los criterios de aceptación. No queda una excepción abierta de severidad P0 o
P1 dentro del alcance de esta etapa.
