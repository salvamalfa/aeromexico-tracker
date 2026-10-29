"""Independent synthetic policy counterexamples; these never certify live sources."""

import copy

import pytest

from src.source_updates import global_readiness as global_gate
from src.source_updates import round_tasks
from src.source_updates.catalog import product_map

MONTHLY_REQUIRED = frozenset({
        "am_traffic_ir",
        "volaris_traffic_ir",
        "viva_traffic",
        "afac_carriers",
        "afac_airports",
        "bts_segments",
        "gap_traffic",
        "asur_traffic",
        "oma_traffic",
        "aicm_traffic",
        "aifa_traffic",
        "banxico",
        "fuel",
        "equities",
})
QUARTERLY_REQUIRED = frozenset(
    {"am_financials", "volaris_sec", "viva_financials", "banxico", "fuel", "equities", "aerocivil"}
)
MONTHLY_CONDITIONAL = frozenset({"am_sec", "afac_countries", "afac_margins", "h10", "derived"})
QUARTERLY_CONDITIONAL = frozenset(
    {
        "am_sec",
        "bmv_xbrl",
        "h10",
        "aicm_slots",
        "airports_reference",
        "dictionary",
        "peer_profiles",
        "curated_context",
        "derived",
        "aena",
    }
)
QUARTERLY_OPTIONAL = frozenset(
    {
        "delta_sec",
        "ryanair_sec",
        "ryanair_ir",
        "anac",
        "caa",
        "am_routes",
        "oma_routes",
        "colima",
        "aifa_roster",
        "iasa",
    }
)


def task(product, cadence, *, used=True):
    key = f"{cadence}_{product}"
    return {
        "id": key,
        "product": product,
        "cadence": cadence,
        "period": "2026M09" if cadence == "monthly" else "2026Q3",
        "used": used,
        "depends_on": [],
        # Unsupported is honest: evaluate tests policy, never source extraction.
        "adapter": "unsupported",
        "workspace": f"tmp/source-updates/independent-global-contract/{key}",
        "receipt_id": "a" * 32,
        "candidate_as_of": "2026-10-21T12:00:00-06:00",
    }


def recipe(kind="monthly"):
    items = []
    cadences = ("monthly", "quarterly") if kind == "combined" else (kind,)
    for cadence in cadences:
        required = MONTHLY_REQUIRED if cadence == "monthly" else QUARTERLY_REQUIRED
        for product, definition in product_map().items():
            if definition["cadence"] in (cadence, "both"):
                items.append(task(product, cadence, used=product in required))
    return {
        "version": 1,
        "round": kind,
        "as_of": "2026-10-21T12:00:00-06:00",
        "monthly_period": "2026M09",
        "quarterly_period": "2026Q3",
        "items": items,
        "releases": [],
    }


def outcomes(value, *, availability=True, editorial=True):
    results = {
        item["id"]: {
            "status": "checks_passed",
            "source_conditions": [],
            "latest_source_availability_verified": availability,
            "semantic_acceptance_verified": item["product"] == "aerocivil",
        }
        for item in value["items"]
    }
    if editorial and value["round"] in {"monthly", "combined"}:
        # Policy fixture only, never a physical editorial review or real search.
        results[round_tasks.EDITORIAL_ID] = {
            "status": "checks_passed",
            "period": value["monthly_period"],
        }
    return results


def selected(value, product, cadence=None):
    return next(
        item
        for item in value["items"]
        if item["product"] == product and (cadence is None or item["cadence"] == cadence)
    )


def test_approved_policy_matches_all_catalogued_tasks_without_silent_defaults():
    expected = {
        "monthly": (MONTHLY_REQUIRED, MONTHLY_CONDITIONAL, frozenset({"rss", "gdelt"})),
        "quarterly": (QUARTERLY_REQUIRED, QUARTERLY_CONDITIONAL, QUARTERLY_OPTIONAL),
    }
    for cadence, groups in expected.items():
        actual = (
            global_gate.REQUIRED[cadence],
            global_gate.CONDITIONAL[cadence],
            global_gate.OPTIONAL[cadence],
        )
        assert actual == groups
        assert all(isinstance(group, frozenset) for group in actual)
        assert sum(map(len, groups)) == len(set.union(*(set(group) for group in groups)))
        assert set.union(*(set(group) for group in groups)) == {
            name for name, definition in product_map().items() if definition["cadence"] in (cadence, "both")
        }
    assert "news_errors" not in set.union(*(set(group) for groups in expected.values() for group in groups))


