# Extracción de tablas de Airlines Tracker

Esta capa convierte documentos Bronze en tablas Silver. Cada tabla conserva
el significado de su fuente: unidades, periodos, entidad reportante y faltantes.
La combinación entre proveedores ocurre después, en
[src/transform](../transform/README.md).

## Responsabilidad

| Fuente | Lectura y normalización |
|---|---|
| SEC EDGAR | [sec/](sec/): cifras operativas y financieras de los documentos públicos. |
| BMV | [bmv/](bmv/): paquetes XBRL y sus conceptos contables. |
| AFAC | [afac/](afac/): libros y boletines de tráfico mensual. |
| BTS y otras aerolíneas | [bts/](bts/), [peers/](peers/): tráfico por tramo y reportes comparables. |
| Aeroméxico | [aeromexico_ir.py](aeromexico_ir.py) y [aeromexico_ir_financial.py](aeromexico_ir_financial.py): métricas y referencias de reportes trimestrales. |
| Fuentes complementarias | [stage4.py](stage4.py): variables económicas, mercado, aeropuertos y noticias. |

Un faltante permanece ausente. Operador y comercializador se conservan
separados cuando la fuente permite distinguirlos. El linaje mantiene la
referencia al documento original y su huella; las
[reglas del proyecto](../../AGENTS.md#reglas-de-significado-de-datos) precisan
estas diferencias.

## Entradas / salidas

- **Entradas:** originales locales en `data/bronze/` y su manifiesto.
- **Salidas:** tablas `data/silver/`, locales y regenerables.
- **Control posterior:** los [contratos Silver](../transform/silver_contracts.py)
  verifican estructura, grano, dominios y relaciones antes de construir Gold.

El clon público no contiene todos los originales. La guía de
[desarrollo y reproducibilidad](../../docs/cloud-development.md) explica qué
puede ejecutarse con los datos públicos y qué requiere restauración local.

## Puntos de entrada

Desde la raíz, con Bronze disponible:

```bash
just parse
```

Equivale a `uv run python -m src.parse` y bloquea la red. Para validar una
fuente por separado:

```bash
just sec-validate
just bmv-validate
just afac-validate
```

Estos comandos llaman a [sec/validate.py](sec/validate.py),
[bmv/validate.py](bmv/validate.py) y [afac/validate.py](afac/validate.py).
El [registro central](../pipeline/registry.py) declara los insumos de cada paso.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_sec_definitions.py tests/test_afac_monthly_stats.py -m "not local_data"
```

La marca `local_data` identifica las pruebas que requieren originales o tablas
locales. Quita ese filtro solo cuando sus insumos estén disponibles.
