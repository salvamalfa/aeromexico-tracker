"""Configuration for the local conversational analytics service.

Configuration is deliberately safe to import without API credentials. The
paid OpenAI provider is opt-in and requires an explicit model name.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

MODEL_CATALOG_PATH = Path(__file__).resolve().parents[2] / "config/chat/models.json"


@lru_cache(maxsize=1)
def model_catalog() -> dict[str, dict[str, object]]:
    """Return versioned model capabilities and prices shipped with the chat image."""
    with MODEL_CATALOG_PATH.open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        raise ValueError("config/chat/models.json must use schema_version 1")
    models = catalog.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("config/chat/models.json must define model capabilities")
    return models


@dataclass(frozen=True)
class ChatConfig:
    state_path: Path = Path.home() / ".local/state/airline-tracker/chat.sqlite3"
    auth_mode: str = "local"
    # user_id -> scrypt hash (see auth.hash_password). Only hashes are configured.
    password_users: dict[str, str] = field(default_factory=dict)
    session_ttl_hours: int = 12
    trusted_proxies: tuple[str, ...] = ()
    login_max_failures_per_client: int = 5
    login_client_window_minutes: int = 15
    # Alert threshold only (logged as an error), never a lockout.
    login_max_failures_global: int = 50
    login_global_window_minutes: int = 60
    allowed_origins: tuple[str, ...] = ()
    provider: str = "mock"
    model: str | None = None
    reasoning_effort: str = "medium"
    text_verbosity: str = "medium"
    openai_enabled: bool = False
    admission_enabled: bool = True
    max_message_chars: int = 8_000
    max_tool_calls: int = 8
    max_tool_result_bytes: int = 16_000
    max_turn_seconds: int = 180
    # Pending plus running turns admitted across all users. One worker thread
    # executes them sequentially; this is a queue bound, not parallelism.
    max_concurrent_global: int = 2
    max_active_per_user: int = 1
    # Spend is capped in dollars; the token caps are only a runaway brake and
    # no longer track the Data Sharing incentive.
    daily_token_budget_user: int = 2_000_000
    daily_token_budget_global: int = 2_000_000
    minimum_turn_reservation_tokens: int = 150_000
    daily_cost_budget_user_usd: float = 1.0
    daily_cost_budget_global_usd: float = 1.0
    estimated_input_cost_per_million: float = 5.0
    estimated_output_cost_per_million: float = 15.0
    long_context_threshold_input_tokens: int = 272_000
    long_context_input_multiplier: float = 2.0
    long_context_output_multiplier: float = 1.5
    cache_write_input_multiplier: float = 1.25
    retention_days: int = 30
    poll_interval_seconds: float = 0.2

    @classmethod
    def from_env(cls) -> "ChatConfig":
        """Read CHAT_* configuration without exposing secret values."""
        state_path = Path(
            os.environ.get("CHAT_STATE_PATH", str(Path.home() / ".local/state/airline-tracker/chat.sqlite3"))
        )
        auth_mode = os.environ.get("CHAT_AUTH_MODE", "local").lower()
        if auth_mode not in {"local", "password"}:
            raise ValueError("CHAT_AUTH_MODE must be 'local' or 'password'")
        users = _password_users(os.environ.get("CHAT_PASSWORDS_JSON", ""))
        if auth_mode == "password" and not users:
            raise ValueError("password mode requires CHAT_PASSWORDS_JSON with scrypt password hashes")
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
        if auth_mode == "password" and not allowed_origins:
            raise ValueError("password mode requires explicit CHAT_ALLOWED_ORIGINS")
        from .auth import parse_trusted_proxy

        try:
            raw_proxies = os.environ.get("CHAT_TRUSTED_PROXY", "").split(",")
            trusted_proxies = tuple(parse_trusted_proxy(v) for v in raw_proxies if v.strip())
        except ValueError as exc:
            raise ValueError(
                "CHAT_TRUSTED_PROXY must list proxy IPs or loopback/private/shared-address CIDR networks"
            ) from exc
        provider = os.environ.get("CHAT_PROVIDER", "mock").lower()
        if provider not in {"mock", "openai"}:
            raise ValueError("CHAT_PROVIDER must be 'mock' or 'openai'")
        model = os.environ.get("CHAT_MODEL") or None
        reasoning_effort = os.environ.get("CHAT_REASONING_EFFORT", "medium").strip().lower()
        text_verbosity = os.environ.get("CHAT_TEXT_VERBOSITY", "medium").strip().lower()
        openai_enabled = os.environ.get("CHAT_OPENAI_ENABLED", "false").lower() in {"1", "true", "yes"}
        if provider == "openai" and (not openai_enabled or not model):
            raise ValueError("OpenAI mode requires CHAT_OPENAI_ENABLED=true and an explicit CHAT_MODEL")
        allow_local_openai = os.environ.get("CHAT_ALLOW_LOCAL_OPENAI", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        if provider == "openai" and auth_mode == "local" and not allow_local_openai:
            raise ValueError(
                "OpenAI mode requires CHAT_AUTH_MODE=password "
                "(CHAT_ALLOW_LOCAL_OPENAI=true only on the owner's machine)"
            )
        if provider == "openai":
            _validate_model_settings(model, reasoning_effort, text_verbosity)
            rates = model_catalog()[model]
            for env_name, key in (
                ("CHAT_INPUT_COST_PER_MILLION", "input_usd_per_million"),
                ("CHAT_OUTPUT_COST_PER_MILLION", "output_usd_per_million"),
            ):
                configured = _env_float(env_name, float(rates[key]))
                if not math.isclose(configured, float(rates[key]), rel_tol=0.0, abs_tol=1e-9):
                    raise ValueError(f"{env_name} must match the versioned price for CHAT_MODEL")
            input_rate = float(rates["input_usd_per_million"])
            output_rate = float(rates["output_usd_per_million"])
            long_context_threshold = int(rates["long_context_threshold_input_tokens"])
            long_context_input_multiplier = float(rates["long_context_input_multiplier"])
            long_context_output_multiplier = float(rates["long_context_output_multiplier"])
            cache_write_input_multiplier = float(rates["cache_write_input_multiplier"])
        else:
            input_rate = _env_float("CHAT_INPUT_COST_PER_MILLION", 5.0)
            output_rate = _env_float("CHAT_OUTPUT_COST_PER_MILLION", 15.0)
            long_context_threshold = 272_000
            long_context_input_multiplier = 2.0
            long_context_output_multiplier = 1.5
            cache_write_input_multiplier = 1.25
        return cls(
            state_path=state_path,
            auth_mode=auth_mode,
            password_users=users,
            session_ttl_hours=_env_int("CHAT_SESSION_TTL_HOURS", 12),
            trusted_proxies=trusted_proxies,
            allowed_origins=allowed_origins,
            provider=provider,
            model=model,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
            openai_enabled=openai_enabled,
            admission_enabled=os.environ.get("CHAT_ADMISSION_ENABLED", "true").lower()
            not in {"0", "false", "no"},
            max_message_chars=_env_int("CHAT_MAX_MESSAGE_CHARS", 8_000),
            max_tool_calls=_env_int("CHAT_MAX_TOOL_CALLS", 8),
            max_tool_result_bytes=_env_int("CHAT_MAX_TOOL_RESULT_BYTES", 16_000),
            max_turn_seconds=_env_int("CHAT_MAX_TURN_SECONDS", 180),
            max_concurrent_global=_env_int("CHAT_MAX_CONCURRENT_GLOBAL", 2),
            max_active_per_user=_env_int("CHAT_MAX_ACTIVE_PER_USER", 1),
            daily_token_budget_user=_env_int("CHAT_DAILY_TOKEN_BUDGET_USER", 2_000_000),
            daily_token_budget_global=_env_int("CHAT_DAILY_TOKEN_BUDGET_GLOBAL", 2_000_000),
            minimum_turn_reservation_tokens=_env_int("CHAT_MINIMUM_TURN_RESERVATION_TOKENS", 150_000),
            daily_cost_budget_user_usd=_env_float("CHAT_DAILY_COST_BUDGET_USER_USD", 1.0),
            daily_cost_budget_global_usd=_env_float("CHAT_DAILY_COST_BUDGET_GLOBAL_USD", 1.0),
            estimated_input_cost_per_million=input_rate,
            estimated_output_cost_per_million=output_rate,
            long_context_threshold_input_tokens=long_context_threshold,
            long_context_input_multiplier=long_context_input_multiplier,
            long_context_output_multiplier=long_context_output_multiplier,
            cache_write_input_multiplier=cache_write_input_multiplier,
            retention_days=_env_int("CHAT_RETENTION_DAYS", 30),
            poll_interval_seconds=_env_float("CHAT_POLL_INTERVAL_SECONDS", 0.2),
        )

    def __post_init__(self) -> None:
        for name in (
            "daily_cost_budget_user_usd",
            "daily_cost_budget_global_usd",
            "estimated_input_cost_per_million",
            "estimated_output_cost_per_million",
            "long_context_input_multiplier",
            "long_context_output_multiplier",
            "cache_write_input_multiplier",
            "poll_interval_seconds",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")

    def validate_admission_budgets(self) -> None:
        """Fail early if one minimum paid turn cannot fit the chat cost quotas."""
        if self.provider != "openai":
            return
        reserve_cost = self.reservation_cost_usd(self.minimum_turn_reservation_tokens)
        for setting, budget in (
            ("CHAT_DAILY_COST_BUDGET_USER_USD", self.daily_cost_budget_user_usd),
            ("CHAT_DAILY_COST_BUDGET_GLOBAL_USD", self.daily_cost_budget_global_usd),
        ):
            if reserve_cost > budget:
                raise ValueError(
                    f"minimum OpenAI turn reservation is estimated at ${reserve_cost:.4f}, "
                    f"above {setting}=${budget:.4f}; use the selected model's verified normal prices "
                    "and configure the chat cost quota to cover this reservation before starting"
                )

    def reservation_cost_usd(self, reserved_tokens: int) -> float:
        """Price a reservation entirely at the higher of the two token rates.

        Agents API sessions accept no output-token limit, so any share of the
        reservation may arrive as output (including reasoning); pricing it all
        at the output rate keeps the hold an upper bound for tokens within it.
        """
        rate = max(
            self.estimated_input_cost_per_million
            * self.long_context_input_multiplier
            * self.cache_write_input_multiplier,
            self.estimated_output_cost_per_million * self.long_context_output_multiplier,
        )
        return reserved_tokens * rate / 1_000_000

    def usage_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        """Estimated spend of confirmed usage; the mock provider never spends."""
        if self.provider != "openai":
            return 0.0
        long_context = input_tokens > self.long_context_threshold_input_tokens
        input_multiplier = self.cache_write_input_multiplier * (
            self.long_context_input_multiplier if long_context else 1.0
        )
        output_multiplier = self.long_context_output_multiplier if long_context else 1.0
        return (
            input_tokens * self.estimated_input_cost_per_million * input_multiplier
            + output_tokens * self.estimated_output_cost_per_million * output_multiplier
        ) / 1_000_000

    def password_fingerprints(self) -> dict[str, str]:
        """Fingerprint per configured user; sessions die when a hash rotates."""
        from .auth import hash_fingerprint

        return {user_id: hash_fingerprint(encoded) for user_id, encoded in self.password_users.items()}


def _password_users(raw: str) -> dict[str, str]:
    from .auth import parse_password_hash

    if not raw:
        return {}
    users: dict[str, str] = {}
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            raise ValueError
        for entry in entries:
            user_id, encoded = entry["user_id"], entry["password_hash"]
            if not isinstance(user_id, str) or not user_id or len(user_id) > 64 or user_id in users:
                raise ValueError
            parse_password_hash(encoded)
            users[user_id] = encoded
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("CHAT_PASSWORDS_JSON must contain user_id and scrypt password_hash entries") from exc
    return users


def _validate_model_settings(model: str | None, effort: str, verbosity: str) -> None:
    if not model:
        raise ValueError("OpenAI mode requires an explicit CHAT_MODEL")
    entry = model_catalog().get(model)
    if entry is None:
        raise ValueError("CHAT_MODEL must be listed in config/chat/models.json")
    efforts = entry.get("reasoning_efforts")
    if not isinstance(efforts, list) or effort not in efforts:
        allowed = ", ".join(efforts) if isinstance(efforts, list) else "none"
        raise ValueError(f"CHAT_REASONING_EFFORT for {model} must be one of: {allowed}")
    levels = entry.get("text_verbosity")
    if not isinstance(levels, list) or verbosity not in levels:
        allowed = ", ".join(levels) if isinstance(levels, list) else "none"
        raise ValueError(f"CHAT_TEXT_VERBOSITY for {model} must be one of: {allowed}")


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