@pytest.mark.parametrize("kind", ["monthly", "quarterly", "combined"])
def test_numeric_core_pass_never_grants_automatic_execution_or_unproven_calendar(kind):
    value = recipe(kind)
    before = copy.deepcopy(value)
    result = global_gate.evaluate(value, outcomes(value, availability=False))
    assert result["core_ready"] and result["requested_bundle_ready"]
    assert not result["ready_for_calendar_incorporation"]
    assert result["calendar_blockers"]
    assert result["ready_for_automatic_execution"] is False
    assert result["activation"] == "none"
    assert result["publication"] == "not_authorized"
    assert value == before


@pytest.mark.parametrize("product", sorted(MONTHLY_REQUIRED))
def test_every_monthly_required_product_is_required_when_omitted(product):
    value = recipe()
    value["items"] = [item for item in value["items"] if item["product"] != product]
    result = global_gate.evaluate(value, outcomes(value))
    assert not result["core_ready"] and not result["requested_bundle_ready"]
    assert f"monthly:{product}:missing" in result["blockers"]


@pytest.mark.parametrize("product", sorted(QUARTERLY_REQUIRED))
def test_every_quarterly_required_product_is_required_when_omitted(product):
    value = recipe("quarterly")
    value["items"] = [item for item in value["items"] if item["product"] != product]
    result = global_gate.evaluate(value, outcomes(value))
    assert not result["core_ready"] and not result["requested_bundle_ready"]
    assert f"quarterly:{product}:missing" in result["blockers"]


def test_monthly_h10_cannot_satisfy_missing_banxico():
    value = recipe()
    value["items"] = [item for item in value["items"] if item["product"] != "banxico"]
    selected(value, "h10")["used"] = True
    result = global_gate.evaluate(value, outcomes(value))
    assert not result["core_ready"]
    assert "monthly:banxico:missing" in result["blockers"]


@pytest.mark.parametrize("product", ["am_sec", "bmv_xbrl"])
def test_supplementary_financial_source_cannot_satisfy_missing_primary(product):
    value = recipe("quarterly")
    value["items"] = [item for item in value["items"] if item["product"] != "am_financials"]
    selected(value, product)["used"] = True
    result = global_gate.evaluate(value, outcomes(value))
    assert not result["core_ready"]
    assert "quarterly:am_financials:missing" in result["blockers"]


@pytest.mark.parametrize("product", ["aena", "delta_sec", "anac", "airports_reference"])
def test_failed_extra_only_blocks_its_requested_bundle_when_used(product):
    value = recipe("quarterly")
    item = selected(value, product)
    results = outcomes(value)
    results[item["id"]] = {"status": "blocked", "source_conditions": []}
    unused = global_gate.evaluate(value, results)
    assert unused["core_ready"] and unused["requested_bundle_ready"]
    item["used"] = True
    used = global_gate.evaluate(value, results)
    assert used["core_ready"] and not used["requested_bundle_ready"]


def test_aerocivil_numeric_success_with_pending_legend_cannot_pass_required_core():
    value = recipe("quarterly")
    results = outcomes(value)
    results[selected(value, "aerocivil")["id"]]["source_conditions"] = [
        "official_service_code_legend_pending"
    ]
    result = global_gate.evaluate(value, results)
    assert not result["core_ready"] and not result["requested_bundle_ready"]
    assert not result["ready_for_calendar_incorporation"]


@pytest.mark.parametrize("proof", [None, False, 0, "true"])
def test_aerocivil_needs_positive_semantic_proof_not_merely_absence_of_warning(proof):
    value = recipe("quarterly")
    results = outcomes(value)
    result = results[selected(value, "aerocivil")["id"]]
    if proof is None:
        result.pop("semantic_acceptance_verified")
    else:
        result["semantic_acceptance_verified"] = proof
    decision = global_gate.evaluate(value, results)
    assert not decision["core_ready"] and not decision["requested_bundle_ready"]
    assert not decision["ready_for_calendar_incorporation"]


