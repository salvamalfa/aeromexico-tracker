"""Source handoff contracts; fixtures never represent a native dispatch or source check."""

import copy
import json
import socket
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from scripts import source_update_coordinator as coordinator
from scripts import source_update_dispatch as dispatch
from src.source_updates.catalog import ROOT, product_map

AS_OF = "2026-10-29T12:00:00Z"
DUE = "2026-11-17T08:00:00-06:00"


def reports(day="2026-10-26", entities=("AEROMEXICO", "VOLARIS")):
    return [
        {
            "entity": entity,
            "kind": "financial_report",
            "period": "2026Q3",
            "confirmed": True,
            "publication_precision": "day",
            "published_on": day,
            "published_at": None,
            "document_url": "https://example.test/reviewed-report",
        }
        for entity in entities
    ]


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Handoff preparation cannot make source or native tool requests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    state = coordinator.prepare(
        {"as_of": AS_OF, "start": "2026-11", "months": 2, "quarter": "2026Q3", "releases": reports()}
    )
    state["workspace"] = str(tmp_path / "canonical")
    workers = ROOT / "tmp/source-updates" / ("dispatch-test-" + uuid4().hex)
    return state, workers


def event(state, at=AS_OF):
    return coordinator.trigger(state, at)["event_id"]


def build(prepared, **kwargs):
    state, workers = prepared
    at = kwargs.pop("as_of", AS_OF)
    return dispatch.manifest(state, event(state, at), at, worker_root=workers, **kwargs)


def test_map_covers_every_product_and_eight_real_skills_without_source_requests():
    result = dispatch.source_map()
    assert result["catalogue_sources"] == 30
    assert set(result["families"]) == set(dispatch.SKILLS)
    products = {row["product"]: row for row in result["products"]}
    assert set(products) == {*product_map(), "editorial_news"}
    assert len(products) == 44
    assert products["gap_traffic"]["family"] == products["asur_traffic"]["family"] == "airports"
    assert products["am_financials"]["family"] == "corporate"
    assert products["aerocivil"]["family"] == "routes"
    assert products["editorial_news"]["skill"]["path"] == ".agents/skills/airline-update-news/SKILL.md"
    assert products["news_errors"]["handoff_eligible"] is False
    assert products["banxico"]["provider_publication_frequency"] == "Diaria."
    assert products["banxico"]["cadence"] == "both"
    assert all(row["official_publication_date"] is None for row in products.values())
    assert result["network_requests"] == 0 and result["writes"] == []


def test_source_map_resolves_all_configured_product_entries_without_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Source mapping must not acquire or verify remote sources")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    products = {row["product"]: row for row in dispatch.source_map()["products"]}
    recipes = dispatch.acquisition_config()["products"]
    catalogue = dispatch.load_catalog()
    for product, recipe in recipes.items():
        row = products[product]
        assert row["source_catalogue_discovery_page"] == catalogue[row["source_key"]]["official_page_url"]
        assert row["acquisition_entry_url"] == dispatch.resolve_entry(recipe["entry_ref"])
        assert row["discovery_page"] == dispatch.resolve_entry(
            recipe.get("discovery_ref", recipe["entry_ref"])
        )
    assert products["bts_segments"]["discovery_page"] != products["bts_segments"]["acquisition_entry_url"]
    for product in ("peer_profiles", "curated_context", "derived", "editorial_news"):
        assert products[product]["acquisition_entry_url"] is None
        assert products[product]["discovery_page"] is None


