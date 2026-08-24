# Decisión 007 — Warehouse de consumo y BigQuery

Fecha: 2026-08-23  
Estado: aceptada

## Contexto

La Etapa 6 debía decidir si la capa gold se mantendría solo en DuckDB local o si se
crearía además un espejo en BigQuery. El volumen actual cabe holgadamente en un motor
embebido y el dashboard previsto puede leer DuckDB o Parquet sin un servicio remoto.

## Decisión

Mantener **DuckDB local como único warehouse de consumo** y Parquet como formato
persistente de las tablas gold. No se implementa espejo en BigQuery.

También se mantienen dos alcances de entidad:

- `v_carrier_standalone`: cada entidad por separado.
- `v_carrier_consolidated`: las subsidiarias se asignan al grupo mediante
  `dim_carrier.parent_carrier_key`.

La vista `v_carrier_default` usa el alcance consolidado, por decisión explícita del
usuario, para que Aeroméxico + Aeroméxico Connect sea comparable con los financieros
consolidados.

## Consecuencias

- Cero infraestructura y costo operativo remoto.
- Rebuild completamente offline y reproducible.
- Las consultas ad hoc se ejecutan sobre `data/warehouse.duckdb` o directamente sobre
  `data/gold/*.parquet`.
- BigQuery puede añadirse después como exportación opcional; nunca será dependencia del
  pipeline ni del dashboard.
