"""FastAPI endpoints for owner-scoped conversations and durable SSE events."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .config import ChatConfig
from .providers import MockProvider
from .service import ChatService, InvalidRequest
from .storage import AdmissionDenied, ChatStore, Conflict, NotFound
from .worker import TurnWorker

LOG = logging.getLogger("conversational_analytics.api")


class UnavailableSnapshot:
    version = "unavailable"

    def catalog(self):
        return {}


class MessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1)
    client_message_id: str
    context: dict | None = None


def _loopback_host(host: str) -> bool:
    host = urlsplit(f"//{host}").hostname or ""
    host = host.lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def create_app(
    config: ChatConfig | None = None,
    snapshot=None,
    provider=None,
    start_worker: bool = True,
) -> FastAPI:
    config = config or ChatConfig.from_env()
    if snapshot is None:
        try:
            from .data.snapshot import Snapshot

            snapshot = Snapshot(Path(os.environ.get("CHAT_SNAPSHOT_ROOT", "site")))
        except Exception as exc:
            LOG.warning("Published snapshot unavailable (%s)", type(exc).__name__)
            snapshot = UnavailableSnapshot()
    if provider is None:
        if config.provider == "mock":
            provider = MockProvider(snapshot)
        else:
            # Lazy and opt-in: imports and app setup without credentials have
            # no provider client or network side effects.
            from .providers.openai import OpenAIProvider

            provider = OpenAIProvider(config)
    store = ChatStore(config.state_path)
    worker = (
        TurnWorker(store, config, provider, snapshot)
        if start_worker and getattr(snapshot, "version", "unavailable") != "unavailable"
        else None
    )
    service = ChatService(store, config, snapshot, worker, provider)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if worker:
            worker.start()
        yield
        if worker:
            worker.stop()

    app = FastAPI(title="Airline Tracker Chat API", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.chat_service = service
    app.state.chat_store = store
    app.state.chat_provider = provider
    app.state.chat_worker = worker
    app.state.snapshot_available = getattr(snapshot, "version", "unavailable") != "unavailable"

    @app.middleware("http")
    async def local_boundary_and_auth(request: Request, call_next):
        origin = request.headers.get("origin")
        peer = request.client.host if request.client else ""
        if config.auth_mode == "local":
            try:
                peer_local = ipaddress.ip_address(peer).is_loopback
            except ValueError:
                peer_local = False
            host = request.headers.get("host", "")
            if not peer_local or not _loopback_host(host):
                return JSONResponse({"detail": "local loopback access required"}, status_code=403)
            if origin:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or not _loopback_host(parsed.hostname)
                ):
                    return JSONResponse({"detail": "non-local origin rejected"}, status_code=403)
            request.state.owner_id = "local"
        else:
            if origin and config.allowed_origins and origin.rstrip("/") not in config.allowed_origins:
                return JSONResponse({"detail": "origin not allowed"}, status_code=403)
            if origin and not config.allowed_origins:
                return JSONResponse({"detail": "CHAT_ALLOWED_ORIGINS must be configured"}, status_code=403)
            if request.method == "OPTIONS":
                return await call_next(request)
            auth = request.headers.get("authorization", "")
            scheme, _, token = auth.partition(" ")
            owner = config.owner_for_token(token) if scheme.lower() == "bearer" and token else None
            if not owner:
                return JSONResponse(
                    {"detail": "bearer authentication required"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            request.state.owner_id = owner
        content_length = request.headers.get("content-length")
        if content_length and request.method in {"POST", "PUT", "PATCH"}:
            try:
                too_large = int(content_length) > max(16_384, config.max_message_chars * 8 + 4_096)
            except ValueError:
                return JSONResponse({"detail": "invalid content length"}, status_code=400)
            if too_large:
                return JSONResponse({"detail": "request body too large"}, status_code=413)
        return await call_next(request)

    # Add CORS after the auth middleware so it wraps even 401/403 responses.
    # No cookies are accepted; only explicit origins and the bearer header.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_origin_regex=r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?"
        if config.auth_mode == "local"
        else None,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        expose_headers=["Content-Type"],
        max_age=600,
    )

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(Conflict)
    async def conflict(_: Request, exc: Conflict):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(AdmissionDenied)
    async def admission(_: Request, exc: AdmissionDenied):
        return JSONResponse({"detail": str(exc)}, status_code=429)

    @app.exception_handler(InvalidRequest)
    async def invalid(_: Request, exc: InvalidRequest):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/api/chat/health")
    async def health():
        data = service.health()
        if not app.state.snapshot_available:
            return JSONResponse(
                {**data, "status": "unavailable", "reason": "published_snapshot_unavailable"}, status_code=503
            )
        if not worker or not worker.running:
            return JSONResponse(
                {**data, "status": "degraded", "reason": "worker_unavailable"}, status_code=503
            )
        return data

    @app.post("/api/chat/conversations", status_code=201)
    async def create_conversation(request: Request):
        if not app.state.snapshot_available:
            return JSONResponse({"detail": "published snapshot unavailable"}, status_code=503)
        return service.create_conversation(request.state.owner_id)

    @app.get("/api/chat/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str, request: Request):
        return store.get_conversation(request.state.owner_id, conversation_id)

    @app.delete("/api/chat/conversations/{conversation_id}", status_code=204)
    async def delete_conversation(conversation_id: str, request: Request):
        service.delete_conversation(request.state.owner_id, conversation_id)
        return JSONResponse(status_code=204, content=None)

    @app.post("/api/chat/conversations/{conversation_id}/messages", status_code=202)
    async def submit_message(conversation_id: str, body: MessageBody, request: Request):
        if not app.state.snapshot_available:
            return JSONResponse({"detail": "published snapshot unavailable"}, status_code=503)
        service.ensure_current_snapshot(request.state.owner_id, conversation_id)
        if not worker or not worker.running:
            return JSONResponse({"detail": "worker unavailable"}, status_code=503)
        return service.submit(
            request.state.owner_id, conversation_id, body.content, body.client_message_id, body.context
        )

    @app.get("/api/chat/turns/{turn_id}/events")
    async def events(
        turn_id: str,
        request: Request,
        after: int = 0,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        if after < 0:
            return JSONResponse({"detail": "after must be non-negative"}, status_code=422)
        if last_event_id:
            try:
                after = max(after, int(last_event_id))
            except ValueError:
                return JSONResponse({"detail": "Last-Event-ID must be an integer"}, status_code=422)
        owner = request.state.owner_id
        store.get_turn(owner, turn_id)

        async def stream():
            cursor = after
            last_ping = asyncio.get_running_loop().time()
            while True:
                rows = store.list_events(owner, turn_id, cursor)
                for event in rows:
                    cursor = event["seq"]
                    data = json.dumps(event["data"], ensure_ascii=False, separators=(",", ":"))
                    yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {data}\n\n"
                turn = store.get_turn(owner, turn_id)
                if turn["status"] in {"completed", "failed", "cancelled"} and not store.list_events(
                    owner, turn_id, cursor
                ):
                    break
                now = asyncio.get_running_loop().time()
                if now - last_ping > 15:
                    yield ": keep-alive\n\n"
                    last_ping = now
                if await request.is_disconnected():
                    break
                await asyncio.sleep(config.poll_interval_seconds)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/chat/turns/{turn_id}/cancel")
    async def cancel_turn(turn_id: str, request: Request):
        status = store.request_cancel(request.state.owner_id, turn_id)
        if worker:
            worker.cancel(turn_id)
        return {"turn_id": turn_id, "status": status}

    return app


__all__ = ["create_app"]
