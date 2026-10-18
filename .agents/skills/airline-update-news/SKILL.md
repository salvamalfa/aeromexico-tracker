---
name: airline-update-news
description: "Actualizar candidatos de la familia noticias mensuales de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Noticias mensuales

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `news`. Alcance: Google News RSS y GDELT; news_http_error conserva fallos y permanece inactivo.

Una revisión mensual, también cuando se combina con una ronda trimestral.
Capturar solo metadatos autorizados (título, URL, emisor, fecha y consulta);
no artículos completos. El adaptador candidato `src/source_updates/news.py`
deduplica URL normalizada y fecha local, conserva todas las procedencias y
separa ediciones de días distintos. No resuelve enlaces opacos de Google News.
Los feeds no garantizan recuperar el mes entero: mostrar cobertura real.
Distinguir fecha del evento, publicación y captura; noticias no sustituyen
fuentes financieras oficiales. `news_http_error` nunca cuenta como noticia ni
ausencia de noticias. Reutilizar el archivo mensual de PR136 tras integrarlo;
no cambiar su rama ni activar candidatos. El contrato Silver conserva un
representante por noticia y `provenance_json` registra sus fuentes; una fuente
sin representante debe revisarse en esa procedencia antes de afirmar cobertura.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family news
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: parse.news

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

