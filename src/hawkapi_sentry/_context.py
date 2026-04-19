"""Request context helpers for Sentry event enrichment."""

from __future__ import annotations

from typing import Any

_REDACT_HEADER_NAMES = frozenset(
    [
        "authorization",
        "cookie",
        "x-api-key",
        "x-auth-token",
        "proxy-authorization",
    ]
)

_FILTERED = "[Filtered]"


def redact_headers(headers: Any) -> dict[str, str]:
    """Return a dict of headers with sensitive values masked.

    Accepts any iterable of (key, value) pairs or an object with an .items()
    method — covers both HawkAPI Headers (__iter__ yields tuples) and plain dicts.
    """
    result: dict[str, str] = {}
    items: Any = headers.items() if hasattr(headers, "items") else headers
    for key, value in items:
        if key.lower() in _REDACT_HEADER_NAMES:
            result[key] = _FILTERED
        else:
            result[key] = value
    return result


def status_class(status_code: int) -> str:
    """Map an HTTP status code to an OTel/Sentry transaction status string."""
    if status_code < 400:
        return "ok"
    if status_code < 500:
        return "invalid_argument"
    return "internal_error"


def request_context(request: Any) -> dict[str, Any]:
    """Build a Sentry request context dict from a HawkAPI Request."""
    url: str = request.url
    qs_raw: Any = request.query_string
    qs: str = qs_raw.decode("latin-1") if hasattr(qs_raw, "decode") else str(qs_raw)
    return {
        "method": request.method,
        "url": url,
        "headers": redact_headers(request.headers),
        "query_string": qs,
    }


# Keep underscore aliases so tests that import _redact_headers etc. still work
_redact_headers = redact_headers
_status_class = status_class
_request_context = request_context