def test_aerocivil_product_points_to_colombian_primary_entry_not_generic_caa_catalogue():
    from src.ingest.international_routes import CO_URL

    products = {row["product"]: row for row in dispatch.source_map()["products"]}
    aerocivil = products["aerocivil"]
    assert aerocivil["entry_reference"] == "constant:src.ingest.international_routes:CO_URL"
    assert aerocivil["acquisition_entry_url"] == CO_URL == "https://www.datos.gov.co/resource/jh8x-n6h6.json"
    assert aerocivil["discovery_page"] == CO_URL
    assert aerocivil["source_catalogue_discovery_page"] == "https://www.caa.co.uk/data-and-analysis/"
    assert products["caa"]["discovery_page"].startswith("https://www.caa.co.uk/")
    assert products["anac"]["acquisition_entry_url"].startswith("https://sistemas.anac.gov.br/")
    assert products["aena"]["acquisition_entry_url"].startswith("https://www.aena.es/")


def test_manifest_is_byte_stable_read_only_and_has_fifteen_native_handoffs(prepared):
    state, workers = prepared
    before = copy.deepcopy(state)
    first = build(prepared)
    second = build(prepared)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert state == before and not workers.exists()
    assert first["mode"] == "rehearsal_plan_only" and len(first["jobs"]) == 15
    assert first["native_calls_performed"] == first["network_requests"] == first["scheduled_executions"] == 0
    assert first["native_capability_verified"] is False and first["writes"] == []
    assert all(job["owner_native_id"] is None for job in first["jobs"])
    assert len({job["logical_agent_name"] for job in first["jobs"]}) == len(first["jobs"])
    assert len({job["workspace"] for job in first["jobs"]}) == len(first["jobs"])
    assert all(Path(job["workspace"]).is_relative_to(workers) for job in first["jobs"])
    assert all(job["native_call"]["tool"] == "collaboration.spawn_agent" for job in first["jobs"])
    news = next(job for job in first["jobs"] if job["product"] == "editorial_news")
    assert news["native_call"]["arguments"]["task_name"] == news["logical_agent_name"]
    assert news["period"] == "2026M10" and news["period_closed_at_cutoff"] is False
    assert news["preflight_commands"][-1] == [
        sys.executable,
        "-m",
        "src.source_updates.editorial_news",
        "--help",
    ]
    assert not {"rss", "gdelt"} & {job["product"] for job in first["jobs"]}
    assert "data_verified=false" in news["native_call"]["arguments"]["message"]


def test_envelopes_name_actual_skill_layers_browser_handoff_and_scope(prepared):
    result = build(prepared)
    for job in result["jobs"]:
        message = job["native_call"]["arguments"]["message"]
        assert Path(job["skill"]["absolute_path"]).is_file()
        assert job["skill"]["sha256"] in message
        assert job["task_key"] in message and job["period"] in message and AS_OF in message
        assert all(
            name in job["destinations"] for name in ("bronze", "silver", "gold", "evidence", "receipts")
        )
        assert "Library" in message and "navegador nativo" in message
        assert "No actives datos, noticias, evidencias o tesis" in message
        assert "no es un programa" in message
        assert "readiness/global" in message
        assert "argv[0]" in message and "Conserva cualquier fallo previo" in message
        for command in job["preflight_commands"]:
            assert Path(command[0]).is_absolute()
            assert command[0] == sys.executable


def test_wrong_event_or_changed_member_cannot_be_handed_off(prepared):
    state, workers = prepared
    with pytest.raises(ValueError, match="exact date and members"):
        dispatch.manifest(state, "0" * 64, AS_OF, worker_root=workers)
    orphan = dict(state["tasks"]["monthly:2026M10:am_traffic_ir"], product="unknown_product")
    state["tasks"]["monthly:2026M10:unknown_product"] = orphan
    with pytest.raises(ValueError, match="event membership differ"):
        build(prepared)
    assert not workers.exists()


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.update(version=True),
        lambda s: s.update(publication_authorized=True),
        lambda s: s.update(timezone="UTC"),
        lambda s: s.update(active_task="monthly:2026M10:am_traffic_ir"),
        lambda s: s["tasks"]["monthly:2026M10:am_traffic_ir"].update(selected="true"),
        lambda s: s["tasks"]["monthly:2026M10:am_traffic_ir"].update(reschedules=True),
        lambda s: s["tasks"]["monthly:2026M10:am_traffic_ir"].update(period="2026M11"),
        lambda s: s["tasks"]["monthly:2026M10:am_traffic_ir"].update(dispatches=[{"delivery": "uncertain"}]),
    ],
)
def test_corrupt_or_uncertain_state_fails_closed_without_writes(prepared, change):
    state, workers = prepared
    change(state)
    with pytest.raises((ValueError, KeyError)):
        build(prepared)
    assert not workers.exists()


