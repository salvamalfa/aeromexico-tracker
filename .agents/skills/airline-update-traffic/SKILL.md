---
name: airline-update-traffic
description: "Actualizar candidatos de la familia tráfico afac y bts de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Tráfico AFAC y BTS

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `traffic`. Alcance: AFAC: aerolínea, aeropuertos, países y marginales como productos distintos; BTS T-100 International Segment MX↔US.

AFAC exige misma edición acumulada para O-D y marginal por operador. El PDF canónico de 2026 y su validación están limitados a junio: un control para agosto debe bloquear si agosto no aparece. No asignar el total de ruta a una aerolínea. BTS usa mode=bts_year con año explícito y FORM_URL de src/ingest/bts/t100.py: GET del formulario y POST, incluso para años revisados. No llamar ingest_t100 para descargar toda la historia. Verificar máximo mes realmente presente en MX-US; el anuncio de BTS no lo demuestra. Separar operador de comercializador, realizados de programados y Segment de Market. Seleccionar también años afectados por revisiones, no solo el corriente.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family traffic
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.bts,parse.afac

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.
