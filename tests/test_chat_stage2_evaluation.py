from __future__ import annotations

import json

from src.conversational_analytics.evaluation import verify_observation


def test_quarter_aliases_accept_equivalents_and_reject_wrong_period() -> None:
    from src.conversational_analytics.evaluation_response_checks import (
        response_term_present as _response_term_present,
    )

    for actual in ("2026Q2", "2026 Q2", "2Q26", "2T26"):
        assert _response_term_present("2026Q2", f"Public dashboard period: {actual}.")
    for actual in ("2026Q1", "1Q26", "2T25"):
        assert not _response_term_present("2026Q2", f"Public dashboard period: {actual}.")


def test_stage2_fixture_is_frozen_to_budget_and_preserves_source_lineage() -> None:
    from src.conversational_analytics.data.snapshot import Snapshot
    from src.conversational_analytics.evaluation import (
        BUSINESS_FIXTURE_PATH,
        SAFETY_CURRENT_FIXTURE_PATH,
        STAGE2_PILOT_FIXTURE_PATH,
        phase_cases,
    )
    from src.conversational_analytics.semantic.context import validate_context
    from src.conversational_analytics.service import validate_context as validate_service_context
    from src.conversational_analytics.tools.registry import ToolRegistry

    business = json.loads(BUSINESS_FIXTURE_PATH.read_text(encoding="utf-8"))
    safety = json.loads(SAFETY_CURRENT_FIXTURE_PATH.read_text(encoding="utf-8"))
    derived = json.loads(STAGE2_PILOT_FIXTURE_PATH.read_text(encoding="utf-8"))
    selected = phase_cases(business["cases"], safety["cases"], 2)
    assert [case["id"] for case in selected] == [case["id"] for case in derived["cases"]]
    assert len(selected) == 15
    for source_name, path in (
        ("business_proposed", BUSINESS_FIXTURE_PATH),
        ("safety_current", SAFETY_CURRENT_FIXTURE_PATH),
    ):
        import hashlib

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert derived["lineage"]["source_fixtures"][source_name]["sha256"] == digest
    originals = {
        case["id"]: case
        for source in (business["cases"], safety["cases"])
        for case in source
    }
    for case in derived["cases"]:
        original = originals[case["id"]]
        for field in ("question", "locale", "turns", "rubric", "critical_failures"):
            if field in original:
                assert case.get(field) == original[field]
    registry = ToolRegistry(Snapshot("site"))
    context_case_ids = set()
    for case in derived["cases"]:
        if case.get("context"):
            context_case_ids.add(case["id"])
            semantic_context = validate_context(case["context"])
            service_context = validate_service_context(case["context"])
            result = registry.invoke("get_dashboard_context", {}, context=case["context"])
            assert service_context == semantic_context == result["context"] == case["context"]
    assert {
        "N02", "N11", "N12", "N13", "en_relative_share_change", "es_ratio_average"
    } <= context_case_ids


def test_clarification_accepts_imperatives_without_invented_numeric_answers() -> None:
    from src.conversational_analytics.evaluation_live_scoring import score_live_case

    case = {
        "id": "clarify-case",
        "expected": {"status": "clarify"},
    }
    options = {
        "expected_versions": {},
        "scope": {},
        "metric_dimensions": {},
    }
    _, reasonable = score_live_case(
        case, [], "Please specify the quarter and segment.", **options
    )
    assert reasonable["passed"], reasonable["failures"]

    _, invented = score_live_case(
        case, [], "Please specify the quarter; the share fell by 8.9%.", **options
    )
    assert not invented["passed"]
    assert "numeric_answer_given_when_clarification_expected" in invented["failures"]