def test_missing_skill_and_escaping_worker_root_block(prepared, monkeypatch):
    with pytest.raises(ValueError, match="child of this checkout"):
        dispatch.manifest(prepared[0], event(prepared[0]), AS_OF, worker_root=Path("/tmp/outside"))
    monkeypatch.setitem(dispatch.SKILLS, "news", "missing-skill")
    with pytest.raises(ValueError, match="skill is missing"):
        build(prepared)


def test_execution_envelope_needs_authorized_bound_calendar_exact_day_and_canonical_state(prepared, tmp_path):
    state, _ = prepared
    with pytest.raises(ValueError, match="authorized, bound"):
        build(prepared, execution_handoff=True, as_of=DUE)
    state.update(
        activation_authorized=True, automation_id="synthetic-id", automation_creation={"outcome": "uncertain"}
    )
    with pytest.raises(ValueError, match="uncertain automation"):
        build(prepared, execution_handoff=True, as_of=DUE)
    state["automation_creation"]["outcome"] = "bound"
    with pytest.raises(ValueError, match="requires the event date"):
        build(prepared, execution_handoff=True)
    with pytest.raises(ValueError, match="canonical state"):
        build(prepared, execution_handoff=True, as_of=DUE, state_file=tmp_path / "copy.json")
    canonical = Path(state["workspace"]) / "state.json"
    canonical.parent.mkdir()
    canonical.write_text(json.dumps(state))
    result = build(prepared, execution_handoff=True, as_of=DUE, state_file=canonical)
    assert result["mode"] == "execution_handoff"
    assert result["native_calls_performed"] == 0
    assert all(Path(job["workspace"]).name == "candidate" for job in result["jobs"])
    rehearsal = build(prepared)
    assert all(Path(job["workspace"]).name == "rehearsal" for job in rehearsal["jobs"])
    assert not {job["workspace"] for job in result["jobs"]} & {job["workspace"] for job in rehearsal["jobs"]}


def test_confirmed_release_day_is_separate_from_quarter_execution_and_announcement_is_ignored(prepared):
    state, _ = prepared
    latest = reports("2026-11-13", ("VIVA_AEROBUS",))
    stamp = "2026-11-14T12:00:00Z"
    coordinator.transition(
        state,
        {"action": "refresh_reports", "operation_id": "synthetic-report", "at": stamp, "releases": latest},
        Path(state["workspace"]),
    )
    result = build(prepared, as_of=stamp)
    jobs = {job["product"]: job for job in result["jobs"] if job["cadence"] == "quarterly"}
    assert jobs["viva_financials"]["official_publication_date"] == "2026-11-13"
    assert jobs["viva_financials"]["consolidated_execution_date"] == "2026-11-18"
    assert jobs["am_financials"]["official_publication_date"] == "2026-10-26"
    assert jobs["viva_financials"]["confirmed_publications"][0]["published_at"] is None
    state["releases"].append({**latest[0], "kind": "earnings_call", "published_on": "2026-11-14"})
    again = build(prepared, as_of=stamp)
    assert (
        next(job for job in again["jobs"] if job["product"] == "viva_financials")["official_publication_date"]
        == "2026-11-13"
    )


