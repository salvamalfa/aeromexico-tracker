# Decisión 008 — Saneamiento del backend y trazabilidad

Fecha: 2026-09-01
Estado: aceptada

## Contexto

La auditoría posterior a la construcción del dashboard encontró brechas en
orquestación, reproducibilidad, contratos, historial de versiones, linaje y calidad.
El volumen actual sigue cabiendo con holgura en archivos Parquet y DuckDB, y la tabla
larga de métricas conserva flexibilidad para comparar aerolíneas y periodos.

La decisión debía corregir esas brechas sin cambiar las cifras ancla, inventar enlaces
a archivos públicos ni añadir infraestructura o dependencias.

## Decisión

### Conservar la arquitectura base

Se mantiene **Bronze/Silver/Gold**, Parquet como persistencia, DuckDB como capa de
consulta y Streamlit como producto de consumo. `fact_carrier_metrics` permanece en
formato largo y las vistas SQL continúan como capa semántica.

No se incorpora BigQuery ni dbt. Tampoco se reemplaza el modelo dimensional por una
plataforma externa.

### Unificar la orquestación

Un registro central declara 32 pasos, sus entradas, salidas, dependencias y condición
obligatoria u opcional. Ingesta, parsing, transformaciones y rebuild resuelven ese mismo
registro. Un requisito obligatorio ausente detiene la corrida; uno opcional se registra
como `not_available` con su razón.

El rebuild parte de un checkout limpio con código, configuración, referencias y una
copia de Bronze. No copia salidas Silver, Gold, warehouse, modelos, notebooks ejecutados
ni analítica previa.

### Convertir los contratos en reglas semánticas

Los 28 datasets Silver y las 31 tablas Gold usan contratos `stage9_v1.0.0`. Además de
columnas y tipos, declaran grano, claves, relaciones, dominios, rangos e invariantes.

`record_id` es una clave técnica estable, calculada como `rec_<sha256>` a partir del
nombre de tabla y su grano natural. No reemplaza el grano de negocio ni se usa para
ocultar duplicados.

### Separar artefacto, derivación y registro

- `artifact_sha256` identifica exclusivamente el archivo original preservado.
- `lineage_fingerprint` identifica la combinación o derivación de contribuyentes.
- `bridge_record_lineage` relaciona un `record_id` con uno o varios artefactos o
  registros padre.
- Una curación sin archivo directo declara su tipo de linaje; no recibe una URL o un
  artefacto inventado.

`dim_source` es el catálogo canónico de 23 fuentes y `dim_source_artifact` materializa
los 752 artefactos verificados del manifiesto Bronze.

### Aplicar SCD2 con una excepción explícita de backfill

SEC, AFAC y BMV comparten clave lógica, `valid_from`, `valid_to`, `is_current` y
`restatement_count`. Una observación idéntica no crea una revisión; el contador aumenta
solo cuando cambia el valor.

La fecha de ingesta gobierna las revisiones normales. Para el backfill inicial BMV,
múltiples periodos históricos fueron capturados dentro de un lote corto y su orden de
ingesta no expresa el orden de vigencia. Ese lote se ordena por periodo del paquete y
recibe una fecha efectiva por artefacto. Cualquier revisión posterior vuelve a seguir
la fecha de ingesta. Los contratos rechazan intervalos invertidos, huecos, traslapes y
estados corrientes inconsistentes.

AFAC programado y chárter son componentes complementarios y no revisiones entre sí.

### Centralizar calidad, precedencia y consolidación

`fact_data_quality_issues` es el ledger canónico. Una firma estable reconcilia las 264
incidencias operativas únicas con 23 derivadas, conservando evidencia, severidad,
estado y fechas.

`dim_source_priority` define un único desempate: prioridad, estado definitivo,
confianza y fecha de ingesta. SQL y Python consumen la misma política.

`dim_metric.consolidation_method` obliga a declarar `sum`, `latest`, `weighted` o
`non_additive`. Una métrica sin regla se rechaza; `weighted` exige ponderador y ratios,
márgenes, factores de ocupación y métricas unitarias nunca se suman.

### Separar aeropuertos de grupos aeroportuarios

`dim_airport` conserva únicamente aeropuertos físicos. Los 47 totales de ASUR, GAP y
OMA viven en `dim_airport_group` y `fact_airport_group_traffic`.

### Promover resultados solo después del gate

El código de un checkout sin `.git` se identifica mediante una huella SHA-256
determinista. Todas las salidas se copian primero a staging, se verifican y después se
intercambian. Si falla cualquier movimiento, el rollback restaura todos los destinos.

El bloqueo offline impide conexiones externas y permite únicamente loopback para que
el kernel local de Jupyter pueda ejecutar el notebook reproducible.

## Alternativas consideradas

| Alternativa | Decisión | Motivo |
|---|---|---|
| BigQuery como warehouse principal o espejo obligatorio | Rechazada | Añade costo, credenciales y operación remota sin resolver una necesidad de escala actual. |
| dbt para contratos y transformaciones | Rechazada | Duplicaría una capa declarativa que ya se valida en Python/SQL y agregaría una dependencia no necesaria. |
| Sustituir `fact_carrier_metrics` por tablas anchas | Rechazada | Reduce flexibilidad y complica métricas heterogéneas, versiones y comparables. |
| Guardar solo el artefacto “ganador” | Rechazada | Perdería contribuyentes, revisiones y evidencia de agregaciones. |
| Tratar totales `ALL_*` como aeropuertos | Rechazada | Mezcla entidades físicas con agregados de operadores y crea relaciones falsas. |

## Consecuencias

### Positivas

- El pipeline completo tiene un inventario único y estados explícitos.
- Dos reconstrucciones desde el mismo Bronze producen exactamente los mismos Parquet
  y fingerprints.
- Todo registro en alcance tiene un estado de linaje verificable.
- Las revisiones preservan evidencia sin confundir componentes complementarios.
- Las reglas de negocio son iguales en SQL y Python y fallan de forma explícita ante
  una métrica no consolidable.
- Una corrida incompleta no puede mezclar sus salidas con las de una corrida válida.

### Costos y límites aceptados

- `bridge_record_lineage` aumenta materialmente el tamaño de Gold a cambio de
  trazabilidad a nivel registro.
- Bronze sigue siendo una dependencia local no versionada; debe conservarse junto con
  su manifiesto para repetir el rebuild.
- Las declaraciones de curación sin artefacto directo requieren mantenimiento
  explícito y no deben reinterpretarse como enlaces públicos.
- Las incidencias canónicas permanecen abiertas hasta que exista evidencia de
  resolución; deduplicar no equivale a resolver.

## Controles permanentes

- Dos rebuilds comparables deben conservar igualdad de hashes antes de promover una
  modificación estructural.
- Todo contrato nuevo debe declarar grano, identificador y relaciones seguras.
- Ninguna fuente, artefacto o URL se agrega sin catálogo y validación.
- Ninguna métrica se consolida sin método declarado.
- Cualquier cambio en cifras ancla detiene el gate y exige investigación.
