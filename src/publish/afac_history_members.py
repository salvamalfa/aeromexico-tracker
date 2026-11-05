"""Two reviewed native correction members, with disjoint field ownership.

There is deliberately no adapter path, arbitrary target list or free JSON patch
in a request. A new source kind requires a new reviewed registration and guard.
"""

from __future__ import annotations

import copy
import importlib
import json
import math
from datetime import datetime
from pathlib import Path

from .afac_history_contract import (
    PERIOD,
    PRODUCT,
    TARGETS,
    encoded,
    hex_digest,
    output_boundary,
    relative_name,
    require_keys,
    sha,
)
from .afac_history_parent import file_ref, identity, physical
from .editorial import _git

COMPARISONS = "bts_unchanged_source_comparisons"
ORDER = (COMPARISONS, PRODUCT)
CANONICAL_GOLD = (
    "fact_carrier_metrics",
    "dim_carrier",
    "dim_period",
    "dim_source_artifact",
    "bridge_record_lineage",
)
BTS_TARGETS = {
    "data/v1/flights/international/2026M07.json",
    "data/v1/flights/entities/INDUSTRY/international/2026M07.json",
}
ADAPTERS = {
    PRODUCT: ("src.publish.afac_history_projection", PERIOD),
    COMPARISONS: ("src.publish.bts_comparison_projection", "2026M07"),
}


def adapter(product):
    if product not in ADAPTERS:
        raise ValueError("Unregistered native correction source kind")
    module_name, period = ADAPTERS[product]
    module = importlib.import_module(module_name)
    if module.PRODUCT != product or module.PERIOD != period:
        raise ValueError("Native adapter identity differs from its reviewed registration")
    for name in module.TARGETS:
        relative_name(name)
    if not module.TARGETS or len(set(module.TARGETS)) != len(module.TARGETS):
        raise ValueError("Native adapter has no unique closed target inventory")
    if product == PRODUCT and tuple(module.TARGETS) != TARGETS:
        raise ValueError("AFAC correction cannot expand its two target files")
    if product == COMPARISONS and set(module.TARGETS) != BTS_TARGETS:
        raise ValueError("Comparison restoration has exactly two reviewed network files")
    return module


def selections(request):
    sources = request["native_sources"]
    if not isinstance(sources, list) or len(sources) != len(ORDER):
        raise ValueError("Select both native correction source kinds explicitly")
    for item, product in zip(sources, ORDER):
        require_keys(item, {"product", "period", "profile"}, "native selection")
        if (item["product"], item["period"]) != (product, ADAPTERS[product][1]):
            raise ValueError("Native correction members must be exact, unique and ordered")
    return sources


