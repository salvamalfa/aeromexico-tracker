# `src/publish`

The publication gate for `site/`: the *signed object* the dashboard ships
as — a directory built from `web/` plus the exported v1 payloads. See
`web/README.md`.

## Responsabilidad

- `gate.py`: given one or more `analysis_runs/drafts/<period>/<version>.json`
  records, verifies each through the exact functions `stage18.publish` used
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
- The `intent`/`published` receipt (same style as `stage18`'s under
  `analysis_runs/lifecycle/publications/`) goes to
  `analysis_runs/publications/` (local, gitignored — see `.gitignore`'s
  `analysis_runs/` rule) and hashes the *manifest*, not the raw `site/`
  bytes, since the manifest already lists every file's own hash.

Never writes to the approval ledger, never approves/revokes/records
anything. `web/` is the only implementation of each view, this gate its
only publication path. Running
this gate for real (not just its tests) needs an explicit instruction from
the owner — see `REPO_MAP.md`.

## Entradas / salidas

- **Entradas:** one or more `analysis_runs/drafts/<period>/<version>.json`
  record paths (local, non-versioned); the local warehouse (via
  `src/dashboard/`, same as `src/web_export`); `web/` (Node/npm); `contracts/
  web/`.
- **Salidas:** `site/` (versioned); an intent/published receipt under
  `analysis_runs/publications/` (local, non-versioned).

## Punto de entrada

```
uv run python -m src.publish --record analysis_runs/drafts/2026Q2/<hash>.json --out site/
uv run python -m src.publish.verify site/
```

## Comando de prueba focalizada

```
uv run pytest -q tests/test_publish_manifest.py tests/test_publish_verify.py
```

The negative fixtures under `tests/fixtures/site/` (altered byte, extra
file, missing file, disallowed carrier, undeclared field, malformed
approval entry) run in CI with no private data. A full local run of
`gate.py` itself (`local_data`, needs the warehouse and an approved
`analysis_runs/` record) is exercised by `tests/test_publish_gate.py` and,
for the built site's visible parity against the published page, by
`tests/test_site_parity.py` (`browser` + `local_data`).
