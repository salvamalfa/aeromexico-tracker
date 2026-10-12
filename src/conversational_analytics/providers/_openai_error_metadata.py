"""Allowlisted metadata for diagnosing provider failures without retaining payloads."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

SAFE_UPSTREAM_EXCEPTION_TYPES = frozenset(
    {
        "APIConnectionError",
        "APIError",
        "APIStatusError",
        "APITimeoutError",
        "AuthenticationError",
        "BadRequestError",
        "ConflictError",
        "ConnectionError",
        "InternalServerError",
        "NotFoundError",
        "OSError",
        "PermissionDeniedError",
        "RateLimitError",
        "TimeoutError",
        "UnprocessableEntityError",
    }
)
SAFE_UPSTREAM_HTTP_STATUSES = frozenset(
    {400, 401, 403, 404, 408, 409, 413, 422, 425, 429, 500, 502, 503, 504}
)
SAFE_UPSTREAM_ERROR_CODES = frozenset(
    {
        "authentication_error",
        "conflict",
        "context_length_exceeded",
        "insufficient_quota",
        "invalid_request_error",
        "internal_error",
        "model_not_found",
        "not_found",
        "permission_error",
        "rate_limit_exceeded",
        "request_timeout",
        "server_error",
        "temporarily_unavailable",
        "unsupported_value",
    }
)
SAFE_UPSTREAM_ERROR_TYPES = frozenset(
    {"invalid_request_error", "authentication_error", "permission_error", "rate_limit_error", "server_error"}
)
_SAFE_ERROR_PARAM = re.compile(r"^[A-Za-z0-9_.\[\]-]{1,160}$")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_ERROR_PARAM_ROOTS = frozenset(
    {"agent", "model", "instructions", "tools", "reasoning", "text", "input", "metadata"}
)


def sanitize_upstream_fields(
    exception_type: Any = None,
    status: Any = None,
    code: Any = None,
    error_type: Any = None,
    param: Any = None,
    request_id: Any = None,
) -> dict[str, str | int]:
    result: dict[str, str | int] = {}
    if isinstance(exception_type, str) and exception_type in SAFE_UPSTREAM_EXCEPTION_TYPES:
        result["upstream_exception_type"] = exception_type
    if isinstance(status, int) and not isinstance(status, bool) and status in SAFE_UPSTREAM_HTTP_STATUSES:
        result["upstream_http_status"] = status
    if isinstance(code, str) and code in SAFE_UPSTREAM_ERROR_CODES:
        result["upstream_error_code"] = code
    if isinstance(error_type, str) and error_type in SAFE_UPSTREAM_ERROR_TYPES:
        result["upstream_error_type"] = error_type
    if (
        isinstance(param, str)
        and _SAFE_ERROR_PARAM.fullmatch(param)
        and param.split(".", 1)[0].split("[", 1)[0] in _SAFE_ERROR_PARAM_ROOTS
    ):
        result["upstream_error_param"] = param
    if isinstance(request_id, str) and _SAFE_REQUEST_ID.fullmatch(request_id):
        result["upstream_request_id"] = request_id
    return result


def upstream_error_metadata(error: BaseException) -> dict[str, str | int]:
    """Extract only recognized SDK class, HTTP status, and API error code fields."""
    exception_type = getattr(error, "upstream_exception_type", None) or type(error).__name__
    status = getattr(error, "upstream_http_status", None)
    if status is None:
        status = getattr(error, "status_code", None)
    code = getattr(error, "upstream_error_code", None) or getattr(error, "code", None)
    error_type = getattr(error, "upstream_error_type", None)
    param = getattr(error, "upstream_error_param", None)
    request_id = getattr(error, "request_id", None)
    if request_id is None:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None)
        if isinstance(headers, Mapping):
            request_id = headers.get("x-request-id")
    if not isinstance(code, str) or code not in SAFE_UPSTREAM_ERROR_CODES:
        body = getattr(error, "body", None)
        details = body.get("error") if isinstance(body, Mapping) else None
        if isinstance(details, Mapping):
            code = details.get("code")
            error_type = details.get("type", error_type)
            param = details.get("param", param)
    return sanitize_upstream_fields(exception_type, status, code, error_type, param, request_id)
