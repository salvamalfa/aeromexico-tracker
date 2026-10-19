import json
import shutil
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.source_updates.build import build
from src.source_updates.catalog import ROOT


@pytest.mark.parametrize("returncode,finished_at", [(1, None), (0, None), (1, "2026-10-19T00:00:00Z")])
def test_partial_or_failed_worker_never_accepts_a_completed_intermediate_snapshot(
    monkeypatch, returncode, finished_at
):
    work = ROOT / "tmp/source-updates" / ("worker-receipt-" + uuid4().hex)

    def worker(args, **kwargs):
        from pathlib import Path

        Path(args[-1]).write_text(
            json.dumps({"status": "completed", "finished_at": finished_at, "steps": []})
        )
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr("src.source_updates.build.subprocess.run", worker)
    try:
        result = build(work, ["parse.fuel"], execute=True)
        assert result["status"].startswith("failed")
        assert result["returncode"] == returncode
        assert result["activation"] == "none"
    finally:
        shutil.rmtree(work, ignore_errors=True)
