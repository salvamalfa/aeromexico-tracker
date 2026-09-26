# `src/parse`

Normaliza cada fuente de `data/bronze/` a una tabla fiel a esa fuente,
sin combinar todavía entre proveedores.

## Responsabilidad

- Parsear el contenido crudo por proveedor (`afac/`, `bmv/`, `bts/`, `peers/`,
  `profiles/`, `sec/`, `aeromexico_ir.py`, `aeromexico_ir_financial.py`,
  `stage4.py`) preservando unidades, periodos y faltantes tal como los reporta
  la fuente.
- No rellenar un faltante como cero ni fusionar operador y comercializador si
  la fuente permite separarlos (ver `AGENTS.md`, "Reglas de significado de
  datos").

## Entradas / salidas

- **Entradas:** `data/bronze/` (local).
- **Salidas:** `data/silver/` (local, regenerable, no versionado).

## Puntos de entrada

- `python -m src.parse` (`__main__.py` → `run()`).
- Módulos por proveedor se ejecutan individualmente para depuración
  (`src/parse/sec/validate.py`, `src/parse/bmv/validate.py`,
  `src/parse/afac/validate.py`, expuestos también como `just sec-validate`,
  `just bmv-validate`, `just afac-validate`).

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_sec_definitions.py tests/test_afac_monthly_stats.py -m "not local_data"
```

Nota: la mayoría de pruebas de `parse` necesitan bronze local
(`data/bronze/`) y están marcadas `local_data`; sin ese respaldo, ejecútalas
solo si tienes el clon del repositorio privado (ver `README.md` raíz,
"Datos y documentación").
