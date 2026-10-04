from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from src.conversational_analytics.api import create_app
from src.conversational_analytics.config import ChatConfig


class Snapshot:
    version = "snapshot-v1"
    semantic_version = "semantic-v1"

    def catalog(self):
        return {"metrics": {"metrics": []}}


def test_bearer_owner_isolation_and_strict_cors(tmp_path: Path):
    alice, bob = "alice-secret", "bob-secret"
    config = ChatConfig(
        state_path=tmp_path / "chat.sqlite3",
        auth_mode="bearer",
        bearer_users={
            hashlib.sha256(alice.encode()).hexdigest(): "alice",
            hashlib.sha256(bob.encode()).hexdigest(): "bob",
        },
        allowed_origins=("https://dashboard.example",),
    )
    app = create_app(config, snapshot=Snapshot(), provider=object(), start_worker=False)
    client = TestClient(app, base_url="http://127.0.0.1")
    allowed_preflight = client.options(
        "/api/chat/conversations",
        headers={
            "Origin": "https://dashboard.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert allowed_preflight.status_code == 200
    assert allowed_preflight.headers["access-control-allow-origin"] == "https://dashboard.example"
    missing_auth = client.get("/api/chat/health", headers={"Origin": "https://dashboard.example"})
    assert missing_auth.status_code == 401
    assert missing_auth.headers["access-control-allow-origin"] == "https://dashboard.example"
    assert client.get("/api/chat/health", headers={"Origin": "https://evil.example"}).status_code == 403

    created = client.post("/api/chat/conversations", headers={"Authorization": f"Bearer {alice}"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    denied = client.get(
        f"/api/chat/conversations/{conversation_id}", headers={"Authorization": f"Bearer {bob}"}
    )
    assert denied.status_code == 404
    mine = client.get(
        f"/api/chat/conversations/{conversation_id}", headers={"Authorization": f"Bearer {alice}"}
    )
    assert mine.status_code == 200
    assert mine.json()["snapshot_version"] == "snapshot-v1"


def test_local_mode_rejects_non_loopback_origin_and_host(tmp_path: Path):
    config = ChatConfig(state_path=tmp_path / "chat.sqlite3")
    app = create_app(config, snapshot=Snapshot(), provider=object(), start_worker=False)
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/api/chat/health", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/chat/health", headers={"Host": "outside.example"}).status_code == 403