def test_relative_share_gold_rejects_percentage_points_labeled_as_percent() -> None:
    from src.conversational_analytics.evaluation import STAGE2_PILOT_FIXTURE_PATH

    payload = json.loads(STAGE2_PILOT_FIXTURE_PATH.read_text(encoding="utf-8"))
    case = next(case for case in payload["cases"] if case["id"] == "en_relative_share_change")
    rows = [
        {
            **row,
            "availability": "available",
        }
        for row in case["expected"]["rows"]
    ]
    valid = verify_observation(
        case,
        {
            "status": "supported",
            "plan": case["expected"]["plan"],
            "rows": rows,
            "response": "Relative change: -3.99% from 2T25 to 2T26; separate share-point delta is -1.01 pp.",
        },
    )
    assert valid.passed, valid.failures

    confused = verify_observation(
        case,
        {
            "status": "supported",
            "plan": case["expected"]["plan"],
            "rows": rows,
            "response": "Relative change: -3.99% from 2T25 to 2T26; this is the same as -1.01%.",
        },
    )
    assert not confused.passed
    assert "percentage_point_delta_mislabelled_as_relative_percent" in confused.failures


def test_viva_missing_company_gold_allows_labeled_afac_with_evidence_only() -> None:
    from src.conversational_analytics.evaluation import STAGE2_PILOT_FIXTURE_PATH
    from src.conversational_analytics.evaluation_live_scoring import score_live_case

    payload = json.loads(STAGE2_PILOT_FIXTURE_PATH.read_text(encoding="utf-8"))
    case = next(case for case in payload["cases"] if case["id"] == "es_viva_missing_company_passengers")
    versions = payload["expected_versions"]
    scope = {}
    metric_dimensions = {"afac_passengers": ["segment"]}
    plan = case["expected"]["plan"]
    row = case["expected"]["rows"][0]
    tool_calls = [{
        "name": "query_metrics",
        "arguments": {
            "metric_ids": plan["metric_ids"],
            "entity_ids": plan["entity_ids"],
            "periods": plan["periods"],
            "segment": "total",
        },
        "scope": scope,
        "result": {**versions, "rows": [row], "truncated": False},
    }]
    options = {
        "expected_versions": versions,
        "scope": scope,
        "metric_dimensions": metric_dimensions,
    }
    _, labeled_afac = score_live_case(
        case,
        tool_calls,
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22 y comparó la serie con 1T23; "
            "la serie reportada por la empresa no está disponible."
        ),
        **options,
    )
    assert labeled_afac["passed"], labeled_afac["failures"]

    for response in (
        (
            "Viva reportó 4,876,764 pasajeros; la cifra también aparece en AFAC y no está disponible "
            "para la empresa."
        ),
        (
            "En 2T22, 4,876,764 pasajeros fueron reportados por Viva según AFAC; "
            "la serie de empresa no está disponible."
        ),
        (
            "AFAC reportó 4,876,764 pasajeros para Viva; Viva informó 4,876,764 pasajeros; "
            "la serie no está disponible para la empresa."
        ),
    ):
        _, misattributed = score_live_case(case, tool_calls, response, **options)
        assert not misattributed["passed"]
        assert "AFAC_value_misrepresented_as_company_report" in misattributed["failures"]

    _, invented = score_live_case(
        case,
        tool_calls,
        (
            "AFAC registró 4,876,764 pasajeros de Viva y 5,000,000 pasajeros; "
            "la serie de empresa no está disponible."
        ),
        **options,
    )
    assert not invented["passed"]
    assert "unsupported_or_incorrect_passenger_count" in invented["failures"]

    for response in (
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22; el dato corregido sería 5,000,000; "
            "la serie de empresa no está disponible."
        ),
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22; la cifra comparable fue 5,000,000; "
            "la serie de empresa no está disponible."
        ),
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22 y la variación fue 8.9%; "
            "la serie de empresa no está disponible."
        ),
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22, pero el dato correcto fue 2025Q2; "
            "la serie de empresa no está disponible."
        ),
    ):
        _, ungrounded = score_live_case(case, tool_calls, response, **options)
        assert not ungrounded["passed"]
        assert "response_contains_numeric_claim_without_fixture_evidence" in ungrounded["failures"]

    _, no_evidence = score_live_case(
        case,
        [],
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22; "
            "la serie reportada por la empresa no está disponible."
        ),
        **options,
    )
    assert not no_evidence["passed"]
    assert "supported_answer_not_observed" in no_evidence["failures"]

