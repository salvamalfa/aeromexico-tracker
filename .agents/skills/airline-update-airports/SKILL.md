---
name: airline-update-airports
description: "Actualizar candidatos de la familia aeropuertos y grupos de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Aeropuertos y grupos

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `airports`. Alcance: OMA, AICM, AIFA y tráfico GAP/ASUR publicado vía SEC.

Descubrir el archivo de tráfico nuevo; los enlaces del catálogo pueden ser históricos. Separar aeropuerto de total de grupo y México de otros países de ASUR. AICM slots es otro producto: programación estacional, no tráfico realizado. AIFA XLSX puede cambiar de estructura; contrato y periodo real deben pasar. No atribuir totales aeroportuarios a Aeroméxico.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family airports
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.airports

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

