"""Optional coalescing of already-ready source units; a single source stays valid."""

from __future__ import annotations

import re


def selections(request):
    first = {k: request[k] for k in ("product", "period", "source_profile")}
    extra = request.get("additional_sources", [])
    if not isinstance(extra, list) or len(extra) > 15:
        raise ValueError("Select at most sixteen independently ready source units")
    values = [first, *extra]
    seen = set()
    for unit in values:
        if not isinstance(unit, dict) or set(unit) != {"product", "period", "source_profile"}:
            raise ValueError("Each selected source requires its own product, period and pinned profile")
        key = (unit["product"], unit["period"])
        if key in seen:
            raise ValueError("Do not coalesce the same source/product/period twice")
        seen.add(key)
    return values


def members(spec):
    first = {
        "product": spec["product"],
        "period": spec["period_id"],
        "source_binding": spec["source_binding"],
        "projection": spec["projection"],
    }
    extra = spec.get("additional_sources", [])
    if not isinstance(extra, list) or len(extra) > 15:
        raise ValueError("Invalid additional source projection inventory")
    seen = set()
    for unit in [first, *extra]:
        if not isinstance(unit, dict) or set(unit) != {"product", "period", "source_binding", "projection"}:
            raise ValueError("A projected source member needs its exact independently verified binding")
        key = (unit["product"], unit["period"])
        binding = unit["source_binding"]
        if (
            set(binding) != {"product", "period", "receipt_id", "candidate_as_of", "output_sha256"}
            or not re.fullmatch(r"\d{4}M(?:0[1-9]|1[0-2])", unit["period"])
            or not re.fullmatch("[a-f0-9]{32}", binding["receipt_id"])
            or not isinstance(binding["output_sha256"], dict)
            or not binding["output_sha256"]
            or any(not re.fullmatch("[a-f0-9]{64}", h) for h in binding["output_sha256"].values())
        ):
            raise ValueError("Projected member has an invalid native monthly source binding")
        if key in seen or (unit["source_binding"]["product"], unit["source_binding"]["period"]) != key:
            raise ValueError("Duplicate projected source unit or mismatched native period")
        seen.add(key)
    return [first, *extra]


def contract_names(units, adapter):
    return set().union(*(set(adapter(u["product"]).CONTRACTS) for u in units))


def target_names(units, adapter):
    return set().union(*(set(adapter(u["product"]).TARGETS) for u in units))


def compose(before, units, adapter):
    """Each adapter sees prior members' changes and must preserve unrelated rows."""
    outputs = {}
    for unit in units:
        module = adapter(unit["product"])
        selected = {name: outputs.get(name, before[name]) for name in module.TARGETS}
        current = module.public_outputs(selected, unit["projection"])
        if set(current) != set(module.TARGETS) or any(
            type(raw) is not bytes or not raw for raw in current.values()
        ):
            raise ValueError("Source member projected an undeclared or empty public surface")
        outputs.update(current)
    return outputs
