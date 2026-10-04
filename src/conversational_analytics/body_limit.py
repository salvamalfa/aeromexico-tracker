"""Bounded ASGI buffering for small JSON request bodies.

ASGI servers may deliver HTTP/2 or edge-forwarded request bodies without a
Content-Length header. Enforce the actual byte limit while reading instead of
requiring that optional header or trusting it as the only limit.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable


class BoundedBodyMiddleware:
    def __init__(self, app, limit_for_path: Callable[[str], int], read_timeout_seconds: float = 10.0):
        self.app = app
        self.limit_for_path = limit_for_path
        self.read_timeout_seconds = read_timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        limit = self.limit_for_path(scope["path"])
        raw_headers = scope.get("headers", ())
        lengths = [value for name, value in raw_headers if name.lower() == b"content-length"]
        encodings = [value for name, value in raw_headers if name.lower() == b"transfer-encoding"]
        if len(lengths) > 1 or (lengths and encodings):
            await self._reject(send, 400, "invalid content length")
            return

        declared: int | None = None
        if lengths:
            raw = lengths[0]
            if not raw or not raw.isdigit():
                await self._reject(send, 400, "invalid content length")
                return
            try:
                declared = int(raw)
            except ValueError:
                await self._reject(send, 400, "invalid content length")
                return
            if declared > limit:
                await self._reject(send, 413, "request body too large")
                return
        if encodings and any(value.strip().lower() != b"chunked" for value in encodings):
            await self._reject(send, 400, "unsupported transfer encoding")
            return

        body = bytearray()
        size = 0
        oversized = False
        try:
            async with asyncio.timeout(self.read_timeout_seconds):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    if message["type"] != "http.request":
                        continue
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > limit:
                        oversized = True
                        break
                    if chunk:
                        body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await self._reject(send, 408, "request body timeout")
            return
        if oversized:
            await self._reject(send, 413, "request body too large")
            return
        if declared is not None and size != declared:
            await self._reject(send, 400, "content length mismatch")
            return

        bounded_body = bytes(body)
        replayed = False

        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bounded_body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(send, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}, separators=(",", ":")).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
