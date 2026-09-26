# `src/pipeline`

Registro central y motor de ejecución para las etapas de ingesta, parseo y
transformación: qué corre, con qué requisitos de insumos y qué recibo deja.

## Responsabilidad

- `model.py`: modelo tipado público de fases, requisitos de insumo y recibos
  de ejecución (`PipelinePhase`, dataclasses de registro).
- `registry.py`: registro de acciones ejecutables por fase.
- `runner.py`: motor de ejecución (orquesta, valida requisitos, produce
  recibos con timestamp).
- `actions.py`: acciones concretas registradas (ingest/parse/transform).
- `worker.py`: ejecución de una acción individual.
- `offline.py`: modo de ejecución sin red, para `just rebuild`.

## Entradas / salidas

- **Entradas:** el registro de acciones de cada paquete (`ingest`, `parse`,
  `transform`) y sus requisitos declarados.
- **Salidas:** recibos de ejecución (JSON) y las salidas propias de cada
  acción (bronze/silver/gold, según la fase).

## Puntos de entrada

Sin CLI propio; lo invocan `python -m src.ingest`, `python -m src.parse`,
`python -m src.transform` y `src/rebuild.py` (`just rebuild`).

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_pipeline_orchestration.py
```
