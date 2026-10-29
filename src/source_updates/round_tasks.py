"""One calendar, independent task results; editorial search replaces a mandatory provider."""

import re
from pathlib import Path

from src.source_updates.aerocivil_operational import accepted as aerocivil_accepted
from src.source_updates.calendar import local_time
from src.source_updates.collection import safe_workspace
from src.source_updates.editorial_news import run, sha

NEWS_PROVIDERS = frozenset({"rss", "gdelt"})
EDITORIAL_ID = "editorial_news"


def binding_preflight(recipe, workspace=None):
    if isinstance(recipe.get("items"), list) and any(
        isinstance(i, dict) and i.get("id") == EDITORIAL_ID for i in recipe["items"]
    ):
        raise ValueError("editorial_news is a reserved common-calendar workflow ID")
    binding = recipe.get("editorial_news")
    if binding is None:
        return
    if (
        not isinstance(binding, dict)
        or set(binding) != {"workspace", "receipt_sha256"}
        or not re.fullmatch(r"[a-f0-9]{64}", str(binding["receipt_sha256"]))
    ):
        raise ValueError("Editorial task needs an exact physical candidate-receipt binding")
    root = safe_workspace(Path(binding["workspace"]))
    others = [Path(i["workspace"]) for i in recipe["items"] if i["used"]]
    if workspace is not None:
        others.append(Path(workspace))
    for candidate in others:
        other = safe_workspace(candidate)
        if root == other or root.is_relative_to(other) or other.is_relative_to(root):
            raise ValueError("Editorial receipt, source candidates and common-round receipt must be disjoint")


def editorial_result(recipe):
    required = recipe["round"] in {"monthly", "combined"} or recipe.get("editorial_news") is not None
    base = dict(
        id=EDITORIAL_ID,
        product=EDITORIAL_ID,
        cadence="monthly",
        period=recipe["monthly_period"],
        required=required,
        activation="none",
        publication="not_authorized",
    )
    binding = recipe.get("editorial_news")
    if not binding:
        return dict(
            base,
            status="pending_native_editorial_review" if required else "not_due_this_round",
            ready_for_editorial_review=False,
        )
    try:
        root = safe_workspace(Path(binding["workspace"]))
        receipt = root / "receipt.json"
        if sha(receipt.read_bytes()) != binding["receipt_sha256"]:
            raise ValueError("Editorial receipt hash differs from the selected review")
        result = run(root, check=True)
        if result["receipt_sha256"] != binding["receipt_sha256"]:
            raise ValueError("Selected editorial receipt changed during its verification")
        import json

        payload = json.loads((root / "review-input.json").read_text())
        if result["period"] != recipe["monthly_period"] or local_time(payload["as_of"]) > local_time(
            recipe["as_of"]
        ):
            raise ValueError("Editorial task month or actual review cutoff differs from the common round")
        return {**result, **base, "status": "checks_passed"}
    except (ValueError, KeyError, OSError, TypeError) as exc:
        return dict(base, status="blocked", reason=str(exc), ready_for_editorial_review=False)


def calendar_guards(guards, cadences, indexed, outcomes):
    failures = []
    for key in sorted(key for key in guards if key[0] in cadences):
        item = indexed.get(key)
        result = outcomes.get(item["id"], {}) if item else {}
        if (
            not item
            or not item["used"]
            or result.get("status") != "checks_passed"
            or (key[1] == "aerocivil" and (not aerocivil_accepted(result)))
        ):
            failures.append(f"{key[0]}:{key[1]}:required_calendar_prerequisite_not_verified")
    return failures


def editorial_decision(recipe, outcomes):
    required = recipe["round"] in {"monthly", "combined"} or recipe.get("editorial_news") is not None
    result = outcomes.get(EDITORIAL_ID, {})
    passed = result.get("status") == "checks_passed" and result.get("period") == recipe["monthly_period"]
    return dict(
        required=required,
        prepared=passed,
        status=result.get("status", "pending_native_editorial_review" if required else "not_due_this_round"),
        blocker="monthly:editorial_news:not_verified" if required and not passed else None,
        same_calendar=True,
        publication_authorized=False,
    )


def calendar_tasks(recipe, outcomes, required):
    tasks = [
        dict(
            id=i["id"],
            product=i["product"],
            cadence=i["cadence"],
            period=i["period"],
            required=(i["cadence"], i["product"]) in required,
            status=outcomes.get(i["id"], {}).get("status", "not_verified"),
            prepared_for_review=outcomes.get(i["id"], {}).get("status") == "checks_passed",
            kind="optional_discovery" if i["product"] in NEWS_PROVIDERS else "source_update",
            **(
                {
                    "operational_acceptance": outcomes[i["id"]]["operational_acceptance"],
                    "official_confirmation": False,
                }
                if i["product"] == "aerocivil"
                and aerocivil_accepted(outcomes.get(i["id"], {}))
                and outcomes[i["id"]].get("operational_acceptance")
                else {}
            ),
        )
        for i in recipe["items"]
        if i["used"]
    ]
    news = editorial_decision(recipe, outcomes)
    for cadence, product in sorted(required):
        if not any(i["cadence"] == cadence and i["product"] == product for i in tasks):
            tasks.append(
                dict(
                    id=f"pending_{cadence}_{product}",
                    product=product,
                    cadence=cadence,
                    period=recipe[cadence + "_period"],
                    required=True,
                    status="missing",
                    prepared_for_review=False,
                    kind="source_update",
                )
            )
    tasks.append(
        dict(
            id=EDITORIAL_ID,
            product=EDITORIAL_ID,
            cadence="monthly",
            period=recipe["monthly_period"],
            required=news["required"],
            status=news["status"],
            prepared_for_review=news["prepared"],
            kind="editorial_source_update",
        )
    )
    return tasks
