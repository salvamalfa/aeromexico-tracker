# Modelo de datos de Airlines Tracker

Esta capa reúne las tablas Silver en un modelo analítico compartido. Gold
organiza aerolíneas, aeropuertos, rutas, periodos y métricas para que los
estudios y el dashboard consulten las mismas definiciones.

## Responsabilidad

| Parte del modelo | Código principal |
|---|---|
| Dimensiones y sus cambios históricos | [stage6_dimensions.py](stage6_dimensions.py) |
| Hechos de aerolíneas, rutas, aeropuertos y mercado | [stage6_facts.py](stage6_facts.py) |
| Contratos y relaciones entre tablas | [silver_contracts.py](silver_contracts.py), [stage6_contracts.py](stage6_contracts.py) |
| Vistas de consulta en DuckDB | [stage6_warehouse.py](stage6_warehouse.py) |
| Fuentes, artefactos y linaje por registro | [stage9.py](stage9.py), [stage9_lineage.py](stage9_lineage.py) |
| Diccionario de tablas y columnas | [generate_data_dictionary.py](generate_data_dictionary.py) |

Las dimensiones mantienen historia de cambios mediante versiones con vigencia
(SCD2). Las tablas de hechos conservan entidad, periodo, unidad y procedencia;
las prioridades de fuente resuelven comparables sin convertir un faltante en cero.

Los módulos [domestic_slots.py](domestic_slots.py),
[international_routes.py](international_routes.py),
[afac_exclusive_domestic.py](afac_exclusive_domestic.py),
[aicm_international_slots.py](aicm_international_slots.py),
[aifa_shared_presence.py](aifa_shared_presence.py) y
[oma_documented_routes.py](oma_documented_routes.py) incorporan evidencia de
rutas con alcances distintos. La estructura común conserva esas diferencias;
una inferencia o programación no se convierte en operación observada.

## Entradas / salidas

- **Entradas:** Silver local y, para ciertas extensiones de rutas, evidencia
  Bronze específica.
- **Salidas:** tablas públicas `data/gold/*.parquet`, el warehouse local
  `data/warehouse.duckdb` y el [diccionario de datos](../../docs/diccionario-datos.md).
- **Consumidores:** [modelos y estudios](../analytics/README.md),
  [preparación del dashboard](../dashboard/README.md) y
  [exportación web](../web_export/README.md).

Gold contiene extractos públicos versionados. El warehouse es regenerable y
no se incluye en Git. La materialización completa del catálogo y del linaje
se ejecuta más adelante durante la preparación del dashboard, según
[el registro del pipeline](../pipeline/registry.py).

El [glosario de indicadores](../../docs/glosario-kpis.md) alimenta las
definiciones de métricas. El diccionario se genera desde el modelo; sus
correcciones deben hacerse en el generador o sus insumos.

## Puntos de entrada

Desde la raíz, con Silver y los demás insumos del registro disponibles:

```bash
just transform
```

Equivale a `uv run python -m src.transform` y bloquea la red. Ejecuta la fase
de transformación; la analítica y la publicación tienen entradas separadas.
`just rebuild` reconstruye el pipeline completo sin red desde Bronze en un
entorno aislado. Consulta [src/pipeline](../pipeline/README.md) para sus requisitos.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_stage6.py tests/test_international_routes.py tests/test_aicm_international_slots.py -m "not local_data"
```
