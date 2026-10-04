"""Deployment-entrypoint safety checks without starting a server or provider."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from scripts.start_chat_runtime import runtime_config, secure_existing_sqlite_files
from src.conversational_analytics.auth import hash_password


def _configure(monkeypatch, volume: Path) -> None:
    password_hash = hash_password("railway-pilot-password")
    values = {
        "CHAT_AUTH_MODE": "password",
        "CHAT_PASSWORDS_JSON": json.dumps([{"user_id": "owner", "password_hash": password_hash}]),
        "CHAT_ALLOWED_ORIGINS": "https://dashboard.example",
        "CHAT_PROVIDER": "mock",
        "CHAT_ADMISSION_ENABLED": "false",
        "CHAT_RETENTION_DAYS": "30",
        "CHAT_STATE_PATH": str(volume / "chat.sqlite3"),
        "PORT": "8080",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_runtime_config_accepts_single_owner_and_writable_volume(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)

    config, port = runtime_config(volume_path=tmp_path)

    assert port == 8080
    assert config.provider == "mock"
    assert config.auth_mode == "password"
    assert config.admission_enabled is False
    assert config.retention_days == 30
    assert config.state_path == (tmp_path / "chat.sqlite3").resolve()
    assert not list(tmp_path.glob(".chat-write-check-*"))


@pytest.mark.parametrize(
    ("name", "value", "error"),
    [
        ("CHAT_AUTH_MODE", "local", "CHAT_AUTH_MODE=password"),
        ("CHAT_ADMISSION_ENABLED", "true", "CHAT_ADMISSION_ENABLED=false"),
        ("CHAT_RETENTION_DAYS", "31", "approved 30-day retention"),
        ("PORT", "70000", "PORT must be an integer"),
    ],
)
def test_runtime_config_rejects_unsafe_overrides(monkeypatch, tmp_path, name, value, error):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=error):
        runtime_config(volume_path=tmp_path)


def test_runtime_config_rejects_state_outside_persistent_volume(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("CHAT_STATE_PATH", str(tmp_path.parent / "ephemeral.sqlite3"))

    with pytest.raises(ValueError, match="inside the persistent /data volume"):
        runtime_config(volume_path=tmp_path)


def test_runtime_config_rejects_multiple_users(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    password_hash = hash_password("second-pilot-password")
    monkeypatch.setenv(
        "CHAT_PASSWORDS_JSON",
        json.dumps(
            [
                {"user_id": "owner", "password_hash": password_hash},
                {"user_id": "other", "password_hash": password_hash},
            ]
        ),
    )

    with pytest.raises(ValueError, match="exactly one configured password user"):
        runtime_config(volume_path=tmp_path)


def test_existing_database_and_sidecars_are_restricted_before_open(tmp_path):
    database = tmp_path / "chat.sqlite3"
    paths = (database, Path(f"{database}-wal"), Path(f"{database}-shm"))
    for path in paths:
        path.touch()
        path.chmod(0o644)

    secure_existing_sqlite_files(database)

    for path in paths:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
