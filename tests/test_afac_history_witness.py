"""Bounded transport repair never weakens expected bytes or baseline identity."""

from email.message import Message
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError, URLError

import pytest

from src.publish import afac_history_witness as witness


class Response:
    status = 200

    def __init__(self, url, body):
        self.url, self.body = url, body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self):
        return self.body


def failure(status=503, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError("https://example.invalid", status, "temporary", headers, None)


def transport(monkeypatch, responses):
    calls, delays = [], []

    def open_request(request, timeout):
        calls.append(request)
        assert request.get_method() == "GET" and timeout == 45
        value = responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return Response(request.full_url, value)

    monkeypatch.setattr(witness, "urlopen", open_request)
    # Patch the module name, not the process-wide time.sleep used by threads.
    from types import SimpleNamespace

    monkeypatch.setattr(witness, "time", SimpleNamespace(sleep=delays.append))
    return calls, delays


def test_503_then_exact_200_retries_only_the_same_get_and_honors_capped_retry_after(monkeypatch):
    calls, delays = transport(monkeypatch, [failure(retry_after="9999"), b"correct"])
    assert witness.get_verified("data/v1/market.json", b"correct") == b"correct"
    assert len(calls) == 2 and calls[0].full_url == calls[1].full_url
    assert delays == [witness.RETRY_AFTER_CAP_SECONDS]


def test_three_transient_failures_are_fatal_without_a_fourth_attempt(monkeypatch):
    calls, delays = transport(monkeypatch, [failure(), failure(), failure()])
    with pytest.raises(ValueError, match="after 3 attempt"):
        witness.get_verified("data/v1/market.json", b"correct")
    assert len(calls) == 3 and delays == [1.0, 2.0]


def test_http200_wrong_hash_is_immediately_fatal_even_at_the_right_size(monkeypatch):
    calls, delays = transport(monkeypatch, [b"incorrect", b"correctxx"])
    with pytest.raises(ValueError, match="HTTP200 differs"):
        witness.get_verified("data/v1/market.json", b"correctxx")
    assert len(calls) == 1 and delays == []


@pytest.mark.parametrize("status", [403, 404, 501])
def test_nontransient_http_status_is_not_retried(monkeypatch, status):
    calls, delays = transport(monkeypatch, [failure(status)])
    with pytest.raises(ValueError, match="after 1 attempt"):
        witness.get_verified("data/v1/market.json", b"correct")
    assert len(calls) == 1 and delays == []


def test_actual_302_to_another_origin_never_emits_second_get_or_retries(monkeypatch):
    from types import SimpleNamespace

    calls, delays = [], []

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append("outside_origin")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"correct")

        def log_message(self, *args):
            pass

    target = ThreadingHTTPServer(("127.0.0.1", 0), Destination)

    class Origin(Destination):
        def do_GET(self):
            calls.append("origin")
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/outside")
            self.end_headers()

    source = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
    threads = [
        Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        for server in (source, target)
    ]
    for thread in threads:
        thread.start()
    monkeypatch.setattr(witness.transport, "ORIGIN", f"http://127.0.0.1:{source.server_port}")
    monkeypatch.setattr(witness, "time", SimpleNamespace(sleep=delays.append))
    try:
        with pytest.raises(ValueError, match="after 1 attempt"):
            witness.get_verified("data/v1/market.json", b"correct")
        assert calls == ["origin"]
        assert delays == []
    finally:
        for server in (source, target):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=1)


@pytest.mark.parametrize("error", [TimeoutError(), IncompleteRead(b"part", 7), URLError(TimeoutError())])
def test_only_known_transport_interruptions_may_retry(monkeypatch, error):
    calls, delays = transport(monkeypatch, [error, b"correct"])
    assert witness.get_verified("data/v1/market.json", b"correct") == b"correct"
    assert len(calls) == 2 and delays == [1.0]


def test_unknown_transport_failure_and_unsafe_root_do_not_retry(monkeypatch):
    calls, delays = transport(monkeypatch, [URLError("unclassified DNS failure")])
    with pytest.raises(ValueError, match="after 1 attempt"):
        witness.get_verified("data/v1/market.json", b"correct")
    with pytest.raises(ValueError, match="Unsafe"):
        witness.get_verified("../outside", b"correct")
    assert len(calls) == 1 and delays == []


@pytest.fixture
def baseline(monkeypatch, tmp_path):
    base, head = "a" * 40, "b" * 40
    raw, files = b'{"files":[]}', {"data/v1/value.json": b"{}", "assets/application.js": b"/* exact */"}
    scope = {"baseline_commit": base, "baseline_manifest_sha256": witness.sha(raw)}
    monkeypatch.setattr(witness, "site_tree", lambda *args: ({"files": list(files)}, raw, files))
    monkeypatch.setattr(witness, "successful_deployment", lambda *args: {"headSha": base, "databaseId": 42})
    monkeypatch.setattr(witness.transport, "_git", lambda *args: (base + " refs/heads/master").encode())
    monkeypatch.setattr(witness.manifests, "current_commit", lambda *args: head)
    return tmp_path, scope, raw, files


def test_manifest_is_witnessed_before_and_after_all_exact_files(monkeypatch, baseline):
    root, scope, raw, files = baseline
    calls = []

    def get(name, expected):
        calls.append((name, expected))
        assert expected == (raw if name == "publication_manifest.json" else files[name])
        return expected

    monkeypatch.setattr(witness, "get_verified", get)
    receipt = witness.witness_remote(root, scope)
    assert calls[0] == calls[-1] == ("publication_manifest.json", raw)
    assert {name for name, _ in calls[1:-1]} == set(files)
    assert receipt["files_verified"] == 2


def test_changed_manifest_http200_after_files_is_fatal(monkeypatch, baseline):
    root, scope, raw, files = baseline
    calls = []

    def open_request(request, timeout):
        name = request.full_url.removeprefix(witness.transport.ORIGIN + "/")
        calls.append(name)
        expected = raw if name == "publication_manifest.json" else files[name]
        if name == "publication_manifest.json" and calls.count(name) == 2:
            expected = b'{"files":[1]}'
        return Response(request.full_url, expected)

    monkeypatch.setattr(witness, "urlopen", open_request)
    with pytest.raises(ValueError, match="HTTP200 differs"):
        witness.witness_remote(root, scope)
    assert calls.count("publication_manifest.json") == 2


@pytest.mark.parametrize("move", ["head", "remote"])
def test_head_or_remote_move_during_witness_aborts(monkeypatch, baseline, move):
    root, scope, _, _ = baseline
    monkeypatch.setattr(witness, "get_verified", lambda name, expected: expected)
    if move == "head":
        values = iter(["b" * 40, "c" * 40])
        monkeypatch.setattr(witness.manifests, "current_commit", lambda *args: next(values))
    else:
        values = iter(["a" * 40, "c" * 40])
        monkeypatch.setattr(witness.transport, "_git", lambda *args: (next(values) + " master").encode())
    with pytest.raises(ValueError, match="moved"):
        witness.witness_remote(root, scope)
