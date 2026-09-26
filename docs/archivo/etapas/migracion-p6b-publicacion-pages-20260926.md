# P6b · Gate de publicación sobre `site/`, `verify.py` y GitHub Pages · 26 sep 2026

## Alcance

Fase 5 de `docs/arquitectura/auditoria-arquitectura-20260926.md`: el gate
de publicación deja de firmar un HTML de 7 MB (`stage18`) y firma en su
lugar un directorio `site/` — la página de `web/` ya compilada más su
payload `data/v1/` — con un manifiesto (`publication_manifest.json`) que
lista el commit, el hash de cada contrato, el SHA-256/tamaño de cada
archivo y las entradas del `analysis-manifest` vigente.

## Qué se hizo

1. **`src/publish/`** (`gate.py`, `manifest.py`, `verify.py`,
   `__main__.py`, `README.md`). `python -m src.publish --record <path>
   --out site/`:
   - re-verifica cada registro dado con `lifecycle.consumer_payload`/
     `verified_inputs` — las mismas funciones que `stage18.publish` usa,
     bajo el mismo `flow.writer` — y se niega (excepción
     `PublicationRefused`, salida no cero) si algo no está aprobado o fue
     alterado; nada se escribe;
   - exporta v1 (Vuelos/ejecutivo completos, análisis solo de los
     periodos dados) a un directorio temporal, reutilizando
     `src.web_export.{flights,executive}` y las funciones privadas de
     `analysis.py` (`_drop_private_sections`, `_citations_by_claim`) para
     no volver a consultar el ledger una segunda vez tras soltar el
     candado de escritura;
   - copia ese payload a `web/public/data/v1` (scratch local ya
     ignorado) y corre `npm ci && npm run build`;
   - ensambla `site/` a partir de `web/dist/` (Vite ya copia `public/`
     dentro de `dist/`, así que "dist + datos" es literalmente eso) en un
     directorio temporal hermano, firma `publication_manifest.json` y
     hace el swap con un `rename` atómico (con respaldo `.prev-*` por si
     el rename final falla);
   - escribe un recibo intent/published en `analysis_runs/publications/`
     (local, ignorado) que hashea el manifiesto, no los bytes crudos.
   - `contracts/web/publication_manifest.schema.json` describe ese
     manifiesto.
2. **`src/publish/verify.py`** (`python -m src.publish.verify site/`):
   sin datos privados. Revisa el manifiesto contra su esquema, cada
   archivo listado (hash + tamaño), que no exista un archivo no listado,
   cada `data/v1/**/*.json` contra su sub-esquema de
   `contracts/web/*.schema.json` y `privacy.yaml`, y que cada entrada de
   `analysis_manifest` tenga sus campos requeridos no vacíos.
   `tests/fixtures/site/` (generado por `_generate.py` desde los mismos
   fixtures públicos de `tests/fixtures/web/`) trae el sitio válido y seis
   negativos: byte alterado, archivo extra, archivo faltante, aerolínea no
   permitida, campo no declarado, entrada de aprobación malformada — los
   seis se rechazan (`tests/test_publish_verify.py`).
3. **`.github/workflows/pages.yml`**: en push a `master` que toque
   `site/**`, o `workflow_dispatch`: job `verify` (checkout, `uv sync
   --locked --no-group dev`, `uv run python -m src.publish.verify
   site/`) y luego `deploy` (`actions/configure-pages` +
   `upload-pages-artifact` con `path: site` + `deploy-pages`). Sin
   secretos, sin reconstrucción de datos.
4. **Corrida real, autorizada por el dueño** (el mismo registro ya
   aprobado y publicado de 2026Q2 —
   `analysis_runs/drafts/2026Q2/26bc9135….json`): `site/` quedó con 34
   archivos, 3.7 MB, `python -m src.publish.verify site/` en verde, y
   `tests/test_site_parity.py` (Playwright, `browser`+`local_data`, 3/3)
   confirma que el `site/` servido coincide con
   `static/aeromexico_tracker.html` (pestañas, texto de lectura por
   trimestre, KPIs de economía) para toda la matriz de 22 trimestres.
   `analysis_runs/drafts/`, aprobaciones y `stage18` quedaron intactos.
5. Docs: `REPO_MAP.md` (fila de `src/publish/`, sección "Publicación en
   GitHub Pages", comandos), `web/README.md` (sección "Publicación") y
   este reporte.

## Verificación

```
uv run pytest -m "not local_data and not browser" -q          # 539 passed
uv run pytest -q tests/test_publish_manifest.py tests/test_publish_verify.py   # 15 passed
uv run pytest -m local_data -q tests/test_publish_gate.py      # 4 passed
uv run pytest -m "browser and local_data" -q tests/test_site_parity.py  # 3 passed
uv run python -m src.publish.verify site/                      # valid
cd web && npm run check && npm run test                        # sin cambios en web/; ya verdes en P6a
```

## Pendiente / riesgo

- El paso manual único del dueño: **Settings → Pages → Source: GitHub
  Actions** en el repositorio de GitHub, para que
  `.github/workflows/pages.yml` pueda desplegar. Sin ese cambio el job
  `deploy` fallará en `actions/deploy-pages` aunque `verify` pase.
- `tests/test_publish_gate.py` no ejerce el pipeline completo
  (`npm ci && npm run build`) para no duplicar el costo de
  `tests/test_site_parity.py`/la corrida real ya hecha; si `build_web()`
  cambia, correr `python -m src.publish` a mano localmente sigue siendo
  la prueba de humo más directa.
- `site/` publicado en esta sesión trae solo la aprobación de 2026Q2 (la
  única vigente en este checkout); una futura aprobación de otro
  trimestre necesita una nueva corrida del gate con ese `--record`
  adicional.

## Próximo paso para el tracker

Marcar P6b listo en `docs/arquitectura/migracion-estado.md` (tabla +
bitácora) e iniciar P7 (retiro de Streamlit) — no lo hace este paquete
por instrucción del coordinador.
