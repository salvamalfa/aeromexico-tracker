# Contratos públicos de Airlines Tracker

Los esquemas JSON de esta carpeta definen los datos que pueden salir hacia
la interfaz y el chat. Usan JSON Schema draft 2020-12.
`privacy.yaml` fija además la frontera entre información pública y privada.

## Qué describe cada contrato

| Esquema | Contenido |
|---|---|
| `flights.schema.json` | Proyección pública de Vuelos producida por `integration_flight_payload(build_flight_payload())`. No describe el objeto interno completo del generador. |
| `executive.schema.json` | Registros y vistas financieras de `build_executive_payload()`. |
| `analysis.schema.json` y contratos editoriales específicos | Lecturas autorizadas por `consumer_payload(record)`, sin secciones privadas para lectores y con citas públicas. Cada edición usa su contrato exacto. |
| `market.schema.json`, `market_demand.schema.json` | Participación de aerolíneas y demanda aeroportuaria, con universos distintos. |
| `official-routes.schema.json` | Red AFAC/BTS del mapa oficial; su validación no equivale a activación. |
| `news.schema.json` | Archivo público de noticias. |
| `business_metrics.schema.json`, `business_metrics_approval.schema.json` | Series financieras aprobadas y recibo ligado a las definiciones y propuesta exactas. |
| `publication_manifest.schema.json` | Inventario de archivos, hashes, contratos e identidades de análisis de una publicación. |

Las citas solo exponen campos públicos: URL autorizada por el esquema,
texto visible y valor citado. No salen originales, extractos de evidencia,
nodos de cálculo ni linaje. El exportador está en
[`src/web_export/analysis.py`](../../src/web_export/analysis.py).

En `executive.json`, `metadata.default_period` corresponde al último
trimestre financiero completo con registro y vista, entre la serie principal
y los emisores. No exige un trimestre común de Industria ni una tesis nueva.
El consumidor aplica ese criterio a publicaciones históricas cuyo valor
quedó rezagado y respeta enlaces históricos válidos. Usa los campos existentes;
no reescribe esquemas ni hashes históricos.

Las métricas financieras mantienen calendario/fiscal, moneda, unidad reportada,
conversión de divisas y referencias. Sin un recibo coincidente en
`config/chat/business-metrics-approval-receipt.json`, la publicación no
incorpora esos archivos.

## Privacidad y consumidores

`privacy.yaml` declara aerolíneas admitidas en celdas estimadas, campos
prohibidos en cualquier nivel y tamaño máximo por archivo. No confundas esa
lista con una restricción general de todas las observaciones de aerolíneas.

Los contratos se mantienen a mano. Cambiarlos es una decisión explícita;
no es un efecto automático de modificar el generador.
Los consumen `src/web_export/`, los verificadores de publicación y el lector
de snapshots del chat. Las pruebas usan datos sintéticos públicos y, con
`local_data`, el conjunto real de datos.

## Versiones exactas

Cada manifiesto identifica los contratos por SHA-256 de sus bytes.
[`contract_versions.py`](../../src/web_export/contract_versions.py)
acepta el archivo vigente si coincide y, para los contratos que lo permiten,
una versión retenida explícitamente en `versions/<SHA256>/`.
Reconoce versiones de Vuelos, Mercado, demanda aeroportuaria y citas de análisis;
no busca la versión «más cercana» ni registra archivos automáticamente.

Un campo nuevo no puede validarse con el hash de un esquema antiguo.
Se rechazan hashes desconocidos, archivos alterados, rutas inseguras y enlaces
simbólicos. Privacidad y aprobación siguen exigiendo sus hashes vigentes.
Un manifiesto nuevo usa el contrato vigente. Conservar un esquema anterior
no aprueba datos ni modifica manifiestos, recibos o aprobaciones existentes.

Las regresiones están en `tests/test_contract_versions.py`,
`tests/test_chat_semantic.py` y `tests/test_publish_verify*.py`.

## Evolucionar el contrato

1. Cambia el generador en `src/dashboard/`, no el HTML compilado.
2. Ajusta el esquema y revisa la privacidad. Un campo que no deba ser público
   debe quedar fuera de la proyección; añádelo a `forbidden_fields` cuando corresponda.
3. Actualiza los exportadores y su [documentación](../../src/web_export/README.md).
4. Regenera los tipos de la interfaz y ejecuta las pruebas:

```bash
cd web
npm run gen:types
npm run check
npm run test
cd ..
uv run pytest -q tests/test_web_contracts.py tests/test_web_privacy.py
```

Los casos `local_data` necesitan warehouse e insumos locales. Los demás
validan los datos sintéticos de `tests/fixtures/web/`. Revisa además los
consumidores afectados y el perfil de publicación aplicable:
[guía del gate](../../src/publish/README.md).
