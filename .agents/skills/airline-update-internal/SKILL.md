---
name: airline-update-internal
description: "Actualizar candidatos de la familia derivados y curación de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Derivados y curación

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `internal`. Alcance: peer_profile, curated_primary_sources y derived_gold, sin endpoint propio.

No crear tres descargas ficticias. Reconstruir solo derivados con padres validados, versión de fórmula, unidades y fecha de corte. Preservar N/D, etiquetas reportado/calculado/inferido/estimado/programado y reglas de ponderación. Hash agregado o fuente heredada requiere puente de linaje, no una URL inventada. No reentrenar forecast, recalcular estudios, cambiar cortes de análisis ni activar tesis.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family internal
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: transform.stage4,transform.validate_stage4,transform.validate_stage5,transform.validate_silver,transform.stage6,transform.validate_stage6; requieren todos sus insumos y no incluyen analytics/dashboard/publicación.

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.
