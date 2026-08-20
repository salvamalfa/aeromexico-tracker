# Decision 001 — Bronze fuera de Git

Fecha: 2026-08-20
Estado: Aceptada

## Decisión

`data/bronze/` no se versiona en Git. Sí se versionan, cuando existan, los
ledgers `_manifest.jsonl` y `_restatements.jsonl`, además de fixtures pequeños y
congelados bajo `tests/fixtures/`.

## Motivo

Las descargas crudas pueden crecer a varios GB, especialmente BTS T-100. Git no
es un almacén adecuado para ese volumen. Los hashes SHA-256, URLs, timestamps y
metadatos preservan procedencia y permiten auditar o reconstruir la colección,
mientras que los fixtures mantienen reproducibles los tests de parsers.

## Consecuencias

- Cada operador conserva bronze localmente o en almacenamiento externo.
- Ningún pipeline puede asumir que Git contiene los archivos crudos.
- `save_bronze()` mantiene manifiesto y restatements append-only.
- La reconstrucción sin red parte de una copia local de bronze.
