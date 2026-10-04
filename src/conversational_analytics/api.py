"""FastAPI endpoints for owner-scoped conversations and durable SSE events."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .auth import client_address, hash_fingerprint, new_session_token, token_digest, verify_password
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


FORWARDING_HEADERS = {"forwarded", "x-real-ip"}
PUBLIC_PATHS = {"/api/chat/health", "/api/chat/login"}
LOGIN_BODY_LIMIT = 1_024


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


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
    worker_shutdown_timeout_seconds: float | None = None,
) -> FastAPI:
    config = config or ChatConfig.from_env()
    allow_local_openai = os.environ.get("CHAT_ALLOW_LOCAL_OPENAI", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    if config.provider == "openai" and config.auth_mode == "local" and not allow_local_openai:
        raise ValueError(
            "OpenAI mode requires password authentication "
            "(CHAT_ALLOW_LOCAL_OPENAI=true only on the owner's machine)"
        )
    config.validate_admission_budgets()
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
            timeout = (
                config.max_turn_seconds + 5
                if worker_shutdown_timeout_seconds is None
                else worker_shutdown_timeout_seconds
            )
            await asyncio.to_thread(worker.stop, timeout)

    app = FastAPI(title="Airline Tracker Chat API", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.chat_service = service
    app.state.chat_store = store
    app.state.chat_provider = provider
    app.state.chat_worker = worker
    app.state.snapshot_available = getattr(snapshot, "version", "unavailable") != "unavailable"
    app.state.begin_shutdown = worker.begin_shutdown if worker else (lambda: None)

    fingerprints = config.password_fingerprints()
    login_slots = threading.BoundedSemaphore(2)

    def bearer_digest(request: Request) -> str | None:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        return token_digest(token.strip()) if scheme.lower() == "bearer" and token.strip() else None

    @app.middleware("http")
    async def local_boundary_and_auth(request: Request, call_next):
        origin = request.headers.get("origin")
        peer = request.client.host if request.client else ""
        if request.method in {"POST", "PUT", "PATCH"}:
            # Bodies must declare their size; chunked uploads would bypass the limit.
            content_length = request.headers.get("content-length")
            if request.headers.get("transfer-encoding") or content_length is None:
                return JSONResponse({"detail": "content-length required"}, status_code=411)
            try:
                size = int(content_length)
            except ValueError:
                return JSONResponse({"detail": "invalid content length"}, status_code=400)
            limit = (
                LOGIN_BODY_LIMIT
                if request.url.path == "/api/chat/login"
                else max(16_384, config.max_message_chars * 8 + 4_096)
            )
            if size > limit:
                return JSONResponse({"detail": "request body too large"}, status_code=413)
        if config.auth_mode == "local":
            try:
                peer_local = ipaddress.ip_address(peer).is_loopback
            except ValueError:
                peer_local = False
            host = request.headers.get("host", "")
            if not peer_local or not _loopback_host(host):
                return JSONResponse({"detail": "local loopback access required"}, status_code=403)
            has_forwarding_headers = any(
                name in FORWARDING_HEADERS or name.startswith("x-forwarded-") for name in request.headers
            )
            if has_forwarding_headers:
                # A reverse proxy makes every client look like loopback.
                return JSONResponse({"detail": "local mode cannot run behind a proxy"}, status_code=403)
            if origin:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or not _loopback_host(parsed.hostname)
                ):
                    return JSONResponse({"detail": "non-local origin rejected"}, status_code=403)
            request.state.owner_id = "local"
            return await call_next(request)
        if origin and origin.rstrip("/") not in config.allowed_origins:
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        digest = bearer_digest(request)
        owner = await run_in_threadpool(store.session_owner, digest, fingerprints) if digest else None
        if not owner:
            return JSONResponse(
                {"detail": "login required"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )
        request.state.owner_id = owner
        return await call_next(request)

    # Add CORS after the auth middleware so it wraps even 401/403 responses.
    # No cookies: GitHub Pages and the API are cross-site, so third-party
    # cookies would be blocked. The login session travels in Authorization.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_origin_regex=r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?"
        if config.auth_mode == "local"
        else None,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        expose_headers=["Content-Type", "Retry-After"],
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
    def health():
        data = {**service.health(), "auth": config.auth_mode}
        if not app.state.snapshot_available:
            return JSONResponse(
                {**data, "status": "unavailable", "reason": "published_snapshot_unavailable"}, status_code=503
            )
        if not worker or not worker.running:
            return JSONResponse(
                {**data, "status": "degraded", "reason": "worker_unavailable"}, status_code=503
            )
        return data

    @app.post("/api/chat/login")
    def login(body: LoginBody, request: Request):
        if config.auth_mode != "password":
            return JSONResponse({"detail": "login is not used in local mode"}, status_code=400)
        peer = request.client.host if request.client else ""
        client = client_address(peer, request.headers.get("x-forwarded-for"), config.trusted_proxies)
        retry_after, attempt_id = store.begin_login_attempt(
            client,
            max_per_client=config.login_max_failures_per_client,
            window_minutes=config.login_client_window_minutes,
        )
        if retry_after:
            return JSONResponse(
                {"detail": "too many failed attempts", "retry_after_seconds": retry_after},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        # scrypt takes 32 MiB per hash; bound concurrent verifications so a
        # burst of logins cannot exhaust memory or the worker threadpool.
        if not login_slots.acquire(timeout=10):
            return JSONResponse(
                {"detail": "login busy, retry"}, status_code=503, headers={"Retry-After": "2"}
            )
        try:
            # Check every configured hash so timing does not reveal which matched.
            matched = [
                user
                for user, encoded in config.password_users.items()
                if verify_password(body.password, encoded)
            ]
        finally:
            login_slots.release()
        if len(matched) != 1:
            # The attempt already counts as a failure. The global count only
            # raises an alert: a hard global cap would let anyone lock the
            # owner out with wrong passwords from many addresses.
            if (
                store.recent_login_failures(config.login_global_window_minutes)
                >= config.login_max_failures_global
            ):
                LOG.error("Chat login failures above the global alert threshold")
            else:
                LOG.warning("Failed chat login attempt")
            return JSONResponse({"detail": "invalid password"}, status_code=401)
        store.forget_login_attempt(attempt_id)
        owner = matched[0]
        token = new_session_token()
        expires_at = store.create_session(
            token_digest(token),
            owner,
            hash_fingerprint(config.password_users[owner]),
            config.session_ttl_hours,
        )
        return {"session": token, "expires_at": expires_at}

    @app.post("/api/chat/logout", status_code=204)
    def logout(request: Request):
        digest = bearer_digest(request)
        if digest:
            store.revoke_session(digest)
        return Response(status_code=204)

    @app.post("/api/chat/conversations", status_code=201)
    def create_conversation(request: Request):
        if not app.state.snapshot_available:
            return JSONResponse({"detail": "published snapshot unavailable"}, status_code=503)
        return service.create_conversation(request.state.owner_id)

    @app.get("/api/chat/conversations/{conversation_id}")
    def get_conversation(conversation_id: str, request: Request):
        return store.get_conversation(request.state.owner_id, conversation_id)

    @app.delete("/api/chat/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str, request: Request):
        service.delete_conversation(request.state.owner_id, conversation_id)
        # No body: a 204 carrying "null" breaks HTTP/1.1 keep-alive under uvicorn.
        return Response(status_code=204)

    @app.post("/api/chat/conversations/{conversation_id}/messages", status_code=202)
    def submit_message(conversation_id: str, body: MessageBody, request: Request):
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
        await run_in_threadpool(store.get_turn, owner, turn_id)
        loop = asyncio.get_running_loop()
        # Bound each connection; the client reconnects with the last sequence.
        stream_deadline = loop.time() + config.max_turn_seconds + 30

        async def stream():
            cursor = after
            last_ping = loop.time()
            while True:
                # Status is read before events, so a terminal status implies its
                # final events are already visible in the same read.
                rows, status = await run_in_threadpool(store.events_and_status, owner, turn_id, cursor)
                for event in rows:
                    cursor = event["seq"]
                    data = json.dumps(event["data"], ensure_ascii=False, separators=(",", ":"))
                    yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {data}\n\n"
                if status in {"completed", "failed", "cancelled"}:
                    break
                now = loop.time()
                if now >= stream_deadline:
                    break
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
    def cancel_turn(turn_id: str, request: Request):
        status = store.request_cancel(request.state.owner_id, turn_id)
        if worker:
            worker.cancel(turn_id)
        return {"turn_id": turn_id, "status": status}

    return app


__all__ = ["create_app"]
