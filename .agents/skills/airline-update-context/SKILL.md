---
name: airline-update-context
description: "Actualizar candidatos de la familia referencias y contexto de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Referencias y contexto

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `context`. Alcance: OurAirports, FAA IASA y diccionario Loughran–McDonald.

Versionar crosswalk y diccionario. Un código nuevo requiere revisar filas no mapeadas y monto AFAC sin mapear. OurAirports es referencia comunitaria; IASA evalúa al país, no a una aerolínea y no demuestra causalidad. Cambiar versión del diccionario exige revisar comparabilidad del tono, sin recalcularlo automáticamente.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family context
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.airport_reference escribe dim_airport en Gold candidato; requiere data/reference. FAA y diccionario necesitan curación/adapter explícitos.

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.
