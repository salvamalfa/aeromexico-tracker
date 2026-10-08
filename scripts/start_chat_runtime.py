"""Start the hosted chat API with a public snapshot and safe pilot defaults."""

from __future__ import annotations

import copy
import logging
import os
import stat
import tempfile
from pathlib import Path

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers._openai_helpers import (
    TERMINAL_USAGE_RECONCILIATION_SECONDS,
)

RAILWAY_EDGE_NETWORK = "100.64.0.0/10"
RAILWAY_DRAIN_SECONDS = 230
UVICORN_CONNECTION_DRAIN_SECONDS = 5
PROVIDER_EXECUTION_MAX_SECONDS = 180
USAGE_RECONCILIATION_SECONDS = int(TERMINAL_USAGE_RECONCILIATION_SECONDS)
LOCAL_FINALIZATION_SECONDS = 10
WORKER_DRAIN_SECONDS = (
    PROVIDER_EXECUTION_MAX_SECONDS
    + USAGE_RECONCILIATION_SECONDS
    + LOCAL_FINALIZATION_SECONDS
)
RAILWAY_SHUTDOWN_MARGIN_SECONDS = 5


def worker_drain_seconds(config: ChatConfig) -> int:
    """Bound worker shutdown by execution, usage reconciliation, and finalization."""
    if config.max_turn_seconds > PROVIDER_EXECUTION_MAX_SECONDS:
        raise ValueError(
            "Hosted CHAT_MAX_TURN_SECONDS cannot exceed "
            f"{PROVIDER_EXECUTION_MAX_SECONDS} seconds"
        )
    return (
        config.max_turn_seconds
        + USAGE_RECONCILIATION_SECONDS
        + LOCAL_FINALIZATION_SECONDS
    )


def required_railway_drain_seconds(config: ChatConfig) -> int:
    """Return the host drain required around Uvicorn and worker shutdown."""
    return (
        UVICORN_CONNECTION_DRAIN_SECONDS
        + worker_drain_seconds(config)
        + RAILWAY_SHUTDOWN_MARGIN_SECONDS
    )


def split_stream_log_config(base: dict) -> dict:
    """Send Uvicorn's INFO lines to stdout and keep warnings and errors on stderr.

    Railway labels every stderr line as an error, so the default config made
    routine startup and shutdown messages look like failures.
    """
    config = copy.deepcopy(base)
    handlers = config["handlers"]
    handlers["errors"] = {**handlers["default"], "stream": "ext://sys.stderr", "level": "WARNING"}
    handlers["default"] = {
        **handlers["default"],
        "stream": "ext://sys.stdout",
        "filters": [lambda record: record.levelno < logging.WARNING],
    }
    config["loggers"]["uvicorn"]["handlers"] = ["default", "errors"]
    return config


def create_shutdown_aware_server(uvicorn, app, *, host: str, port: int):
    """Start claim draining on SIGTERM, before Uvicorn waits on SSE requests."""
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        proxy_headers=False,
        timeout_graceful_shutdown=UVICORN_CONNECTION_DRAIN_SECONDS,
        log_config=split_stream_log_config(uvicorn.config.LOGGING_CONFIG),
    )

    class ShutdownAwareServer(uvicorn.Server):
        async def shutdown(self, sockets=None):
            app.state.begin_shutdown()
            await super().shutdown(sockets=sockets)

    return ShutdownAwareServer(config)


def runtime_config(*, volume_path: Path = Path("/data")) -> tuple[ChatConfig, int]:
    os.environ.setdefault("CHAT_STATE_PATH", "/data/chat.sqlite3")
    os.environ.setdefault("CHAT_PROVIDER", "mock")
    os.environ.setdefault("CHAT_ADMISSION_ENABLED", "false")
    os.environ.setdefault("CHAT_RETENTION_DAYS", "30")
    # Railway's edge reaches the container from the shared address space
    # (RFC 6598) and is its only ingress. Without trusting it, every client
    # shares the edge address and five wrong passwords lock out the owner.
    os.environ.setdefault("CHAT_TRUSTED_PROXY", RAILWAY_EDGE_NETWORK)

    port_raw = os.environ.get("PORT", "8080")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535")

    config = ChatConfig.from_env()
    if config.max_turn_seconds > PROVIDER_EXECUTION_MAX_SECONDS:
        raise ValueError(
            "Hosted CHAT_MAX_TURN_SECONDS cannot exceed "
            f"{PROVIDER_EXECUTION_MAX_SECONDS} seconds"
        )
    required_drain = required_railway_drain_seconds(config)
    if required_drain > RAILWAY_DRAIN_SECONDS:
        raise ValueError(
            "Hosted CHAT_MAX_TURN_SECONDS requires at least "
            f"{required_drain} seconds of Railway deployment draining; "
            f"configured launcher budget is {RAILWAY_DRAIN_SECONDS} seconds"
        )
    if config.auth_mode != "password":
        raise ValueError("Hosted chat requires CHAT_AUTH_MODE=password")
    if len(config.password_users) != 1:
        raise ValueError("Hosted single-owner chat requires exactly one configured password user")
    # The defaults above keep a fresh service on mock with admission closed.
    # Enabling OpenAI is an explicit Railway configuration: ChatConfig.from_env
    # already requires CHAT_OPENAI_ENABLED, CHAT_MODEL, normal prices and
    # password auth, and create_app checks that one reservation fits the
    # daily dollar caps.
    config.validate_admission_budgets()
    if config.retention_days != 30:
        raise ValueError("Hosted pilot uses the approved 30-day retention period")

    state_path = config.state_path.resolve()
    volume_path = volume_path.resolve()
    if not state_path.is_relative_to(volume_path):
        raise ValueError("CHAT_STATE_PATH must be inside the persistent /data volume")
    try:
        volume_path.mkdir(parents=True, exist_ok=True)
        volume_path.chmod(0o700)
        state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        state_path.parent.chmod(0o700)
        with tempfile.NamedTemporaryFile(prefix=".chat-write-check-", dir=state_path.parent):
            pass
    except OSError as exc:
        raise RuntimeError("Persistent /data volume must be writable by the container runtime") from exc

    return config, port


def secure_existing_sqlite_files(state_path: Path) -> None:
    """Restrict an existing DB and sidecars before SQLite opens them."""
    for path in (state_path, Path(f"{state_path}-wal"), Path(f"{state_path}-shm")):
        try:
            if path.is_file():
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError as exc:
            raise RuntimeError("Could not restrict permissions on existing chat database files") from exc


def main() -> None:
    import uvicorn

    from src.conversational_analytics.api import create_app

    config, port = runtime_config()
    # SQLite database, journal, and WAL files contain private chat state.
    os.umask(0o077)
    secure_existing_sqlite_files(config.state_path)
    app = create_app(
        config,
        worker_shutdown_timeout_seconds=worker_drain_seconds(config),
    )
    server = create_shutdown_aware_server(uvicorn, app, host="0.0.0.0", port=port)
    server.run()


if __name__ == "__main__":
    main()