def test_empty_gdelt_is_neither_absence_of_news_nor_a_pass():
    value = recipe()
    selected(value, "gdelt")["used"] = True
    selected(value, "rss")["used"] = True
    results = outcomes(value, editorial=False)
    results[selected(value, "gdelt")["id"]]["status"] = "empty_result_unproven_coverage"
    result = global_gate.evaluate(value, results)
    assert result["data_tasks_ready"]
    assert results[selected(value, "afac_airports")["id"]]["status"] == "checks_passed"
    assert not result["core_ready"] and not result["ready_for_calendar_incorporation"]
    assert result["news_task"]["prepared"] is False
    assert "monthly:editorial_news:not_verified" in result["blockers"]
    tasks = {task["id"]: task for task in result["calendar_tasks"]}
    assert tasks[selected(value, "gdelt")["id"]]["status"] == "empty_result_unproven_coverage"
    assert not tasks[selected(value, "gdelt")["id"]]["prepared_for_review"]
    assert tasks[round_tasks.EDITORIAL_ID]["required"]


@pytest.mark.parametrize("kind", ["monthly", "combined"])
@pytest.mark.parametrize("editorial_state", ["missing", "blocked", "wrong_month"])
def test_editorial_task_is_required_in_same_calendar_without_blocking_independent_data(kind, editorial_state):
    value = recipe(kind)
    results = outcomes(value, editorial=False)
    if editorial_state != "missing":
        results[round_tasks.EDITORIAL_ID] = {
            "status": "blocked" if editorial_state == "blocked" else "checks_passed",
            "period": "2026M08" if editorial_state == "wrong_month" else value["monthly_period"],
        }
    before = copy.deepcopy(results)
    decision = global_gate.evaluate(value, results)
    assert decision["data_tasks_ready"]
    assert not decision["core_ready"] and not decision["requested_bundle_ready"]
    assert not decision["ready_for_calendar_incorporation"]
    assert decision["blockers"] == ["monthly:editorial_news:not_verified"]
    assert decision["news_task"]["same_calendar"] and not decision["news_task"]["prepared"]
    assert results == before
    tasks = {item["id"]: item for item in decision["calendar_tasks"]}
    assert tasks[round_tasks.EDITORIAL_ID]["required"]
    assert not tasks[round_tasks.EDITORIAL_ID]["prepared_for_review"]
    assert tasks[selected(value, "afac_airports")["id"]]["prepared_for_review"]


@pytest.mark.parametrize("provider", ["gdelt", "rss"])
@pytest.mark.parametrize("status", ["blocked", "empty_result_unproven_coverage"])
def test_optional_news_provider_failure_does_not_cancel_verified_calendar_tasks(provider, status):
    value = recipe()
    item = selected(value, provider)
    item["used"] = True
    results = outcomes(value)
    results[item["id"]]["status"] = status
    decision = global_gate.evaluate(value, results)
    assert decision["data_tasks_ready"] and decision["core_ready"]
    assert decision["requested_bundle_ready"] and decision["ready_for_calendar_incorporation"]
    assert decision["news_task"]["prepared"]
    tasks = {task["id"]: task for task in decision["calendar_tasks"]}
    assert tasks[item["id"]]["status"] == status
    assert not tasks[item["id"]]["required"] and not tasks[item["id"]]["prepared_for_review"]
    assert tasks[round_tasks.EDITORIAL_ID]["prepared_for_review"]
    assert decision["activation"] == "none" and decision["publication"] == "not_authorized"


def test_combined_calendar_has_twenty_one_data_obligations_and_one_editorial_obligation():
    value = recipe("combined")
    decision = global_gate.evaluate(value, outcomes(value))
    required = [task for task in decision["calendar_tasks"] if task["required"]]
    assert len(required) == 22
    assert sum(task["kind"] == "source_update" for task in required) == 21
    assert sum(task["id"] == round_tasks.EDITORIAL_ID for task in required) == 1
    assert {task["product"] for task in required} >= {"aerocivil", "viva_financials"}


