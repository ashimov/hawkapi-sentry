"""Tests for SentryPlugin lifecycle and exception-capture behaviour."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from hawkapi_sentry._plugin import SentryPlugin
from tests.conftest import CapturingTransport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeHeaders:
    def __init__(self, data: dict[str, str] | None = None) -> None:
        self._data = data or {}

    def items(self) -> list[tuple[str, str]]:
        return list(self._data.items())

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._data.get(key, default)


class _FakeState:
    pass


class _FakeRequest:
    def __init__(
        self,
        method: str = "GET",
        url: str = "http://localhost/test",
        headers: dict[str, str] | None = None,
        state_attrs: dict[str, Any] | None = None,
    ) -> None:
        self.method = method
        self.url = url
        self.headers = _FakeHeaders(headers or {})
        self.query_string = b""
        self.state = _FakeState()
        for k, v in (state_attrs or {}).items():
            setattr(self.state, k, v)


class _SpyScope:
    """Minimal scope spy that records set_user and set_tag calls."""

    def __init__(self) -> None:
        self.user: dict[str, Any] | None = None
        self.tags: dict[str, str] = {}
        self.contexts: dict[str, Any] = {}

    def __enter__(self) -> _SpyScope:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_context(self, key: str, value: Any) -> None:
        self.contexts[key] = value

    def set_user(self, user: Any) -> None:
        self.user = user

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value


# ---------------------------------------------------------------------------
# Tests: no-op mode
# ---------------------------------------------------------------------------


def test_noop_when_dsn_empty() -> None:
    """on_startup does NOT call sentry_sdk.init when dsn is empty."""
    plugin = SentryPlugin(dsn="")
    with patch("sentry_sdk.init") as mock_init:
        plugin.on_startup()
        mock_init.assert_not_called()


def test_noop_when_dsn_none() -> None:
    """on_startup does NOT call sentry_sdk.init when dsn is None."""
    plugin = SentryPlugin(dsn=None)
    with patch("sentry_sdk.init") as mock_init:
        plugin.on_startup()
        mock_init.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: init called with DSN
# ---------------------------------------------------------------------------


def test_init_called_with_dsn(capturing_transport: CapturingTransport) -> None:
    """on_startup calls sentry_sdk.init when dsn is provided."""
    plugin = SentryPlugin(dsn="http://fake@localhost/1", transport=capturing_transport)
    plugin.on_startup()
    assert plugin._initialised is True


# ---------------------------------------------------------------------------
# Tests: on_exception captures events
# ---------------------------------------------------------------------------


def test_on_exception_captures_non_http(capturing_transport: CapturingTransport) -> None:
    """on_exception captures a plain Exception into Sentry."""
    plugin = SentryPlugin(dsn="http://fake@localhost/1", transport=capturing_transport)
    plugin.on_startup()
    plugin.on_exception(_FakeRequest(), ValueError("boom"))
    assert len(capturing_transport.captured) > 0


def test_on_exception_ignores_404(capturing_transport: CapturingTransport) -> None:
    """on_exception skips capture when status_code is in ignore_status_codes."""
    plugin = SentryPlugin(
        dsn="http://fake@localhost/1",
        transport=capturing_transport,
        ignore_status_codes=(404, 401, 403),
    )
    plugin.on_startup()

    exc: Any = Exception("not found")
    exc.status_code = 404
    plugin.on_exception(_FakeRequest(), exc)

    assert len(capturing_transport.captured) == 0


def test_on_exception_captures_500(capturing_transport: CapturingTransport) -> None:
    """on_exception captures when status is 500 (not in default ignore list)."""
    plugin = SentryPlugin(dsn="http://fake@localhost/1", transport=capturing_transport)
    plugin.on_startup()

    exc: Any = Exception("server error")
    exc.status_code = 500
    plugin.on_exception(_FakeRequest(), exc)

    assert len(capturing_transport.captured) > 0


# ---------------------------------------------------------------------------
# Tests: request context attached
# ---------------------------------------------------------------------------


def test_request_context_attached(capturing_transport: CapturingTransport) -> None:
    """Request method, url, and redacted headers are set on the scope."""
    plugin = SentryPlugin(dsn="http://fake@localhost/1", transport=capturing_transport)
    plugin.on_startup()

    spy = _SpyScope()
    req = _FakeRequest(
        method="POST",
        url="http://localhost/login",
        headers={"authorization": "Bearer tok", "content-type": "application/json"},
    )

    with patch("sentry_sdk.new_scope", return_value=spy), patch("sentry_sdk.capture_exception"):
        plugin.on_exception(req, ValueError("x"))

    assert spy.contexts.get("request", {}).get("method") == "POST"
    assert spy.contexts.get("request", {}).get("headers", {}).get("authorization") == "[Filtered]"


# ---------------------------------------------------------------------------
# Tests: user context
# ---------------------------------------------------------------------------


def test_user_getter_called(capturing_transport: CapturingTransport) -> None:
    """user_getter return value is attached as user context."""
    user_info: dict[str, Any] = {"id": "42", "email": "user@example.com"}
    plugin = SentryPlugin(
        dsn="http://fake@localhost/1",
        transport=capturing_transport,
        user_getter=lambda _req: user_info,
    )
    plugin.on_startup()

    spy = _SpyScope()
    with patch("sentry_sdk.new_scope", return_value=spy), patch("sentry_sdk.capture_exception"):
        plugin.on_exception(_FakeRequest(), ValueError("x"))

    assert spy.user == user_info


def test_include_user_data_from_state(capturing_transport: CapturingTransport) -> None:
    """include_user_data=True reads request.state.user dict."""
    plugin = SentryPlugin(
        dsn="http://fake@localhost/1",
        transport=capturing_transport,
        include_user_data=True,
    )
    plugin.on_startup()

    spy = _SpyScope()
    req = _FakeRequest(state_attrs={"user": {"id": "99", "name": "Alice"}})

    with patch("sentry_sdk.new_scope", return_value=spy), patch("sentry_sdk.capture_exception"):
        plugin.on_exception(req, ValueError("y"))

    assert spy.user == {"id": "99", "name": "Alice"}


# ---------------------------------------------------------------------------
# Tests: global tags
# ---------------------------------------------------------------------------


def test_global_tags_attached(capturing_transport: CapturingTransport) -> None:
    """tags dict is applied to every captured event scope."""
    plugin = SentryPlugin(
        dsn="http://fake@localhost/1",
        transport=capturing_transport,
        tags={"service": "api", "region": "eu-west-1"},
    )
    plugin.on_startup()

    spy = _SpyScope()
    with patch("sentry_sdk.new_scope", return_value=spy), patch("sentry_sdk.capture_exception"):
        plugin.on_exception(_FakeRequest(), ValueError("z"))

    assert spy.tags.get("service") == "api"
    assert spy.tags.get("region") == "eu-west-1"


# ---------------------------------------------------------------------------
# Tests: on_shutdown
# ---------------------------------------------------------------------------


def test_on_shutdown_flushes() -> None:
    """on_shutdown calls sentry_sdk.flush."""
    plugin = SentryPlugin(dsn=None)
    with patch("sentry_sdk.flush") as mock_flush:
        plugin.on_shutdown()
        mock_flush.assert_called_once_with(timeout=2.0)


# ---------------------------------------------------------------------------
# Tests: before_send filter
# ---------------------------------------------------------------------------


def test_before_send_blocks_events(capturing_transport: CapturingTransport) -> None:
    """before_send returning None suppresses all events."""
    plugin = SentryPlugin(
        dsn="http://fake@localhost/1",
        transport=capturing_transport,
        before_send=lambda event, hint: None,
    )
    plugin.on_startup()
    plugin.on_exception(_FakeRequest(), ValueError("filtered"))
    assert len(capturing_transport.captured) == 0
