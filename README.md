# Aeromexico Tracker

Reproducible public-data pipeline and quarterly business analytics dashboard for
Grupo Aeromexico S.A.B. de C.V. (`AERO`, NYSE/BMV; SEC CIK `0001561861`).

The project uses an immutable bronze layer, typed silver datasets, dimensional
gold tables, DuckDB/Parquet storage, and explicit source lineage. It is a
portfolio analytics project, not an investment recommendation.

## Current status

Stages 0 and 1 are complete. SEC EDGAR ingestion, filing classification,
quarterly/monthly parsing, source crosschecks, and offline reconstruction are
production-ready within the documented coverage. BMV and later sources remain pending.

## Setup

Prerequisites: Git, `uv`, and `just`.

1. Copy `.env.example` to `.env` and set a real `SEC_USER_AGENT` contact.
2. Run `just setup`.
3. Run `just test`.
4. Run `just smoke-test` to inspect lightweight source connectivity.

The environment is locked in `uv.lock`. All project commands run through `uv`,
so global Python packages are ignored.

## Common commands

| Command | Purpose |
|---|---|
| `just setup` | Install the locked environment and Chromium |
| `just ingest` | Run registered network ingestion jobs |
| `just parse` | Rebuild silver data from immutable bronze files |
| `just transform` | Build gold tables from silver data |
| `just rebuild` | Offline parse + transform from bronze |
| `just test` | Run the test suite |
| `just smoke-test` | Probe source accessibility without large downloads |
| `just dashboard` | Launch the Streamlit application |
| `just sec-validate` | Validate SEC anchors, invariants, lineage, and crosschecks |
| `just sec-series` | Print quarterly load factor, TRASM, and CASM ex-fuel |

## Repository layout

```text
data/bronze/       immutable raw downloads; not committed
data/silver/       typed source-faithful Parquet; not committed
data/gold/         dimensional consumption tables; not committed
data/quality/      append-only data-quality events
docs/plan/         authoritative staged implementation plan
docs/etapas/       stage closure and connectivity reports
docs/decisiones/   architecture decision records
src/common/        HTTP, storage, logging, and quality infrastructure
src/ingest/        source-specific network ingestion
src/parse/         bronze-to-silver processing
src/transform/     silver-to-gold transformations
src/analytics/     forecasting, clustering, NLP, anomaly detection
src/dashboard/     Streamlit application
sql/               versioned silver and gold SQL
tests/             unit, contract, invariant, and frozen-fixture tests
```

Raw downloads are never overwritten. Their SHA-256 hashes, source URLs, and
metadata are written to `data/bronze/_manifest.jsonl`; changed source content is
also recorded in `_restatements.jsonl`.

See [the implementation plan](docs/plan/README.md) for scope, sources, stage
gates, and acceptance criteria.
