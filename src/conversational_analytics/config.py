"""Configuration for the local conversational analytics service.

Configuration is deliberately safe to import without API credentials. The
paid OpenAI provider is opt-in and requires an explicit model name.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ChatConfig:
    state_path: Path = Path.home() / ".local/state/airline-tracker/chat.sqlite3"
    auth_mode: str = "local"
    bearer_users: dict[str, str] = field(default_factory=dict)
    allowed_origins: tuple[str, ...] = ()
    provider: str = "mock"
    model: str | None = None
    openai_enabled: bool = False
    admission_enabled: bool = True
    max_message_chars: int = 8_000
    max_tool_calls: int = 4
    max_tool_result_bytes: int = 16_000
    max_turn_seconds: int = 90
    max_concurrent_global: int = 2
    max_active_per_user: int = 1
    daily_token_budget_user: int = 100_000
    daily_token_budget_global: int = 500_000
    daily_cost_budget_user_usd: float = 2.0
    daily_cost_budget_global_usd: float = 10.0
    estimated_input_cost_per_million: float = 5.0
    estimated_output_cost_per_million: float = 15.0
    retention_days: int = 30
    poll_interval_seconds: float = 0.2

    @classmethod
    def from_env(cls) -> "ChatConfig":
        """Read CHAT_* configuration without exposing secret values."""
        state_path = Path(
            os.environ.get("CHAT_STATE_PATH", str(Path.home() / ".local/state/airline-tracker/chat.sqlite3"))
        )
        auth_mode = os.environ.get("CHAT_AUTH_MODE", "local").lower()
        if auth_mode not in {"local", "bearer"}:
            raise ValueError("CHAT_AUTH_MODE must be 'local' or 'bearer'")
        users: dict[str, str] = {}
        raw_users = os.environ.get("CHAT_USERS_JSON", "")
        if raw_users:
            try:
                entries = json.loads(raw_users)
                if not isinstance(entries, list):
                    raise ValueError
                for entry in entries:
                    user_id, token_hash = entry["user_id"], entry["token_sha256"]
                    if not isinstance(user_id, str) or not user_id or len(token_hash) != 64:
                        raise ValueError
                    bytes.fromhex(token_hash)
                    users[token_hash.lower()] = user_id
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise ValueError("CHAT_USERS_JSON must contain user_id and token_sha256 entries") from exc
        if auth_mode == "bearer" and not users:
            raise ValueError("bearer mode requires CHAT_USERS_JSON with SHA-256 token hashes")
        allowed_origins = tuple(
            v.strip().rstrip("/") for v in os.environ.get("CHAT_ALLOWED_ORIGINS", "").split(",") if v.strip()
        )
        for origin in allowed_origins:
            parsed_origin = urlsplit(origin)
            if (
                parsed_origin.scheme != "https"
                or not parsed_origin.hostname
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
                or parsed_origin.username
                or parsed_origin.password
            ):
                raise ValueError("CHAT_ALLOWED_ORIGINS must contain HTTPS origins without paths")
        if auth_mode == "bearer" and not allowed_origins:
            raise ValueError("bearer mode requires explicit CHAT_ALLOWED_ORIGINS")
        provider = os.environ.get("CHAT_PROVIDER", "mock").lower()
        if provider not in {"mock", "openai"}:
            raise ValueError("CHAT_PROVIDER must be 'mock' or 'openai'")
        model = os.environ.get("CHAT_MODEL") or None
        openai_enabled = os.environ.get("CHAT_OPENAI_ENABLED", "false").lower() in {"1", "true", "yes"}
        if provider == "openai" and (not openai_enabled or not model):
            raise ValueError("OpenAI mode requires CHAT_OPENAI_ENABLED=true and an explicit CHAT_MODEL")
        if (
            provider == "openai"
            and not {"CHAT_INPUT_COST_PER_MILLION", "CHAT_OUTPUT_COST_PER_MILLION"} <= os.environ.keys()
        ):
            raise ValueError(
                "OpenAI mode requires explicit per-million token prices for conservative cost quotas"
            )
        return cls(
            state_path=state_path,
            auth_mode=auth_mode,
            bearer_users=users,
            allowed_origins=allowed_origins,
            provider=provider,
            model=model,
            openai_enabled=openai_enabled,
            admission_enabled=os.environ.get("CHAT_ADMISSION_ENABLED", "true").lower()
            not in {"0", "false", "no"},
            max_message_chars=_env_int("CHAT_MAX_MESSAGE_CHARS", 8_000),
            max_tool_calls=_env_int("CHAT_MAX_TOOL_CALLS", 4),
            max_tool_result_bytes=_env_int("CHAT_MAX_TOOL_RESULT_BYTES", 16_000),
            max_turn_seconds=_env_int("CHAT_MAX_TURN_SECONDS", 90),
            max_concurrent_global=_env_int("CHAT_MAX_CONCURRENT_GLOBAL", 2),
            max_active_per_user=_env_int("CHAT_MAX_ACTIVE_PER_USER", 1),
            daily_token_budget_user=_env_int("CHAT_DAILY_TOKEN_BUDGET_USER", 100_000),
            daily_token_budget_global=_env_int("CHAT_DAILY_TOKEN_BUDGET_GLOBAL", 500_000),
            daily_cost_budget_user_usd=_env_float("CHAT_DAILY_COST_BUDGET_USER_USD", 2.0),
            daily_cost_budget_global_usd=_env_float("CHAT_DAILY_COST_BUDGET_GLOBAL_USD", 10.0),
            estimated_input_cost_per_million=_env_float("CHAT_INPUT_COST_PER_MILLION", 5.0),
            estimated_output_cost_per_million=_env_float("CHAT_OUTPUT_COST_PER_MILLION", 15.0),
            retention_days=_env_int("CHAT_RETENTION_DAYS", 30),
            poll_interval_seconds=_env_float("CHAT_POLL_INTERVAL_SECONDS", 0.2),
        )

    def __post_init__(self) -> None:
        for name in (
            "daily_cost_budget_user_usd",
            "daily_cost_budget_global_usd",
            "estimated_input_cost_per_million",
            "estimated_output_cost_per_million",
            "poll_interval_seconds",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")

    def owner_for_token(self, token: str) -> str | None:
        """Resolve a configured bearer token without storing or logging it."""
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        # Compare every configured digest in constant time.
        import hmac

        for configured_hash, user_id in self.bearer_users.items():
            if hmac.compare_digest(configured_hash, digest):
                return user_id
        return None


def _env_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _env_float(name: str, default: float) -> float:
    value = float(os.environ.get(name, str(default)))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value
