# Exportación web de Airlines Tracker

Convierte los datos del dashboard en archivos JSON que la interfaz carga por
periodo. Valida su forma y privacidad antes de escribirlos. Este módulo no
publica el sitio ni concede aprobaciones.

## Flujo y límites

1. Los generadores de [`src/dashboard/`](../dashboard/README.md) preparan
   Vuelos, datos financieros y Mercado. Noticias tiene su exportador propio.
2. Cada salida se valida con [`contracts/web/`](../../contracts/web/README.md)
   y `privacy.yaml`. Los insumos requeridos se declaran en
   [`config/web_inputs.yaml`](../../config/web_inputs.yaml).
3. Los JSON se escriben con claves ordenadas, separadores compactos y sin
   `NaN`. Las mismas entradas producen los mismos bytes.
4. [`web/`](../../web/README.md) consume esos archivos;
   [`src/publish/`](../publish/README.md) controla la publicación.

Si falta un Gold requerido, el exportador falla y nombra el archivo.
Un clon público no incluye los cuatro Gold privados requeridos por Vuelos
ni el expediente de `analysis_runs/`. **`--allow-missing-analysis` solo
permite omitir análisis ausentes en desarrollo; no reemplaza esos Gold.**
Para revisar el sitio público sin esos insumos, sirve `site/` o usa sus
datos ya exportados, como explica [la guía web](../../web/README.md).

## Archivos de salida

El destino habitual es `web/public/data/v1/`, local e ignorado por Git.
Vite lo sirve como `data/v1/` y lo copia al compilar.

| Archivo | Contenido |
|---|---|
| `flights/quarters.json` | Periodos, metadatos, series agregadas y geometría. |
| `flights/domestic/<period_id>.json`, `flights/international/<period_id>.json` y redes por entidad | Detalle de rutas por periodo. |
| `executive.json` | Registros financieros y vistas de todas las entidades. |
| Archivos de Mercado y Noticias | Participación, demanda aeroportuaria y archivo de noticias. |
| `analysis/<period_id>.json` o `analysis/<entity_key>/<period_id>.json` | Lecturas con aprobación vigente y citas públicas. |
| Archivos de métricas financieras y recibo | Solo se exportan si se proporcionan la propuesta y el recibo de aprobación coincidente. |

`official_routes.export_official_routes` es una exportación separada del mapa
oficial, tras reproducir sus fuentes y validar el candidato. No altera el
exportador histórico ni activa su resultado. Véase [mapa oficial](../../docs/mapa-oficial.md).

## Análisis y citas

`analysis.py` lee el expediente local de `analysis_runs/`. Descubre las
identidades aprobadas con `discover_approved_manifest` y obtiene el contenido
público mediante `src.analysis_agent.lifecycle.consumer_payload(record)`.
Después verifica los insumos con `flow.verified_inputs(record)`.

Cada cita contiene solo URL, texto visible y fragmento de la afirmación al que
se adjunta. No exporta originales, extractos de evidencia, nodos de cálculo
ni linaje privado. Los dominios permitidos dependen del contrato exacto de la
lectura. El exportador no escribe en el registro de aprobaciones.

## Comandos

Desde la raíz, con las entradas locales necesarias:

```bash
uv run python -m src.web_export --out web/public/data/v1
```

Para desarrollo sin todos los análisis locales:

```bash
uv run python -m src.web_export --out web/public/data/v1 --allow-missing-analysis
```

Para reproducir las identidades exactas de una publicación:

```bash
uv run python -m src.web_export --out web/public/data/v1 --analysis-manifest site/publication_manifest.json
```

`--analysis-manifest` admite el manifiesto completo o una lista con
`period_id`, `version` y, para las lecturas por entidad, `entity_key`.
En Python: `export_analysis(out_dir, manifest=identidades)`.
El módulo `src.web_export.analysis` acepta también `--out` y
`--analysis-manifest` para regenerar solo las lecturas.

La selección conserva cada versión exacta y exige aprobación vigente y código
compatible. Una selección explícita incompleta falla incluso con
`--allow-missing-analysis`; no se sustituye por otra versión.
Sin selección explícita, el descubrimiento rechaza varias versiones aprobadas
de la misma entidad y periodo.

El comando imprime rutas y tamaños; devuelve código 1 ante una entrada ausente
o inválida. Las opciones adicionales están en
[`__main__.py`](__main__.py), incluidos `--only market` y
`--only official-routes`; no equivalen a una publicación completa.

## Métricas financieras con autorización separada

Después de la revisión del dueño, proporciona juntas las opciones
`--business-metrics-proposal <proposal.json>` y
`--business-metrics-receipt <receipt.json>`. El entorno debe contener
`CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256` con el hash canónico autorizado.

El recibo exige `owner_id: "salvamalfa"`, `approved_at` válido y
`decision_reference` no vacía. Su hash usa JSON canónico: claves ordenadas,
separadores compactos y UTF-8. Cambiar sangría no cambia su identidad.
No guardes el pin en Git ni lo derives automáticamente de un recibo incluido
en el repositorio. Sin la autorización coincidente, la exportación se rechaza.

## Verificación

```bash
uv run pytest -q tests/test_web_export.py
```

Los casos `local_data` necesitan entradas locales y comprueban que recombinar
los archivos reproduce el contenido público del generador. Las pruebas públicas
usan datos sintéticos; no demuestran una reconstrucción desde fuentes privadas.
