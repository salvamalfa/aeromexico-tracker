from pathlib import Path

import httpx
import pytest

from scripts.refresh_anac_routes import RangeClient, refresh
from src.ingest.international_routes import ANAC_URL, anac_content
from src.source_updates.catalog import bronze_aliases
from src.source_updates.retained_registry import spec


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def response(body, content_range, validator='"one-edition"'):
    return httpx.Response(
        206,
        content=body,
        headers={"content-range": content_range, "etag": validator},
        request=httpx.Request("GET", ANAC_URL),
    )


def test_assembles_complete_original_and_binds_subsequent_range(tmp_path):
    client = Client([response(b"ab", "bytes 0-1/4"), response(b"cd", "bytes 2-3/4")])
    body, headers = anac_content(client, cache_root=tmp_path)
    assert body == b"abcd"
    assert headers["etag"] == '"one-edition"'
    assert client.calls[1][1]["headers"]["If-Range"] == '"one-edition"'
    assert client.calls[1][1]["headers"]["Range"] == "bytes=2-3"


def test_changed_edition_does_not_create_complete_original(tmp_path):
    client = Client([response(b"ab", "bytes 0-1/4"), response(b"cd", "bytes 2-3/4", '"new-edition"')])
    with pytest.raises(ValueError, match="Inconsistent range"):
        anac_content(client, cache_root=tmp_path)


def test_size_bound_fails_before_fetching_remaining_ranges(tmp_path):
    client = Client([response(b"ab", "bytes 0-1/999")])
    with pytest.raises(ValueError, match="byte bound"):
        anac_content(client, cache_root=tmp_path, max_bytes=4)
    assert len(client.calls) == 1


def test_native_dry_run_never_creates_workspace(monkeypatch):
    workspace = Path("tmp/source-updates/anac-dry-run-contract")
    monkeypatch.setattr(
        "scripts.refresh_anac_routes.SourceHttpClient", lambda *a, **k: pytest.fail("network")
    )
    existed = workspace.exists()
    result = refresh(workspace)
    assert result["status"] == "dry_run" and result["paid_requests"] == 0
    assert result["maximum_http_requests"] == 187
    assert workspace.exists() == existed


def test_range_transport_rejects_other_source_before_network():
    client = RangeClient(None)
    with pytest.raises(ValueError, match="exact public original"):
        client.get("https://example.com/file")
    assert client.calls == []


def test_current_anac_alias_reaches_its_existing_certifier():
    assert "anac" in bronze_aliases("anac")
    assert "anac" in spec("anac")["roles"]["json"]
