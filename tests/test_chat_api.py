from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from src.conversational_analytics.__main__ import main as chat_main
from src.conversational_analytics.api import create_app
from src.conversational_analytics.auth import (
    client_address,
    generate_password,
    hash_password,
    parse_password_hash,
    verify_password,
)
from src.conversational_analytics.config import ChatConfig

ORIGIN = "https://dashboard.example"


class Snapshot:
    version = "snapshot-v1"
    semantic_version = "semantic-v1"

    def catalog(self):
        return {"metrics": {"metrics": []}}


def _password_app(tmp_path: Path, users: dict[str, str], **overrides):
    config = ChatConfig(
        state_path=tmp_path / "chat.sqlite3",
        auth_mode="password",
        password_users=users,
        allowed_origins=(ORIGIN,),
        **overrides,
    )
    app = create_app(config, snapshot=Snapshot(), provider=object(), start_worker=False)
    return app, TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def _login(client: TestClient, password: str, **headers: str):
    return client.post("/api/chat/login", json={"password": password}, headers={"Origin": ORIGIN, **headers})


def test_password_hash_round_trip_and_format():
    password = generate_password()
    encoded = hash_password(password)
    assert encoded.startswith("scrypt$15$8$1$") and password not in encoded
    parse_password_hash(encoded)
    assert verify_password(password, encoded)
    assert not verify_password(password + "x", encoded)
    assert not verify_password(password, "not-a-hash")
    assert hash_password(password) != encoded  # salted
    with pytest.raises(ValueError):
        hash_password("short")


def test_hash_password_cli_generates_a_verifiable_pair(capsys):
    assert chat_main(["hash-password", "--generate"]) == 0
    lines = dict(line.split(": ", 1) for line in capsys.readouterr().out.strip().splitlines())
    assert verify_password(lines["password"], lines["password_hash"])


def test_login_session_logout_and_strict_cors(tmp_path: Path):
    password = generate_password()
    app, client = _password_app(tmp_path, {"owner": hash_password(password)})
    preflight = client.options(
        "/api/chat/login",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGIN
    health = client.get("/api/chat/health", headers={"Origin": ORIGIN})
    assert health.json()["auth"] == "password"
    assert client.get("/api/chat/health", headers={"Origin": "https://evil.example"}).status_code == 403

    missing = client.post("/api/chat/conversations", headers={"Origin": ORIGIN})
    assert missing.status_code == 401
    assert missing.headers["access-control-allow-origin"] == ORIGIN
    assert _login(client, "wrong-password-123").status_code == 401

    login = _login(client, password)
    assert login.status_code == 200, login.text
    session = login.json()["session"]
    auth = {"Authorization": f"Bearer {session}", "Origin": ORIGIN}
    created = client.post("/api/chat/conversations", headers=auth)
    assert created.status_code == 201
    assert client.get(f"/api/chat/conversations/{created.json()['id']}", headers=auth).status_code == 200

    db_bytes = (tmp_path / "chat.sqlite3").read_bytes()
    wal = tmp_path / "chat.sqlite3-wal"
    stored = db_bytes + (wal.read_bytes() if wal.exists() else b"")
    assert password.encode() not in stored and session.encode() not in stored

    assert client.post("/api/chat/logout", headers=auth).status_code == 204
    assert client.post("/api/chat/conversations", headers=auth).status_code == 401


def test_sessions_are_owner_isolated_and_die_on_rotation_or_expiry(tmp_path: Path):
    alice_pw, bob_pw = generate_password(), generate_password()
    users = {"alice": hash_password(alice_pw), "bob": hash_password(bob_pw)}
    app, client = _password_app(tmp_path, users)
    alice = {"Authorization": f"Bearer {_login(client, alice_pw).json()['session']}"}
    bob = {"Authorization": f"Bearer {_login(client, bob_pw).json()['session']}"}
    conversation_id = client.post("/api/chat/conversations", headers=alice).json()["id"]
    assert client.get(f"/api/chat/conversations/{conversation_id}", headers=bob).status_code == 404

    # Rotating alice's hash invalidates her existing session on the same state.
    _, rotated = _password_app(tmp_path, {**users, "alice": hash_password(generate_password())})
    assert rotated.post("/api/chat/conversations", headers=alice).status_code == 401
    assert rotated.post("/api/chat/conversations", headers=bob).status_code == 201

    store = app.state.chat_store
    with store._connect() as db:
        db.execute("UPDATE chat_sessions SET expires_at='2000-01-01T00:00:00.000+00:00'")
    assert client.post("/api/chat/conversations", headers=bob).status_code == 401


def test_failed_logins_are_throttled_per_client(tmp_path: Path):
    password = generate_password()
    _, client = _password_app(tmp_path, {"owner": hash_password(password)}, trusted_proxies=("127.0.0.1",))
    attacker = {"X-Forwarded-For": "203.0.113.9"}
    for _ in range(5):
        assert _login(client, "wrong-password-123", **attacker).status_code == 401
    blocked = _login(client, password, **attacker)
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    # Another client behind the same trusted proxy is unaffected.
    assert _login(client, password, **{"X-Forwarded-For": "198.51.100.7"}).status_code == 200


def test_failures_from_many_addresses_never_lock_out_the_owner(tmp_path: Path):
    password = generate_password()
    _, client = _password_app(
        tmp_path,
        {"owner": hash_password(password)},
        trusted_proxies=("127.0.0.1",),
        login_max_failures_global=5,
    )
    for index in range(8):
        response = _login(client, "wrong-password-123", **{"X-Forwarded-For": f"203.0.113.{index}"})
        assert response.status_code == 401
    assert _login(client, password, **{"X-Forwarded-For": "198.51.100.7"}).status_code == 200


def test_concurrent_wrong_logins_cannot_exceed_the_per_client_limit(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor

    password = generate_password()
    _, client = _password_app(
        tmp_path,
        {"owner": hash_password(password)},
        trusted_proxies=("127.0.0.1",),
        login_max_failures_per_client=3,
    )
    attacker = {"X-Forwarded-For": "203.0.113.9"}
    with ThreadPoolExecutor(max_workers=12) as pool:
        codes = list(
            pool.map(lambda _: _login(client, "wrong-password-123", **attacker).status_code, range(12))
        )
    assert codes.count(401) == 3 and codes.count(429) == 9


def test_successful_login_does_not_consume_the_failure_budget(tmp_path: Path):
    password = generate_password()
    _, client = _password_app(
        tmp_path,
        {"owner": hash_password(password)},
        trusted_proxies=("127.0.0.1",),
        login_max_failures_per_client=2,
    )
    owner = {"X-Forwarded-For": "198.51.100.7"}
    for _ in range(4):
        assert _login(client, password, **owner).status_code == 200


def test_no_content_responses_have_no_body(tmp_path: Path):
    password = generate_password()
    _, client = _password_app(tmp_path, {"owner": hash_password(password)})
    auth = {"Authorization": f"Bearer {_login(client, password).json()['session']}", "Origin": ORIGIN}
    conversation_id = client.post("/api/chat/conversations", headers=auth).json()["id"]
    deleted = client.delete(f"/api/chat/conversations/{conversation_id}", headers=auth)
    assert deleted.status_code == 204 and deleted.content == b""
    assert deleted.headers.get("content-length", "0") == "0"
    logout = client.post("/api/chat/logout", headers=auth)
    assert logout.status_code == 204 and logout.content == b""


def test_client_address_trusts_forwarded_for_only_from_configured_proxy():
    assert client_address("10.0.0.5", "203.0.113.9", ()) == "10.0.0.5"
    assert client_address("10.0.0.5", "1.1.1.1, 203.0.113.9", ("10.0.0.5",)) == "203.0.113.9"
    assert client_address("10.0.0.5", "garbage", ("10.0.0.5",)) == "10.0.0.5"


def test_local_mode_rejects_non_loopback_origin_host_and_proxies(tmp_path: Path):
    config = ChatConfig(state_path=tmp_path / "chat.sqlite3")
    app = create_app(config, snapshot=Snapshot(), provider=object(), start_worker=False)
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/api/chat/health", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/chat/health", headers={"Host": "outside.example"}).status_code == 403
    # A default reverse proxy keeps a loopback peer and Host; it must not open the API.
    proxied = TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000))
    response = proxied.post("/api/chat/conversations", headers={"X-Forwarded-For": "203.0.113.9"})
    assert response.status_code == 403
    assert proxied.post("/api/chat/conversations").status_code == 201


