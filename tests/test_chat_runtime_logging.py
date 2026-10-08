"""Uvicorn's routine lines must not reach Railway as errors."""

from __future__ import annotations

import io
import logging
import logging.config
import sys

import pytest

uvicorn_config = pytest.importorskip("uvicorn.config")

from scripts.start_chat_runtime import split_stream_log_config


def test_uvicorn_info_goes_to_stdout_and_errors_stay_on_stderr(monkeypatch):
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    logger = logging.getLogger("uvicorn.error")
    saved = {name: logging.getLogger(name).handlers[:] for name in ("uvicorn", "uvicorn.access")}
    try:
        logging.config.dictConfig(split_stream_log_config(uvicorn_config.LOGGING_CONFIG))
        logger.info("Application startup complete.")
        logger.error("Exception in ASGI application")
    finally:
        for name, handlers in saved.items():
            logging.getLogger(name).handlers = handlers

    assert "Application startup complete." in stdout.getvalue()
    assert "Application startup complete." not in stderr.getvalue()
    assert "Exception in ASGI application" in stderr.getvalue()
    assert "Exception in ASGI application" not in stdout.getvalue()


def test_split_config_leaves_uvicorn_defaults_untouched():
    before = repr(uvicorn_config.LOGGING_CONFIG)
    split_stream_log_config(uvicorn_config.LOGGING_CONFIG)
    assert repr(uvicorn_config.LOGGING_CONFIG) == before
