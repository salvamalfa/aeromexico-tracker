# Vista previa del Dashboard v2 en Pages (`/v2/`)

Fecha: 30 de septiembre de 2026.

## Decisión del dueño

- **Qué se publica:** la v2 (PR #77) se publica en `/v2/` sin fusionarse a `master`.
- **Qué commit:** fijo, en `7d7957c`, el `site/` re-firmado con el gate y el registro
  2026Q2 aprobado.
- **Qué autoriza:** la publicación de las estimaciones internacionales y de ocupación
  que ya aprobó para la v2 (fases 3 y 4). La tesis por aerolínea (fase 5) va después.

## Cómo funciona

- **Pin:** `.github/pages-preview.json` fija `path` (`v2`) y `ref`, un SHA completo;
  nunca una rama.
- **Validación del pin:** el job `preview` de `pages.yml` exige que `path` sea un
  segmento seguro y no choque con `site/` de `master`, y que `ref` sea un SHA de 40
  caracteres.
- **Verificación del `site/`:** el job hace checkout de ese commit y corre
  `src.publish.verify site/` con el código y los contratos del propio commit. Su
  `site/` está firmado contra esos contratos, no contra los de `master`.
- **Checks del commit fijado:** antes de verificar, `preview` exige que ese commit ya
  tenga `test` y `web` en verde (check runs de la API de GitHub, el más reciente de
  cada uno). El job `ci` de este workflow prueba el código de `master`, no el del
  commit fijado.
- **Permisos:** el workflow es de solo lectura. Solo `deploy` recibe `pages: write` e
  `id-token: write`, y ese job solo copia archivos. `preview`, que ejecuta código del
  commit fijado, no recibe credenciales de despliegue (hallazgos de Codex en el PR
  #80).
- **Despliegue:** `deploy` depende de `verify` (el `site/` de `master`), `preview` y
  `ci`. Arma `_pages/` con el `site/` de `master` en la raíz y el `site/` fijado en
  `_pages/v2/`, y publica eso. Si una verificación falla, no se publica nada.
- **Rutas:** el sitio usa rutas relativas (`base: "./"` en Vite y `fetch("data/v1/…")`),
  así que funciona igual bajo `/v2/`.
- **Disparadores:** además de los cambios en `site/**`, el deploy corre cuando cambia
  `.github/pages-preview.json`.

## Validación

- **Prueba nueva:** `tests/test_pages_preview.py` valida el pin y que el workflow lo
  use.
- **Simulación local del ensamblado:** `site/` de `master` en la raíz y
  `git archive 7d7957c site` en `v2/`, servido con `http.server`. Con Playwright
  cargaron `/` ("Aeroméxico Tracker") y `/v2/` ("Aerolíneas MX Tracker"), incluida la
  pestaña de Vuelos. No hubo errores de consola ni respuestas HTTP ≥ 400.
- **Verificación del commit fijado:** en `7d7957c`, `src.publish.verify site/` pasa.

## Límites

- **Visibilidad:** `/v2/` es público para quien tenga la liga. No se enlaza desde la
  v1.
- **Actualizaciones:** la vista previa no sigue a la rama. Cada actualización es un PR
  a `master` que cambia `ref`.
- **Cuándo retirarla:** al fusionar la v2, se borra el archivo y `/v2/` desaparece en
  el siguiente deploy.

## Cierre (30 sep 2026)

- **La v2 pasa a la raíz:** el dueño aprobó que la v2 sea la versión principal y el
  PR #77 se fusiona a `master`.
- **Pin retirado:** en ese mismo PR se borra `.github/pages-preview.json`, así que
  `/v2/` deja de publicarse.
- **Mecanismo conservado:** el mecanismo de `pages.yml` sigue disponible. Sin pin, el
  job `preview` no hace nada y `tests/test_pages_preview.py` omite la validación del
  pin.
