"""Polite HTTP client with strict rate limits, retries, and request telemetry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
import logging
from threading import Lock
import time
from typing import Any, ParamSpec, TypeVar

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from src.common.logging import log_event
from src.config import RATE_LIMITS, get_sec_user_agent


P = ParamSpec("P")
R = TypeVar("R")
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class RetryableHttpStatusError(httpx.HTTPStatusError):
    """HTTP response that should be retried under the project policy."""


class TokenBucket:
    """Thread-safe token bucket with injectable time for deterministic tests."""

    def __init__(
        self,
        rate_per_second: float,
        *,
        capacity: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if capacity < 1:
            raise ValueError("capacity must be at least one")
        self.rate_per_second = float(rate_per_second)
        self.capacity = float(capacity)
        self._clock = clock
        self._sleeper = sleeper
        self._tokens = self.capacity
        self._last_refill = self._clock()
        self._lock = Lock()

    def acquire(self) -> None:
        """Block until exactly one token is available, then consume it."""

        with self._lock:
            while True:
                now = self._clock()
                elapsed = max(0.0, now - self._last_refill)
                self._tokens = min(
                    self.capacity,
                    self._tokens + elapsed * self.rate_per_second,
                )
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait_seconds = (1.0 - self._tokens) / self.rate_per_second
                self._sleeper(wait_seconds)


_LIMITERS: dict[str, TokenBucket] = {}
_LIMITERS_LOCK = Lock()


def get_rate_limiter(source: str) -> TokenBucket:
    """Return one process-wide limiter for a configured source."""

    if source not in RATE_LIMITS:
        raise KeyError(f"Unknown rate-limit source: {source}")
    with _LIMITERS_LOCK:
        limiter = _LIMITERS.get(source)
        if limiter is None:
            limiter = TokenBucket(RATE_LIMITS[source], capacity=1.0)
            _LIMITERS[source] = limiter
        return limiter


def rate_limited(source: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a synchronous operation with the configured source limiter."""

    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            get_rate_limiter(source).acquire()
            return function(*args, **kwargs)

        return wrapper

    return decorator


def _is_retryable(exception: BaseException) -> bool:
    return isinstance(exception, (httpx.TransportError, RetryableHttpStatusError))


class SourceHttpClient:
    """Source-aware synchronous HTTP client used by ingestion jobs."""

    def __init__(
        self,
        source: str,
        *,
        timeout_seconds: float = 60.0,
        max_attempts: int = 5,
        transport: httpx.BaseTransport | None = None,
        limiter: TokenBucket | None = None,
        retry_wait: Any | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if source not in RATE_LIMITS:
            raise KeyError(f"Unknown source: {source}")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self.source = source
        self.max_attempts = max_attempts
        self.limiter = limiter or get_rate_limiter(source)
        self.logger = logger or logging.getLogger("aeromexico_tracker.http")
        self._retry_wait = retry_wait or wait_exponential_jitter(
            initial=1,
            max=30,
            jitter=1,
        )
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            transport=transport,
            headers={"Accept": "*/*"},
        )

    def _headers(self, supplied: Mapping[str, str] | None) -> httpx.Headers:
        headers = httpx.Headers(supplied or {})
        if self.source == "sec":
            headers["User-Agent"] = get_sec_user_agent()
        elif "User-Agent" not in headers:
            headers["User-Agent"] = "Aeromexico-Tracker/0.1"
        return headers

    def _request_once(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None,
        request_kwargs: dict[str, Any],
        attempt_number: int,
    ) -> httpx.Response:
        self.limiter.acquire()
        started = time.perf_counter()
        try:
            response = self._client.request(
                method,
                url,
                headers=self._headers(headers),
                **request_kwargs,
            )
        except httpx.TransportError as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            log_event(
                self.logger,
                logging.WARNING,
                "http_transport_error",
                source=self.source,
                url=url,
                duration_ms=duration_ms,
                attempt=attempt_number,
                error_type=type(exc).__name__,
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        log_event(
            self.logger,
            logging.INFO,
            "http_response",
            source=self.source,
            url=str(response.url),
            status=response.status_code,
            bytes=len(response.content),
            duration_ms=duration_ms,
            attempt=attempt_number,
        )
        if response.status_code in RETRYABLE_STATUS_CODES:
            raise RetryableHttpStatusError(
                f"Retryable status {response.status_code} for {response.url}",
                request=response.request,
                response=response,
            )
        response.raise_for_status()
        return response

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        **request_kwargs: Any,
    ) -> httpx.Response:
        """Run an HTTP request with source policy and at most five attempts."""

        retrying = Retrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=self._retry_wait,
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return self._request_once(
                    method,
                    url,
                    headers=headers,
                    request_kwargs=request_kwargs,
                    attempt_number=attempt.retry_state.attempt_number,
                )
        raise RuntimeError("Retry loop ended without a response")

    def get_json(self, url: str, **request_kwargs: Any) -> Any:
        response = self.request("GET", url, **request_kwargs)
        return response.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SourceHttpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