def test_post_bodies_must_declare_their_length(tmp_path: Path):
    config = ChatConfig(state_path=tmp_path / "chat.sqlite3")
    app = create_app(config, snapshot=Snapshot(), provider=object(), start_worker=False)
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

    def chunks():
        yield b"{}"

    assert client.post("/api/chat/conversations", content=chunks()).status_code == 411


def test_config_requires_password_mode_for_openai(monkeypatch: pytest.MonkeyPatch):
    for name in list(__import__("os").environ):
        if name.startswith("CHAT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_OPENAI_ENABLED", "true")
    monkeypatch.setenv("CHAT_MODEL", "test-model")
    monkeypatch.setenv("CHAT_INPUT_COST_PER_MILLION", "1")
    monkeypatch.setenv("CHAT_OUTPUT_COST_PER_MILLION", "2")
    with pytest.raises(ValueError, match="CHAT_AUTH_MODE=password"):
        ChatConfig.from_env()
    monkeypatch.setenv("CHAT_ALLOW_LOCAL_OPENAI", "true")
    assert ChatConfig.from_env().auth_mode == "local"

    monkeypatch.setenv("CHAT_AUTH_MODE", "password")
    with pytest.raises(ValueError, match="CHAT_PASSWORDS_JSON"):
        ChatConfig.from_env()
    monkeypatch.setenv("CHAT_PASSWORDS_JSON", json.dumps([{"user_id": "owner", "password_hash": "plain"}]))
    with pytest.raises(ValueError, match="scrypt"):
        ChatConfig.from_env()
    encoded = hash_password(generate_password())
    monkeypatch.setenv("CHAT_PASSWORDS_JSON", json.dumps([{"user_id": "owner", "password_hash": encoded}]))
    with pytest.raises(ValueError, match="CHAT_ALLOWED_ORIGINS"):
        ChatConfig.from_env()
    monkeypatch.setenv("CHAT_ALLOWED_ORIGINS", ORIGIN)
    config = ChatConfig.from_env()
    assert config.password_users == {"owner": encoded}