def test_editorial_task_is_not_due_in_quarterly_only_calendar():
    value = recipe("quarterly")
    decision = global_gate.evaluate(value, outcomes(value))
    editorial = next(task for task in decision["calendar_tasks"] if task["id"] == round_tasks.EDITORIAL_ID)
    assert editorial["status"] == "not_due_this_round"
    assert not editorial["required"] and not editorial["prepared_for_review"]
    assert decision["core_ready"]
    assert "monthly:editorial_news:not_verified" not in decision["blockers"]


def test_combined_keeps_both_period_tasks_for_shared_required_source():
    value = recipe("combined")
    results = outcomes(value)
    results[selected(value, "volaris_sec", "quarterly")["id"]]["status"] = "blocked"
    result = global_gate.evaluate(value, results)
    assert not result["core_ready"] and not result["requested_bundle_ready"]


@pytest.mark.parametrize(
    "mutation", ["caller_required", "caller_outcomes", "wrong_month", "wrong_quarter", "never"]
)
def test_invalid_recipe_cannot_change_acceptance_scope(mutation):
    value = recipe("combined")
    if mutation == "caller_required":
        value["items"][0]["required"] = False
    elif mutation == "caller_outcomes":
        value["outcomes"] = outcomes(value)
    elif mutation == "wrong_month":
        selected(value, "gdelt")["period"] = "2026M08"
    elif mutation == "wrong_quarter":
        selected(value, "aerocivil")["period"] = "2026Q2"
    else:
        value["items"].append(task("news_errors", "monthly"))
    with pytest.raises(ValueError):
        global_gate.evaluate(value, outcomes(value))


@pytest.mark.parametrize("mutation", ["missing", "unused", "cycle"])
def test_dependency_graph_cannot_hide_a_needed_input(mutation):
    value = recipe()
    first, second = selected(value, "am_sec"), selected(value, "h10")
    first["used"] = True
    first["depends_on"] = [second["id"]]
    if mutation == "missing":
        value["items"].remove(second)
    elif mutation == "cycle":
        second["used"] = True
        second["depends_on"] = [first["id"]]
    with pytest.raises(ValueError):
        global_gate.evaluate(value, outcomes(value))


def test_used_reference_outside_monthly_cadence_is_not_ignored():
    value = recipe()
    reference = task("airports_reference", "quarterly")
    value["items"].append(reference)
    selected(value, "afac_airports")["depends_on"] = [reference["id"]]
    results = outcomes(value)
    results[reference["id"]]["status"] = "blocked"
    result = global_gate.evaluate(value, results)
    assert not result["core_ready"]
    assert not result["requested_bundle_ready"]
    assert not result["ready_for_calendar_incorporation"]


def test_failed_transitive_dependency_blocks_the_required_result():
    value = recipe()
    reference = task("airports_reference", "quarterly")
    parent = task("anac", "quarterly")
    reference["depends_on"] = [parent["id"]]
    selected(value, "afac_airports")["depends_on"] = [reference["id"]]
    value["items"].extend([reference, parent])
    results = outcomes(value)
    results[parent["id"]]["status"] = "blocked"
    result = global_gate.evaluate(value, results)
    assert not result["core_ready"] and not result["requested_bundle_ready"]


def test_required_product_cannot_be_demoted_by_unused_flag():
    value = recipe()
    selected(value, "afac_airports")["used"] = False
    result = global_gate.evaluate(value, outcomes(value))
    assert not result["core_ready"] and not result["requested_bundle_ready"]


def test_catalogue_cadence_drift_requires_deliberate_policy_review(monkeypatch):
    changed = copy.deepcopy(product_map())
    changed["am_financials"]["cadence"] = "monthly"
    monkeypatch.setattr(global_gate, "product_map", lambda: changed)
    with pytest.raises(ValueError):
        global_gate.policy()


def test_immutable_verifier_inventory_covers_external_gdelt_contract():
    assert "contracts/source_updates/gdelt-observed-metadata.schema.json" in global_gate.fingerprints()


@pytest.mark.parametrize("product", ["afac_carriers", "afac_airports", "bts_segments"])
def test_explicit_native_lag_does_not_change_target_or_verify_availability(product):
    value = recipe()
    item = selected(value, product)
    item["source_period"] = "2026M07"
    result = global_gate.evaluate(value, outcomes(value, availability=False))
    assert result["core_ready"]
    assert not result["ready_for_calendar_incorporation"]
    assert item["period"] == "2026M09" and item["source_period"] == "2026M07"


