---
name: airline-update-routes
description: "Actualizar candidatos de la familia autoridades y evidencia de rutas de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Autoridades y evidencia de rutas

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `routes`. Alcance: ANAC, Aerocivil, CAA, Aena y evidencia fechada de Aeroméxico, OMA, Colima y Expansión.

Seleccionar documentos reales; no ejecutar el descargador histórico con URLs fijas como refresh universal. ANAC puede bloquear acceso; Aerocivil necesita paginación acotada y reconciliar cantidad de registros. CAA Flight Punctuality no es Airport Data. Aena requiere exportación manual; compañía×aeropuerto y mercado entre aeropuertos no producen compañía×ambos extremos. Comunicados y listados permiten presencia/programación/inferencia limitada, no pasajeros o vuelos observados. Conservación del original no autoriza activar inferencias ni estimaciones.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family routes
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: Sin parser genérico certificado para novedades; capturar candidato y dejar bloqueada la incorporación hasta disponer de adaptador probado.

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

