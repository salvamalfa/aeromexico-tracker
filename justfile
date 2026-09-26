set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]
set shell := ["bash", "-cu"]

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

dashboard-validate:
    uv run python -m src.dashboard.validate_stage8

stage11-validate:
    uv run pytest -q tests/test_stage11_executive_prototype.py

stage12-prototype:
    uv run python -m src.analysis_agent.stage12

stage12-validate:
    uv run pytest -q tests/test_stage12_diagnosis.py tests/test_stage11_executive_prototype.py

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

stage13-extract:
    uv run python -m src.analysis_agent.stage13

stage13-review:
    uv run python -m src.analysis_agent.stage13_report

stage13-html tools_dir:
    uv run python -m src.analysis_agent.stage13_html --tools-dir "{{tools_dir}}"

stage13-validate:
    uv run pytest -q tests/test_stage13_financial_history.py tests/test_stage9_silver_contracts.py tests/test_pipeline_orchestration.py

stage14-prepare quarter:
    uv run python -m src.analysis_agent.evidence prepare "{{quarter}}"

stage14-prototype:
    uv run python -m src.analysis_agent.stage14_html

stage14-validate:
    uv run pytest -q tests/test_stage14_evidence.py

stage15-calculate package:
    uv run python -m src.analysis_agent.quantitative "{{package}}"

stage15-prototype:
    uv run python -m src.analysis_agent.stage15_html

stage15-validate:
    uv run pytest -q tests/test_stage15_quantitative.py
