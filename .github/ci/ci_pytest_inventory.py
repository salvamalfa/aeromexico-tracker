"""Record fresh selection and reports without changing pytest decisions."""

from __future__ import annotations

import json
import os
from pathlib import Path

from _pytest.subtests import SubtestReport

_selected = []
_deselected = []
_reports = []
_subtests = []


def pytest_deselected(items):
    _deselected.extend(item.nodeid for item in items)


def pytest_collection_finish(session):
    _selected.extend(item.nodeid for item in session.items)


def pytest_runtest_logreport(report):
    entry = {
        "id": report.nodeid,
        "phase": report.when,
        "outcome": report.outcome,
        "seconds": report.duration,
    }
    if isinstance(report, SubtestReport):
        entry["context"] = report.context._to_json()
        # The pinned pytest context normalizes repr values again on transport.
        # Verify the controller against that roundtrip without altering reports.
        entry["transport_context"] = type(report.context)._from_json(entry["context"])._to_json()
        _subtests.append(entry)
    else:
        _reports.append(entry)


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    worker = getattr(config, "workerinput", {}).get("workerid", "main")
    target = Path(os.environ["CI_TEST_PROFILE_DIR"])
    target.mkdir(parents=True, exist_ok=True)
    label = os.environ["CI_TEST_PROFILE_LABEL"]
    data = {
        "schema_version": "ci-pytest-inventory-v1",
        "worker": worker,
        "exit_code": int(exitstatus),
        "selected": _selected,
        "deselected": _deselected,
        "reports": _reports,
        "subtests": _subtests,
    }
    (target / f"{label}-inventory-{worker}.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
