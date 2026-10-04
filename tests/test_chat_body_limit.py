from __future__ import annotations

import asyncio

import pytest

from src.conversational_analytics.body_limit import BoundedBodyMiddleware


async def _invoke(headers, chunks, limit=8, receive_delay=0, send_delay=0):
    seen: list[bytes] = []
    sent = []

    async def app(scope, receive, send):
        while True:
            message = await receive()
            seen.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    messages = iter(
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    )

    async def receive():
        if receive_delay:
            await asyncio.sleep(receive_delay)
        return next(messages, {"type": "http.disconnect"})

    async def send(message):
        if send_delay:
            await asyncio.sleep(send_delay)
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/chat/login", "headers": headers}
    await BoundedBodyMiddleware(app, lambda _: limit, read_timeout_seconds=0.025)(scope, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    return status, b"".join(seen), sent


def _response_body(sent):
    return next(item.get("body", b"") for item in sent if item["type"] == "http.response.body")


def test_accepts_bounded_multichunk_body_without_content_length():
    status, body, _ = asyncio.run(
        _invoke([(b"content-type", b"application/json")], [b'{"pass', b'word":1}'], limit=32)
    )
    assert status == 204
    assert body == b'{"password":1}'


@pytest.mark.parametrize("header", [b"-1", b"+2", b"abc", b""])
def test_rejects_invalid_declared_content_length(header):
    status, body, _ = asyncio.run(_invoke([(b"content-length", header)], [b"{}"]))
    assert status == 400
    assert b"invalid content length" in _response_body(_)


def test_rejects_duplicate_and_conflicting_length_headers():
    status, _, _ = asyncio.run(_invoke([(b"content-length", b"2"), (b"content-length", b"2")], [b"{}"]))
    assert status == 400
    status, _, _ = asyncio.run(
        _invoke([(b"content-length", b"2"), (b"transfer-encoding", b"chunked")], [b"{}"])
    )
    assert status == 400


def test_rejects_mismatched_declared_length_and_actual_oversize_stream():
    status, _, _ = asyncio.run(_invoke([(b"content-length", b"4")], [b"{}"]))
    assert status == 400
    status, _, sent = asyncio.run(_invoke([], [b"123456", b"789"]))
    assert status == 413
    assert b"request body too large" in sent[1]["body"]


def test_rejects_oversized_declared_body_without_reading_it():
    status, body, sent = asyncio.run(_invoke([(b"content-length", b"9")], [b"ignored"], limit=8))
    assert status == 413
    assert body == b""
    assert sent[1]["body"] == b'{"detail":"request body too large"}'


def test_bounds_time_spent_reading_empty_or_stalled_body_chunks():
    status, _, sent = asyncio.run(_invoke([], [b"", b"", b"", b""], receive_delay=0.01))
    assert status == 408
    assert _response_body(sent) == b'{"detail":"request body timeout"}'


def test_slow_413_response_is_not_replaced_by_a_second_timeout_response():
    status, body, sent = asyncio.run(_invoke([], [b"123456789"], send_delay=0.05))
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert status == 413
    assert body == b""
    assert len(starts) == 1 and starts[0]["status"] == 413
