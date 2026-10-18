---
name: airline-update-macro-market
description: "Actualizar candidatos de la familia macro y mercado de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Macro y mercado

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `macro_market`. Alcance: Banxico FIX/INPC/tasa, H.10 de respaldo, EIA y precios bursátiles.

Capturar la historia diaria dentro de la ronda mensual o trimestral, sin refresh diario/semanal. Las series Banxico tienen calendarios distintos. H.10 conserva su etiqueta como respaldo y no sustituye silenciosamente FIX. Reportar días observados de combustible y tipo de cambio; promedios parciales no son trimestre completo. Combustible spot no es costo contratado. Mantener identidad de AERO e IPO; no empalmar la acción vieja. Los ajustes de precios requieren comparación por fecha/ticker. Respetar entidad y periodo que espera cada parser: EIA usa EER_EPJK_PF4_RGC_DPG y periodo inicio_fin.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family macro_market
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.fx,parse.fuel,parse.market

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