def validate_binding(product, binding, projection):
    if product == PRODUCT:
        require_keys(
            binding,
            {"product", "period", "receipt_id", "candidate_as_of", "output_sha256", "native_dataset"},
            "AFAC binding",
        )
        try:
            dataset = importlib.import_module("src.source_updates.afac_native_dataset")
        except ImportError as error:
            raise ValueError(
                "The normal closed AFAC native dataset adapter is required; no fallback"
            ) from error
        dataset.validate_binding(binding["native_dataset"])
        require_keys(binding["output_sha256"], {"afac_history_native_cells"}, "AFAC native digest")
        hex_digest(binding["receipt_id"])
        if binding["output_sha256"]["afac_history_native_cells"] != sha(encoded(projection)):
            raise ValueError("AFAC source binding differs from its native cell projection")
        at = datetime.fromisoformat(binding["candidate_as_of"].replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("AFAC candidate cutoff needs its actual zone")
    elif product == COMPARISONS:
        require_keys(
            binding,
            {"product", "period", "current", "previous", "historical_baseline", "crosswalk"},
            "BTS binding",
        )
        if binding["historical_baseline"] != "089f48a656e301d2380c8d1a23aab5bb6ada728b":
            raise ValueError("BTS restoration has another independently witnessed prior edition")
        for key in ("current", "previous"):
            require_keys(binding[key], {"path", "sha256", "metadata_sha256"}, "BTS original identity")
            relative_name(binding[key]["path"])
            hex_digest(binding[key]["sha256"])
            hex_digest(binding[key]["metadata_sha256"])
        require_keys(binding["crosswalk"], {"path", "sha256"}, "BTS runtime crosswalk")
        if binding["crosswalk"]["path"] != "config/carrier_crosswalk.csv":
            raise ValueError("BTS runtime crosswalk has another physical identity")
        hex_digest(binding["crosswalk"]["sha256"])
    else:
        raise ValueError("Unregistered native binding kind")
    if (binding["product"], binding["period"]) != (product, ADAPTERS[product][1]):
        raise ValueError("Native binding names another source kind or period")


def bts_boundary(before, outputs):
    for name, raw in outputs.items():
        old, new = json.loads(before[name]), json.loads(raw)
        if old == new:
            continue
        if not isinstance(old.get("routes"), list) or not isinstance(new.get("routes"), list):
            raise ValueError("Comparison restoration changed a non-route payload")
        old_clean, new_clean = copy.deepcopy(old), copy.deepcopy(new)
        if len(old["routes"]) != len(new["routes"]):
            raise ValueError("Comparison restoration added or removed routes")
        for index, (prior, current) in enumerate(zip(old["routes"], new["routes"])):
            if prior.get("market_key") != current.get("market_key"):
                raise ValueError("Comparison restoration reordered route identities")
            previous = prior.get("previous", {}).get("departures")
            restored = current.get("previous", {}).get("departures")
            if previous != restored:
                components = prior.get("flight_components", [])
                if (
                    previous is not None
                    or type(restored) not in (int, float)
                    or not math.isfinite(restored)
                    or restored < 0
                    or not float(restored).is_integer()
                    or not components
                    or any(c.get("source_label") != "Estados Unidos · BTS T-100" for c in components)
                    or any(
                        not c.get("service_class_departures")
                        or set(c["service_class_departures"]) - {"F", "G"}
                        for c in components
                    )
                ):
                    raise ValueError("Only missing comparisons of unchanged BTS cells can be restored")
            for value in (old_clean, new_clean):
                route = value["routes"][index]
                if "previous" in route and "departures" in route["previous"]:
                    del route["previous"]["departures"]
        if old_clean != new_clean:
            raise ValueError("Comparison restoration changed current facts, eligibility or another field")


def compose(before, units):
    if [u["product"] for u in units] != list(ORDER):
        raise ValueError("Unordered or incomplete correction projection members")
    current = dict(before)
    for unit in units:
        require_keys(unit, {"product", "source_binding", "projection"}, "native projection member")
        module = adapter(unit["product"])
        validate_binding(unit["product"], unit["source_binding"], unit["projection"])
        source = {name: current[name] for name in module.TARGETS}
        outputs = module.public_outputs(source, unit["projection"])
        if set(outputs) != set(module.TARGETS) or any(
            type(raw) is not bytes or not raw for raw in outputs.values()
        ):
            raise ValueError("Native member expanded or omitted its reviewed targets")
        if unit["product"] == PRODUCT:
            output_boundary(source, outputs)
        else:
            bts_boundary(source, outputs)
        current.update(outputs)
    return {name: current[name] for name in sorted(target_names(units))}


def target_names(units):
    return {name for unit in units for name in adapter(unit["product"]).TARGETS}


def canonical_gold(repo, units):
    """Gold DATA is an explicit physical source closure, never frozen EVAL."""
    if [unit["product"] for unit in units] != list(ORDER):
        raise ValueError("Canonical Gold requires the exact correction source members")
    expected = units[1]["source_binding"]["native_dataset"]["canonical_gold_sha256"]
    require_keys(expected, set(CANONICAL_GOLD), "canonical AFAC Gold DATA inventory")
    result = {}
    for name in CANONICAL_GOLD:
        hex_digest(expected[name])
        relative = f"data/gold/{name}.parquet"
        observed = identity(physical(repo, relative))
        if (
            observed["sha256"] != expected[name]
            or sha(_git(repo, "show", f"HEAD:{relative}")) != expected[name]
        ):
            raise ValueError("Canonical AFAC Gold DATA must match both its binding and committed HEAD")
        result[relative] = observed
    return result


def replay(repo, request, parent_site, parent_files):
    units, inputs = [], {}
    for selection in selections(request):
        module = adapter(selection["product"])
        profile = file_ref(repo, selection["profile"])
        value = module.replay(json.loads(profile.read_bytes()), parent_site)
        require_keys(value, {"source_binding", "projection", "input_files", "outputs"}, "native replay")
        binding = value["source_binding"]
        validate_binding(selection["product"], binding, value["projection"])
        direct = module.public_outputs(
            {name: parent_files[name] for name in module.TARGETS}, value["projection"]
        )
        if direct != value["outputs"] or not value["input_files"]:
            raise ValueError("Native projection lacks its complete physical source replay")
        for path in [profile, *value["input_files"]]:
            path = Path(path)
            path = physical(
                repo, path.relative_to(repo).as_posix() if path.is_absolute() else path.as_posix()
            )
            inputs[path.relative_to(repo).as_posix()] = identity(path)
        units.append(
            {"product": selection["product"], "source_binding": binding, "projection": value["projection"]}
        )
    inputs.update(canonical_gold(repo, units))
    return units, compose(parent_files, units), inputs