@pytest.mark.parametrize(
    "product,source_period",
    [("am_traffic_ir", "2026M08"), ("bts_segments", "2026M10"), ("viva_traffic", "2026Q3")],
)
def test_native_period_cannot_reduce_corporate_target_or_include_future_data(product, source_period):
    value = recipe()
    selected(value, product)["source_period"] = source_period
    with pytest.raises(ValueError):
        global_gate.evaluate(value, outcomes(value))


@pytest.mark.parametrize("source_period", ["2026M06", "2026M10", "2025M07"])
def test_aerocivil_native_month_must_belong_to_declared_quarter(source_period):
    value = recipe("quarterly")
    selected(value, "aerocivil")["source_period"] = source_period
    with pytest.raises(ValueError):
        global_gate.evaluate(value, outcomes(value))


def physically_bound_reports(value):
    """Invented in-memory identities test binding, never official release evidence."""
    results = outcomes(value)
    financials = {
        "AEROMEXICO": ("am_financials", "https://ir.aeromexico.com/synthetic-contract.pdf"),
        "VOLARIS": ("volaris_sec", "https://ir.volaris.com/synthetic-contract.pdf"),
        "VIVA_AEROBUS": ("viva_financials", "https://cdn.investorcloud.net/synthetic-contract.pdf"),
    }
    for entity, (product, url) in financials.items():
        item = selected(value, product, "quarterly")
        artifact = {"source_url": url, "sha256": "a" * 64}
        results[item["id"]]["contributing_artifacts"] = [artifact]
        if entity == "VOLARIS":
            results[item["id"]]["financial_report_artifacts"] = [artifact]
        value["releases"].append(
            {
                "entity": entity,
                "period": value["quarterly_period"],
                "kind": "financial_report",
                "confirmed": True,
                "published_at": "2026-10-19T12:00:00-06:00",
                "document_url": url,
                "source_sha256": artifact["sha256"],
                "task_id": item["id"],
            }
        )
    return results


def test_synthetic_complete_calendar_proof_still_cannot_activate_execution():
    value = recipe("combined")
    results = physically_bound_reports(value)
    results[selected(value, "gdelt")["id"]]["source_conditions"] = ["source_does_not_certify_complete_month"]
    decision = global_gate.evaluate(value, results)
    assert decision["core_ready"] and decision["requested_bundle_ready"]
    assert decision["monthly_date"] == "2026-10-15"
    assert decision["quarterly_date"] == "2026-10-21"
    assert decision["ready_for_calendar_incorporation"]
    assert decision["ready_for_automatic_execution"] is False
    assert decision["activation"] == "none" and decision["publication"] == "not_authorized"


@pytest.mark.parametrize("kind", ["monthly", "quarterly", "combined"])
def test_calendar_prerequisites_follow_requested_cadence_without_dropping_required_sources(kind):
    """Policy-only success fixtures do not establish availability of any source."""
    value = recipe(kind)
    results = outcomes(value) if kind == "monthly" else physically_bound_reports(value)
    decision = global_gate.evaluate(value, results)
    assert decision["core_ready"] and decision["requested_bundle_ready"]
    assert decision["ready_for_calendar_incorporation"] and not decision["calendar_blockers"]
    assert decision["ready_for_automatic_execution"] is False
    assert decision["activation"] == "none" and decision["publication"] == "not_authorized"


@pytest.mark.parametrize(
    "kind,product,cadence",
    [
        ("monthly", round_tasks.EDITORIAL_ID, "monthly"),
        ("combined", round_tasks.EDITORIAL_ID, "monthly"),
        ("quarterly", "aerocivil", "quarterly"),
        ("combined", "aerocivil", "quarterly"),
    ],
)
def test_calendar_prerequisites_still_block_their_requested_cadence(kind, product, cadence):
    value = recipe(kind)
    results = outcomes(value) if kind == "monthly" else physically_bound_reports(value)
    item_id = (
        round_tasks.EDITORIAL_ID
        if product == round_tasks.EDITORIAL_ID
        else selected(value, product, cadence)["id"]
    )
    results[item_id]["status"] = "blocked"
    decision = global_gate.evaluate(value, results)
    assert not decision["core_ready"] and not decision["ready_for_calendar_incorporation"]
    if product == round_tasks.EDITORIAL_ID:
        assert decision["data_tasks_ready"]
        assert results[selected(value, "afac_airports")["id"]]["status"] == "checks_passed"
        assert "monthly:editorial_news:not_verified" in decision["blockers"]
        assert not decision["news_task"]["prepared"]
    else:
        assert (
            f"{cadence}:{product}:required_calendar_prerequisite_not_verified"
            in decision["calendar_blockers"]
        )


