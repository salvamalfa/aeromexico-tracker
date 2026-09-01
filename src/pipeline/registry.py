"""Single explicit registry for ingestion, rebuild, analytics, and dashboard prep."""

from __future__ import annotations

from collections.abc import Iterable

from src.pipeline.model import (
    InputRequirement,
    PipelinePhase,
    PipelineStep,
    RequirementLevel,
)


REQUIRED = RequirementLevel.REQUIRED
OPTIONAL = RequirementLevel.OPTIONAL


def bronze(description: str, *sources: str) -> InputRequirement:
    return InputRequirement(description, bronze_source_systems=tuple(sources))


def files(description: str, *patterns: str, all_paths: bool = True) -> InputRequirement:
    return InputRequirement(description, tuple(patterns), require_all_paths=all_paths)


PIPELINE_STEPS: tuple[PipelineStep, ...] = (
    # Network ingestion. Complementary sources may be unavailable, but are always receipted.
    PipelineStep("ingest.sec_aeromexico", PipelinePhase.INGEST, "SEC/EDGAR filings and traffic reports", "src.ingest.sec.discover:discover_and_download", REQUIRED, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.bmv", PipelinePhase.INGEST, "BMV XBRL packages", "src.ingest.bmv.download:download_bmv_reports", REQUIRED, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.afac", PipelinePhase.INGEST, "AFAC monthly airline statistics", "src.pipeline.actions:ingest_afac", REQUIRED, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.banxico", PipelinePhase.INGEST, "Banxico exchange rates", "src.ingest.macro.banxico:run", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.fuel", PipelinePhase.INGEST, "EIA jet-fuel prices", "src.ingest.macro.fuel:run", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.market", PipelinePhase.INGEST, "Public market prices", "src.ingest.market.prices:run", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.airport_reference", PipelinePhase.INGEST, "Airport reference catalog", "src.ingest.airports.reference:run", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.airport_traffic", PipelinePhase.INGEST, "Airport and airport-group traffic", "src.ingest.airports.groups:run", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.news", PipelinePhase.INGEST, "RSS and GDELT headlines", "src.ingest.news.rss_gdelt:run", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.faa", PipelinePhase.INGEST, "FAA IASA regulatory status", "src.ingest.regulatory.faa:run", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.peers", PipelinePhase.INGEST, "Peer filings and traffic reports", "src.ingest.peers.stage5:main", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.bts", PipelinePhase.INGEST, "BTS T-100 route traffic", "src.ingest.bts.t100:main", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),
    PipelineStep("ingest.nlp_dictionary", PipelinePhase.INGEST, "Loughran-McDonald dictionary", "src.pipeline.actions:ingest_loughran_mcdonald", OPTIONAL, (), ("data/bronze/_manifest.jsonl",), network_required=True),

    # Bronze to Silver. Every required parser fails explicitly on missing source families.
    PipelineStep("parse.peer_discovery", PipelinePhase.PARSE, "Rebuild peer SEC identities and filing indexes from Bronze", "src.pipeline.actions:rebuild_peer_discovery", REQUIRED, (bronze("SEC peer artifacts", "sec"),), ("data/silver/sec_peer_identities.parquet", "data/silver/sec_peer_filings_index.parquet")),
    PipelineStep("parse.sec", PipelinePhase.PARSE, "SEC earnings and traffic into typed Silver facts", "src.parse.sec.pipeline:run_sec_parse", REQUIRED, (bronze("Aeromexico SEC artifacts", "sec"),), ("data/silver/sec_operating_metrics.parquet", "data/silver/sec_financials.parquet"), depends_on=("parse.peer_discovery",)),
    PipelineStep("parse.bmv", PipelinePhase.PARSE, "BMV XBRL into typed Silver facts", "src.parse.bmv.pipeline:run_bmv_parse", REQUIRED, (bronze("BMV XBRL artifacts", "bmv"),), ("data/silver/bmv_financials.parquet", "data/silver/bmv_packages_index.parquet")),
    PipelineStep("parse.afac", PipelinePhase.PARSE, "AFAC workbooks and bulletins into monthly Silver facts", "src.parse.afac.monthly_stats:run_afac_parse", REQUIRED, (bronze("AFAC artifacts", "afac"),), ("data/silver/afac_monthly_stats.parquet",)),
    PipelineStep("parse.complementary", PipelinePhase.PARSE, "Macro, market, airport, and news sources into Silver", "src.parse.stage4:run", REQUIRED, (
        bronze("Exchange-rate artifacts", "banxico_sie", "federal_reserve_h10"),
        bronze("Fuel artifacts", "eia"),
        bronze("Market artifacts", "yahoo_finance"),
        bronze("Airport reference artifacts", "ourairports"),
        bronze("Airport traffic artifacts", "oma_ir", "aicm", "aifa"),
        bronze("News artifacts", "rss", "gdelt"),
    ), ("data/silver/fx_rates.parquet", "data/silver/fuel_prices.parquet", "data/silver/market_prices.parquet", "data/silver/airport_traffic.parquet", "data/silver/news_headlines.parquet")),
    PipelineStep("parse.peers", PipelinePhase.PARSE, "Peer operating and financial reports into Silver", "src.pipeline.actions:parse_peer_reports", REQUIRED, (
        bronze("Viva reports", "viva_ir"), bronze("Ryanair reports", "ryanair_ir"), bronze("Peer SEC artifacts", "sec")
    ), ("data/silver/peer_operating_metrics.parquet", "data/silver/peer_financials.parquet"), depends_on=("parse.peer_discovery",)),
    PipelineStep("parse.bts", PipelinePhase.PARSE, "BTS T-100 segments into Silver", "src.pipeline.actions:parse_bts", REQUIRED, (bronze("BTS T-100 artifacts", "bts_t100"),), ("data/silver/bts_t100_segment.parquet",)),

    # Silver to Gold and executable quality gates.
    PipelineStep("transform.stage4", PipelinePhase.TRANSFORM, "Business calendars, events, and complementary Gold dimensions", "src.transform.stage4:run", REQUIRED, (
        files("Stage 4 Silver inputs", "data/silver/fx_rates.parquet", "data/silver/fuel_prices.parquet", "data/silver/market_prices.parquet", "data/silver/airport_traffic.parquet", "data/silver/afac_monthly_stats.parquet"),
    ), ("data/gold/dim_events.parquet", "data/gold/dim_fx_period.parquet", "data/gold/dim_fuel_period.parquet"), depends_on=("parse.afac", "parse.complementary")),
    PipelineStep("transform.validate_stage4", PipelinePhase.TRANSFORM, "Validate complementary sources and anchor coverage", "src.transform.validate_stage4:run", REQUIRED, (files("Stage 4 outputs", "data/quality/stage4_acceptance.json"),), ("data/quality/stage4_validation_checks.parquet",), depends_on=("transform.stage4",)),
    PipelineStep("transform.validate_stage5", PipelinePhase.TRANSFORM, "Validate peers and BTS reconciliations", "src.transform.validate_stage5:validate_stage5", REQUIRED, (files("Stage 5 Silver inputs", "data/silver/peer_operating_metrics.parquet", "data/silver/bts_t100_segment.parquet", "data/silver/sec_peer_identities.parquet"),), ("data/silver/bts_t100_aeromexico_validation.parquet",), depends_on=("parse.sec", "parse.peers", "parse.bts")),
    PipelineStep("transform.validate_silver", PipelinePhase.TRANSFORM, "Validate all 28 Silver contracts, grains, domains, lineage fields, and relationships", "src.transform.silver_contracts:run_silver_contract_validation", REQUIRED, (files("Complete Silver layer", "data/silver/*.parquet"),), ("data/quality/stage9_silver_contracts.json",), depends_on=("transform.validate_stage4", "transform.validate_stage5", "parse.bmv")),
    PipelineStep("transform.stage6", PipelinePhase.TRANSFORM, "Build dimensional Gold model and DuckDB semantic layer", "src.transform.stage6:run", REQUIRED, (files("Core Silver facts", "data/silver/sec_operating_metrics.parquet", "data/silver/bmv_financials.parquet", "data/silver/afac_monthly_stats.parquet", "data/silver/peer_operating_metrics.parquet", "data/silver/bts_t100_segment.parquet"),), ("data/gold/fact_carrier_metrics.parquet", "data/gold/dim_metric.parquet", "data/warehouse.duckdb"), depends_on=("transform.validate_silver",)),
    PipelineStep("transform.validate_stage6", PipelinePhase.TRANSFORM, "Validate Gold contracts, relationships, and business anchors", "src.transform.validate_stage6:validate_stage6", REQUIRED, (files("Stage 6 model", "data/gold/fact_carrier_metrics.parquet", "data/warehouse.duckdb"),), ("data/quality/stage6_acceptance.json",), depends_on=("transform.stage6",)),

    PipelineStep("analytics.stage7", PipelinePhase.ANALYTICS, "Forecasts, clusters, anomalies, NLP, and business studies", "src.analytics:run", REQUIRED, (files("Validated Gold model", "data/gold/fact_carrier_metrics.parquet", "data/warehouse.duckdb"),), ("data/gold/fact_forecasts.parquet", "data/gold/fact_anomalies.parquet", "data/analytics/stage7_build.json"), depends_on=("transform.validate_stage6",)),
    PipelineStep("analytics.validate_stage7", PipelinePhase.ANALYTICS, "Validate analytical reproducibility and published models", "src.analytics.validate_stage7:validate_stage7", REQUIRED, (files("Analytical outputs", "data/analytics/stage7_build.json", "data/gold/fact_forecasts.parquet"),), ("data/quality/stage7_acceptance.json",), depends_on=("analytics.stage7",)),

    PipelineStep("dashboard.prepare", PipelinePhase.DASHBOARD, "Prepare bounded dashboard extracts and Stage 8 views", "src.dashboard.prepare:run", REQUIRED, (files("Validated analytical outputs", "data/gold/fact_forecasts.parquet", "data/warehouse.duckdb"),), ("data/gold/fact_dashboard_coverage.parquet", "data/gold/fact_route_traffic_summary.parquet", "data/quality/stage8_prepare.json"), depends_on=("analytics.validate_stage7",)),
    PipelineStep(
        "dashboard.validate_stage8",
        PipelinePhase.DASHBOARD,
        "Validate dashboard data, anchors, pages, offline access, disclosures, and performance",
        "src.dashboard.validate_stage8:validate_stage8",
        REQUIRED,
        (
            files(
                "Prepared dashboard outputs",
                "data/gold/fact_dashboard_coverage.parquet",
                "data/gold/fact_route_traffic_summary.parquet",
                "data/warehouse.duckdb",
            ),
        ),
        (
            "data/quality/stage8_acceptance.json",
            "data/quality/stage8_acceptance_checks.parquet",
        ),
        depends_on=("dashboard.prepare",),
    ),
    PipelineStep(
        "dashboard.materialize_stage9",
        PipelinePhase.DASHBOARD,
        "Materialize the public source catalog, Bronze artifacts, record identifiers, lineage bridge, warehouse, and data dictionary",
        "src.transform.stage9:run",
        REQUIRED,
        (
            files(
                "Stage 9 record-bearing Gold outputs",
                "data/gold/fact_carrier_metrics.parquet",
                "data/gold/fact_route_traffic.parquet",
                "data/gold/fact_dashboard_coverage.parquet",
                "data/gold/fact_route_traffic_summary.parquet",
            ),
            files("Immutable Bronze manifest", "data/bronze/_manifest.jsonl"),
        ),
        (
            "data/gold/dim_source.parquet",
            "data/gold/dim_source_artifact.parquet",
            "data/gold/bridge_record_lineage.parquet",
            "data/gold/dim_source_priority.parquet",
            "data/quality/stage9_lineage.json",
            "data/warehouse.duckdb",
            "docs/diccionario-datos.md",
        ),
        depends_on=("dashboard.validate_stage8",),
    ),
    PipelineStep(
        "dashboard.validate_stage9",
        PipelinePhase.DASHBOARD,
        "Validate Stage 9 contracts, identifiers, lineage coverage, model integrity, and business anchors",
        "src.transform.validate_stage9:run",
        REQUIRED,
        (
            files(
                "Materialized Stage 9 metadata",
                "data/gold/dim_source.parquet",
                "data/gold/dim_source_artifact.parquet",
                "data/gold/bridge_record_lineage.parquet",
                "data/warehouse.duckdb",
            ),
        ),
        ("data/quality/stage9_acceptance.json",),
        depends_on=("dashboard.materialize_stage9",),
    ),
)


def validate_registry(steps: Iterable[PipelineStep] = PIPELINE_STEPS) -> None:
    ordered = tuple(steps)
    identifiers = [step.step_id for step in ordered]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Pipeline step identifiers must be unique")
    known: set[str] = set()
    for step in ordered:
        missing = sorted(set(step.depends_on) - known)
        if missing:
            raise ValueError(f"{step.step_id} has forward or unknown dependencies: {missing}")
        known.add(step.step_id)
    phases = {step.phase for step in ordered}
    if phases != set(PipelinePhase):
        raise ValueError(f"Registry does not cover every phase: {sorted(phases)}")


def steps_for_phases(phases: Iterable[PipelinePhase | str]) -> tuple[PipelineStep, ...]:
    selected = {PipelinePhase(phase) for phase in phases}
    return tuple(step for step in PIPELINE_STEPS if step.phase in selected)


validate_registry()
