# 14 — Etapa 9: Saneamiento del backend

## Objetivo

Cerrar las brechas de orquestación, calidad, linaje, contratos y modelado detectadas
por la auditoría independiente, sin cambiar la arquitectura base Bronze/Silver/Gold,
las cifras de negocio validadas ni el destino DuckDB + Parquet.

## Alcance obligatorio

1. Registro central de pipeline usado por ingesta y rebuild, con pasos obligatorios,
   opcionales y estados explícitos.
2. Catálogo Gold de fuentes y artefactos Bronze, identificadores estables de registro
   y relación muchos-a-muchos de linaje.
3. Ledger Gold único que reconcilie el JSONL operativo y las discrepancias derivadas.
4. Contratos declarativos para Silver y Gold con grano, dominios, rangos y relaciones.
5. SCD2 homogéneo para las versiones disponibles de SEC, AFAC y BMV.
6. Separación de aeropuertos y totales de grupos aeroportuarios.
7. Política central de precedencia de fuentes y reglas de consolidación por métrica.
8. Salud de datos con cobertura de todos los dominios consumidos.
9. Rebuild offline e idempotente desde una copia limpia de Bronze.

## Interfaces previstas

- `dim_source`: catálogo de negocio y acceso de cada fuente.
- `dim_source_artifact`: artefactos públicos preservados en Bronze.
- `bridge_record_lineage`: relación entre registros Gold y artefactos contribuyentes.
- `dim_source_priority`: precedencia declarativa de fuentes.
- `dim_airport_group` y `fact_airport_group_traffic`: totales de operadores separados
  de aeropuertos físicos.
- `fact_data_quality_issues`: ledger canónico de incidencias.
- `record_id` en hechos y resultados analíticos.
- `consolidation_method` en `dim_metric`.

## Reglas de implementación

- No descargar ni modificar Bronze durante el rebuild.
- No reutilizar Silver, Gold, warehouse o analítica de una corrida anterior.
- No inventar URLs ni convertir rutas locales en enlaces públicos.
- Preservar la tabla larga `fact_carrier_metrics` y las vistas SQL semánticas.
- No instalar dependencias nuevas.
- Si una cifra ancla cambia, detener la validación e investigar la diferencia.

## Entregables

- Código, contratos, tablas, vistas y pruebas de la etapa.
- Informe independiente en `docs/auditorias/` y ADR de saneamiento.
- Diccionario de datos regenerado.
- `docs/etapas/etapa-9-reporte.md`.
- Evidencia ejecutable de aceptación conforme a la sección de Etapa 9 del archivo 13.

## Gate

La Etapa 9 termina después de presentar el reporte y esperar aprobación. La página
interactiva “Estructura de datos” pertenece a la Etapa 10 y no se inicia sin un nuevo
“go” explícito.