@pytest.mark.parametrize("dependent", [False, True])
def test_used_outside_cadence_result_and_transitive_dependency_are_still_checked(dependent):
    value = recipe("monthly")
    outside = task("aerocivil", "quarterly")
    value["items"].append(outside)
    required = selected(value, "afac_airports", "monthly")
    if dependent:
        required["depends_on"] = [outside["id"]]
    results = outcomes(value)
    results[outside["id"]]["semantic_acceptance_verified"] = False
    decision = global_gate.evaluate(value, results)
    assert not decision["requested_bundle_ready"] and not decision["ready_for_calendar_incorporation"]
    assert decision["core_ready"] is not dependent
    assert "quarterly:aerocivil:official_service_code_legend_pending" in decision["blockers"]
    if dependent:
        assert "monthly:afac_airports:dependency_not_verified" in decision["blockers"]


@pytest.mark.parametrize("mutation", ["url", "sha256", "not_contributing", "missing_report"])
def test_release_requires_actual_verified_contributor_not_just_a_valid_url(mutation):
    value = recipe("combined")
    results = physically_bound_reports(value)
    release = value["releases"][0]
    if mutation == "url":
        release["document_url"] += "?other-document=1"
    elif mutation == "sha256":
        release["source_sha256"] = "b" * 64
    elif mutation == "not_contributing":
        results[release["task_id"]]["contributing_artifacts"] = []
    else:
        value["releases"].pop()
    decision = global_gate.evaluate(value, results)
    assert decision["core_ready"]
    assert not decision["ready_for_calendar_incorporation"]
    assert decision["calendar_blockers"]


@pytest.mark.parametrize("mutation", ["announcement", "quarter", "entity", "future", "unconfirmed"])
def test_invalid_release_identity_or_timing_is_rejected_before_acceptance(mutation):
    value = recipe("combined")
    results = physically_bound_reports(value)
    release = value["releases"][0]
    if mutation == "announcement":
        release["kind"] = "conference_call"
    elif mutation == "quarter":
        release["period"] = "2026Q2"
    elif mutation == "entity":
        release["task_id"] = selected(value, "volaris_sec", "quarterly")["id"]
    elif mutation == "future":
        release["published_at"] = "2026-10-22T12:00:00-06:00"
    else:
        release["confirmed"] = False
    with pytest.raises(ValueError):
        global_gate.evaluate(value, results)


def test_combined_round_cannot_silently_combine_dates_more_than_seven_days_apart():
    value = recipe("combined")
    value["as_of"] = "2026-11-19T12:00:00-06:00"
    value["monthly_period"] = "2026M10"
    for item in value["items"]:
        item["candidate_as_of"] = value["as_of"]
        item["period"] = value[f"{item['cadence']}_period"]
    decision = global_gate.evaluate(value, physically_bound_reports(value))
    assert decision["core_ready"] and decision["requested_bundle_ready"]
    assert decision["monthly_date"] == "2026-11-17"
    assert decision["quarterly_date"] == "2026-10-21"
    assert not decision["ready_for_calendar_incorporation"]
    assert "combined_rounds_more_than_seven_calendar_days_apart" in decision["calendar_blockers"]


def test_unverified_holiday_year_blocks_calendar_without_inventing_dates():
    value = recipe("combined")
    value["as_of"] = "2027-01-21T12:00:00-06:00"
    value["monthly_period"] = "2026M12"
    for item in value["items"]:
        item["candidate_as_of"] = value["as_of"]
        item["period"] = value[f"{item['cadence']}_period"]
    decision = global_gate.evaluate(value, physically_bound_reports(value))
    assert decision["core_ready"]
    assert not decision["ready_for_calendar_incorporation"]
    assert decision["monthly_date"] is None
    assert any("2027" in reason for reason in decision["calendar_blockers"])
