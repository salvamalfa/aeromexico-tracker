set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

default:
    just --list

setup:
    uv sync --all-extras --all-groups
    uv run playwright install chromium

ingest:
    uv run python -m src.ingest

parse:
    uv run python -m src.parse

transform:
    uv run python -m src.transform

test:
    uv run pytest

rebuild:
    uv run python -m src.rebuild

dashboard:
    uv run streamlit run streamlit_app.py

dashboard-validate:
    uv run python -m src.dashboard.validate_stage8

smoke-test:
    uv run python -m src.smoke_test

verify-identities:
    uv run python -m src.verify_identities

sec-validate:
    uv run python -m src.parse.sec.validate

sec-series:
    uv run python -m src.parse.sec.inspect_series

bmv-validate:
    uv run python -m src.parse.bmv.validate

afac-validate:
    uv run python -m src.parse.afac.validate
