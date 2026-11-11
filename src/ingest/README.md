# Captura de fuentes de Airlines Tracker

Esta capa guarda los documentos tal como los entrega cada fuente. Conserva
sus bytes originales, procedencia y huella SHA-256 para poder comprobar después
de dónde salió una cifra.

## Responsabilidad

Los conectores cubren reportes de aerolíneas y reguladores, tráfico, aeropuertos,
variables económicas y mercado. El [registro del pipeline](../pipeline/registry.py)
declara cuáles ejecuta el comando general; el
[catálogo de fuentes](../../docs/catalogo-fuentes-calendario.md) explica su cobertura.

| Familia | Código de entrada |
|---|---|
| Reportes SEC, BMV y Aeroméxico | [sec/](sec/), [bmv/](bmv/), [aeromexico_ir.py](aeromexico_ir.py) |
| Tráfico AFAC y BTS T-100 | [afac/](afac/), [bts/](bts/) |
| Banxico, combustible EIA y precios | [macro/](macro/), [market/](market/) |
| Aeropuertos y otras aerolíneas | [airports/](airports/), [peers/](peers/) |
| Noticias, diccionario financiero y regulación | [news/](news/), [nlp/](nlp/), [regulatory/](regulatory/) |

La captura puede ser automática o asistida. AFAC conserva actualización manual.
El conector [aerodatabox/](aerodatabox/) permanece para el histórico y tareas
específicas; no forma parte de la lista de ingestas del comando general ni
implica nuevas capturas recurrentes.

## Entradas / salidas

- **Entradas:** documentos descargados o capturados y, cuando corresponda,
  credenciales privadas del proveedor.
- **Salidas:** originales locales en `data/bronze/`, más sus registros en
  `_manifest.jsonl` y `_restatements.jsonl`.
- **Trazabilidad:** el manifiesto conserva URL, fecha, método de captura, tamaño
  y SHA-256. Si cambia el contenido de una fuente para el mismo documento
  lógico, se conserva otra versión y se registra el cambio.

Los originales no se incluyen por defecto en el repositorio público. Sus
manifiestos sí se versionan. El almacenamiento compartido está en
[src/common](../common/README.md); la extracción de tablas corresponde a
[src/parse](../parse/README.md).

## Puntos de entrada

Desde la raíz:

```bash
just ingest
```

Equivale a `uv run python -m src.ingest`. Usa red y los requisitos de cada
fuente; revisa sus límites y la configuración antes de ejecutarlo. Los comandos
con cuotas o costo requieren la comprobación en seco descrita en
[AGENTS.md](../../AGENTS.md#entorno-y-comandos); no todos los conectores comparten
las mismas opciones de consola.

Para trabajar con los originales ya capturados, usa `just parse` o
`just rebuild`, ambos sin red. El [mapa del pipeline](../pipeline/README.md)
explica la diferencia.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_sec_discover.py tests/test_afac_monthly_stats.py tests/test_aerodatabox_international.py
```