def test_unscheduled_rehearsal_has_eight_families_and_closed_periods_without_fictitious_event():
    products = [
        "am_traffic_ir",
        "afac_carriers",
        "oma_traffic",
        "banxico",
        "aerocivil",
        "airports_reference",
        "editorial_news",
        "peer_profiles",
    ]
    result = dispatch.rehearsal_manifest(AS_OF, products)
    assert result["is_scheduled_event"] is False and result["event_id"] is None
    assert result["event_date"] is None and result["mode"] == "unscheduled_skill_rehearsal"
    assert {job["family"] for job in result["jobs"]} == set(dispatch.SKILLS)
    assert {job["period"] for job in result["jobs"]} == {"2026M09", "2026Q3"}
    assert all(job["period_closed_at_cutoff"] for job in result["jobs"])
    for job in result["jobs"]:
        assert job["owner_native_id"] is None and job["event_id"] is None
        assert job["consolidated_execution_date"] is None and job["official_publication_date"] is None
        assert job["lease_fields"] == {
            "execution_mode": "isolated_skill_worker",
            "worker_workspace": job["workspace"],
        }
        assert "Ensayo explícito no programado" in job["native_call"]["arguments"]["message"]
    assert (
        result["native_calls_performed"] == result["network_requests"] == result["scheduled_executions"] == 0
    )


@pytest.mark.parametrize("products", [[], ["missing"], ["banxico", "banxico"], ["news_errors"], "banxico"])
def test_rehearsal_requires_explicit_unique_executable_products(products):
    with pytest.raises(ValueError):
        dispatch.rehearsal_manifest(AS_OF, products)


def test_isolated_workers_allow_only_the_same_coordinator_to_prepare_remaining_handoffs(prepared):
    state, _ = prepared
    key = "monthly:2026M10:am_traffic_ir"
    state["active_task"] = key
    state["active_tasks"] = {key: "synthetic-already-persisted-intent"}
    state["tasks"][key].update(
        status="running",
        dispatches=[
            {
                "execution_mode": "isolated_skill_worker",
                "owner_turn_id": "actual-coordinator-owner",
                "delivery": "uncertain",
            }
        ],
    )
    with pytest.raises(ValueError, match="active writer"):
        build(prepared, coordinator_owner_turn_id="other-owner")
    result = build(prepared, coordinator_owner_turn_id="actual-coordinator-owner")
    assert len(result["jobs"]) == 14 and key not in {job["task_key"] for job in result["jobs"]}
    state["tasks"][key]["dispatches"][-1]["execution_mode"] = "serial_writer"
    with pytest.raises(ValueError, match="active writer"):
        build(prepared, coordinator_owner_turn_id="actual-coordinator-owner")


def test_isolated_workers_accept_same_local_owner_lease_without_native_turn_id(prepared):
    state, _ = prepared
    key = "monthly:2026M10:am_traffic_ir"
    state["active_task"] = key
    state["active_tasks"] = {key: "synthetic-already-persisted-intent"}
    state["tasks"][key].update(
        status="running",
        dispatches=[
            {
                "execution_mode": "isolated_skill_worker",
                "owner_turn_id": None,
                "native_owner_turn_id": None,
                "owner_lease_id": "local_lease:coordinator-test",
                "delivery": "uncertain",
            }
        ],
    )
    before = copy.deepcopy(state)
    result = build(prepared, coordinator_owner_lease_id="local_lease:coordinator-test")
    assert len(result["jobs"]) == 14 and key not in {job["task_key"] for job in result["jobs"]}
    assert state == before
    with pytest.raises(ValueError, match="active writer"):
        build(prepared, coordinator_owner_lease_id="local_lease:other-coordinator")
    with pytest.raises(ValueError, match="active writer"):
        build(prepared, coordinator_owner_turn_id="local_lease:wrong-owner")


@pytest.mark.parametrize("lease", ["unlabelled", "local_lease:", "local_lease: ", 42])
def test_local_owner_lease_requires_explicit_prefix_and_token(prepared, lease):
    with pytest.raises(ValueError, match="local_lease"):
        build(prepared, coordinator_owner_lease_id=lease)
