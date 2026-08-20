from collections.abc import Iterator

import httpx
import pytest
from tenacity import wait_none

from src.common.http import SourceHttpClient, TokenBucket
from src.config import MissingSecUserAgentError


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def unlimited_limiter() -> Iterator[TokenBucket]:
    fake = FakeTime()
    yield TokenBucket(1_000_000, clock=fake.monotonic, sleeper=fake.sleep)


def test_rate_limiter_does_not_exceed_configured_rate() -> None:
    fake = FakeTime()
    limiter = TokenBucket(2.0, capacity=1.0, clock=fake.monotonic, sleeper=fake.sleep)
    acquisition_times: list[float] = []

    for _ in range(3):
        limiter.acquire()
        acquisition_times.append(fake.now)

    assert acquisition_times == pytest.approx([0.0, 0.5, 1.0])
    assert fake.sleeps == pytest.approx([0.5, 0.5])


def test_sec_request_fails_before_network_without_user_agent(
    monkeypatch: pytest.MonkeyPatch,
    unlimited_limiter: TokenBucket,
) -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with SourceHttpClient(
        "sec",
        transport=httpx.MockTransport(handler),
        limiter=unlimited_limiter,
        retry_wait=wait_none(),
    ) as client:
        with pytest.raises(MissingSecUserAgentError):
            client.request("GET", "https://data.sec.gov/example.json")

    assert called is False


def test_sec_request_uses_configured_identity(
    monkeypatch: pytest.MonkeyPatch,
    unlimited_limiter: TokenBucket,
) -> None:
    observed_user_agent = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_user_agent
        observed_user_agent = request.headers["User-Agent"]
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setenv("SEC_USER_AGENT", "Aeromexico Tracker test@example.com")
    with SourceHttpClient(
        "sec",
        transport=httpx.MockTransport(handler),
        limiter=unlimited_limiter,
        retry_wait=wait_none(),
    ) as client:
        assert client.get_json("https://data.sec.gov/example.json") == {"ok": True}

    assert observed_user_agent == "Aeromexico Tracker test@example.com"


def test_retryable_status_is_retried_then_succeeds(
    unlimited_limiter: TokenBucket,
) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, text="temporary")
        return httpx.Response(200, text="ready")

    with SourceHttpClient(
        "default",
        transport=httpx.MockTransport(handler),
        limiter=unlimited_limiter,
        retry_wait=wait_none(),
    ) as client:
        response = client.request("GET", "https://example.test/resource")

    assert response.text == "ready"
    assert attempts == 3


def test_non_retryable_status_fails_once(unlimited_limiter: TokenBucket) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, text="missing")

    with SourceHttpClient(
        "default",
        transport=httpx.MockTransport(handler),
        limiter=unlimited_limiter,
        retry_wait=wait_none(),
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.request("GET", "https://example.test/missing")

    assert attempts == 1
