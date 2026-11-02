"""Explicit local frontend origins preserve the hosted password boundary."""

import json

import pytest
from fastapi.testclient import TestClient
from test_chat_api import Snapshot

from src.conversational_analytics.api import create_app
from src.conversational_analytics.auth import hash_password
from src.conversational_analytics.config import ChatConfig


def configure(monkeypatch, origin):
    monkeypatch.setenv("CHAT_PROVIDER", "mock")
    monkeypatch.setenv("CHAT_ADMISSION_ENABLED", "true")
    monkeypatch.setenv("CHAT_AUTH_MODE", "password")
    monkeypatch.setenv(
        "CHAT_PASSWORDS_JSON",
        json.dumps([{"user_id": "owner", "password_hash": hash_password("local-origin-test-password")}]),
    )
    monkeypatch.setenv("CHAT_ALLOWED_ORIGINS", origin)


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "http://localhost:5173"])
def test_explicit_development_origin_passes_cors_but_still_requires_login(monkeypatch, tmp_path, origin):
    configure(monkeypatch, f"https://salvamalfa.github.io,{origin}")
    monkeypatch.setenv("CHAT_STATE_PATH", str(tmp_path / "chat.sqlite3"))
    config = ChatConfig.from_env()
    assert config.auth_mode == "password"
    app = create_app(config, snapshot=Snapshot(), provider=object(), start_worker=False)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        preflight = client.options(
            "/api/chat/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin
        # No worker runs in this CORS fixture; readiness can be 503 while the
        # public health endpoint still reports the unchanged password boundary.
        health = client.get("/api/chat/health", headers={"Origin": origin})
        assert health.json()["auth"] == "password"
        assert health.headers["access-control-allow-origin"] == origin
        assert client.post("/api/chat/conversations", headers={"Origin": origin}).status_code == 401
        for other in ["http://127.0.0.1:5174", "http://127.0.0.1.evil:5173", "https://evil.example"]:
            assert client.get("/api/chat/health", headers={"Origin": other}).status_code == 403


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "http://localhost:5174",
        "http://localhost:5173/path",
        "http://127.0.0.1.evil:5173",
        "http://0.0.0.0:5173",
    ],
)
def test_other_http_or_wildcard_origins_remain_rejected(monkeypatch, origin):
    configure(monkeypatch, origin)
    with pytest.raises(ValueError, match="HTTPS origins"):
        ChatConfig.from_env()
