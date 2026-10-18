---
name: airline-update-corporate
description: "Actualizar candidatos de la familia fuentes corporativas y regulatorias de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Fuentes corporativas y regulatorias

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `corporate`. Alcance: SEC/IR/BMV: Aeroméxico, Volaris, Viva, Delta y Ryanair; GAP/ASUR se separan como tráfico aeroportuario.

Revalidar catálogos current y seleccionar anexos reales. No tratar llamadas o anuncios como estados financieros. Preservar moneda, escala, trimestre/acumulado/TTM, instante/duración, preliminar/auditado e IFRS/US-GAAP. Los parsers IR de Aeroméxico son históricos; el descargador Viva termina en 2026Q2. Capturar un documento nuevo no demuestra que esos parsers lo incorporen. Para SEC usar importación manual con URL y hash. No ejecutar la ingesta heredada de peers como actualizador genérico.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family corporate
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.peer_discovery,parse.sec,parse.peers,parse.bmv,parse.aeromexico_ir,parse.aeromexico_ir_financial

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.
