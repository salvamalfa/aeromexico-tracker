# `src/publish`

The publication gate for `site/`: the *signed object* the dashboard ships
as — a directory built from `web/` plus the exported v1 payloads. See
`web/README.md`.

## Responsabilidad

- `gate.py`: given one or more `analysis_runs/drafts/<period>/<version>.json`
  records, verifies each through
  (`src.analysis_agent.lifecycle.consumer_payload`/`verified_inputs`, under
  the ledger's writer lock) and refuses (raises `PublicationRefused`, CLI
  exit 1) if any record is not exactly, currently approved — nothing is
  written. On success it runs `src.web_export` into a temp directory
  (flights and executive for every period, analysis only for the given,
  now-verified records), copies that into `web/public/data/v1` (local,
  gitignored dev scratch — see `.gitignore`), and runs `npm ci && npm run
  build` in `web/`, all with the ledger lock released (an `npm run build`
  is slow; a human's approval/revocation should not block on it). Records
  are then **re-verified a second time**, under a fresh ledger lock held
  through the swap itself, immediately before `site/` is replaced — closing
  the window where a revocation could otherwise land between the first
  check and the swap. Only after that second check passes does it assemble
  `site/` from the built `web/dist/` (Vite already copies `public/` into
  `dist/`, so this *is* "dist + data").
  For a strictly interface-only change, `--ui-only` reuses the existing
  public `data/v1/` payload. It first requires the whole tracked `site/` to
  be byte-for-byte unchanged from one pinned `origin/master` commit, verifies the site manifest
  and its exact approved analysis-manifest entries, then checks that the
  frontend build preserved every data file hash and size. It retains the
  trusted manifest's contract hashes too, so a UI release does not change the
  conversation's data version merely because this codebase added a dormant,
  optional contract. It repeats the trusted-site and approval checks
  immediately before the atomic swap, and refuses if the trusted ref moved
  during the build. This mode cannot bless edited data by
  rebuilding its manifest, and it never invokes warehouse exporters.
- `--business-metrics-only` uses the same immutable published-site baseline
  and exact current analysis approval, then adds only the separately pinned
  business-metrics payload and receipt. It requires the baseline data files to
  remain byte-identical, validates the completed candidate site before swap,
  and rechecks both the trusted baseline and Analysis Agent approval under the
  ledger lock immediately before the atomic replacement.
- `--preserve-published-data` prepara el mapa solo de vuelos con el histórico
  completo. Toma el `site/` firmado exacto de `origin/master`, revalida las
  cuatro aprobaciones con la implementación de esa base y los expedientes
  actuales antes/después del build, y conserva **todos** los archivos de
  `data/v1/` byte por byte. Protege los renderers de análisis, fuentes y
  contratos; no reconstruye modelos, crea aprobaciones ni activa datos nuevos.
  El gate normal conserva sus comprobaciones estrictas. El candidato se
  verifica antes del reemplazo y no se despliega: #133 requiere aprobación.
- `--flights-only` proyecta las celdas aceptadas de 2T26 sobre el sitio público
  auditado, sin reconstruir el warehouse ni los otros exportadores. Exige la
  edición exacta de vuelos, el valor anterior de cada sustitución y la
  conciliación por operador/mes/ámbito. Revalida las cuatro aprobaciones con su
  implementación publicada y conserva el resto de payloads e identidades antes
  y después del build. La autorización específica del 19 de octubre cubre esta
  proyección y su tarjeta ponderada; no aprueba tesis nuevas, M11 ni calendarios.
- `manifest.py`: builds and (de)serializes `publication_manifest.json` —
  the code commit (`git rev-parse HEAD`), each `contracts/web/*` file's own
  SHA-256 (its "version"), every other file under `site/` with its
  SHA-256/size (sorted, manifest itself excluded), and the current
  analysis-manifest entries (`period_id`, `version`, `content_hash`,
  `evidence_fingerprint`, `approval_event`, `audit_hash` — the same fields
  the published page's `#analysis-manifest` carries).
- `verify.py` (`python -m src.publish.verify site/`): CI-safe, no private
  data. Checks the manifest against `contracts/web/
  publication_manifest.schema.json`, every listed file's hash/size, no
  unlisted file present, every `data/v1/**/*.json` file against its
  `contracts/web/*.schema.json` sub-schema and `contracts/web/privacy.yaml`,
  and that every `analysis_manifest` entry is well-formed. This is exactly
  what `.github/workflows/pages.yml` runs before deploying.
- `site/` itself is *not* gitignored: an approved run's output is committed
  like any other file, then deployed as-is by CI (`.github/workflows/
  pages.yml` never rebuilds it, never touches `analysis_runs/`).
- The `intent`/`published` receipt goes to
  `analysis_runs/publications/` (local, gitignored — see `.gitignore`'s
  `analysis_runs/` rule) and hashes the *manifest*, not the raw `site/`
  bytes, since the manifest already lists every file's own hash.

Never writes to the approval ledger, never approves/revokes/records
anything. `web/` is the only implementation of each view, this gate its
only publication path. `AGENTS.md` permanently authorizes agents to run this
gate for a requested routine site change using an already approved record, to
commit `site/` in a PR, and to follow the Pages deploy through live
verification. A new approval, changed data meaning, or another higher-risk
action still needs the owner's specific authorization. See `REPO_MAP.md`.

## Entradas / salidas

- **Entradas:** one or more `analysis_runs/drafts/<period>/<version>.json`
  record paths (local, non-versioned); the local warehouse (via
  `src/dashboard/`, same as `src/web_export`); `web/` (Node/npm); `contracts/
  web/`.
- **Salidas:** `site/` (versioned); an intent/published receipt under
  `analysis_runs/publications/` (local, non-versioned).

Los nuevos registros de entidad viven en
`analysis_runs/drafts/<entity_key>/<period>/<version>.json`. Para publicar el
mismo trimestre de Aeroméxico, Volaris, Viva e Industria, pasar los cuatro
registros mediante cuatro opciones `--record`. Cada uno debe conservar su
aprobación vigente y su identidad de entidad, trimestre y versión. El gate
rechaza dos versiones de una misma entidad y trimestre.

El registro histórico de Aeroméxico conserva
`data/v1/analysis/<period>.json` y sus bytes publicados. Los nuevos registros
se exportan a `data/v1/analysis/<entity_key>/<period>.json`, con `entity_key`
en el payload y el manifest. Una entrada histórica sin ese campo corresponde
a Aeroméxico. El verificador comprueba que ruta, encabezado y manifest
coincidan; la presencia de un archivo por sí sola no acredita aprobación.

## Punto de entrada

```
uv run python -m src.publish --record analysis_runs/drafts/2026Q2/<hash>.json --out site/
uv run python -m src.publish --ui-only --record analysis_runs/drafts/2026Q2/<hash>.json --out site/
uv run python -m src.publish --business-metrics-only --record analysis_runs/drafts/2026Q2/<hash>.json --out site/
uv run python -m src.publish.verify site/
```

## Comando de prueba focalizada

```
uv run pytest -q tests/test_publish_manifest.py tests/test_publish_verify.py tests/test_publish_ui_only.py
```

The negative fixtures under `tests/fixtures/site/` (altered byte, extra
file, missing file, disallowed carrier, undeclared field, malformed
approval entry) run in CI with no private data. A full local run of
`gate.py` itself (`local_data`, needs the warehouse and an approved
`analysis_runs/` record) is exercised by `tests/test_publish_gate.py` and,
for the built site's visible parity against the published page, by
`tests/test_site_parity.py` (`browser` + `local_data`).

El ledger conserva aprobaciones técnicas históricas cuando cambia la huella
de implementación. Para reproducir una publicación, selecciona sus cuatro
registros exactos con `--record`; toma las identidades de
`site/publication_manifest.json`. El descubrimiento automático rechaza
múltiples versiones aprobadas de una misma entidad y trimestre. En un
export de desarrollo, pasa ese `analysis_manifest` explícitamente a
`src.web_export.analysis.export_analysis(..., manifest=...)`; no revoques
autorizaciones históricas ni elijas una versión por fecha para eludir el guard.
