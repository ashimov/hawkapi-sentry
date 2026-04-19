"""Tests for SentryMiddleware transaction and tag behaviour."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hawkapi_sentry._middleware import SentryMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeHeaders:
    def __init__(self, data: dict[str, str] | None = None) -> None:
        self._data = data or {}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._data.get(key, default)

    def items(self) -> list[tuple[str, str]]:
        return list(self._data.items())


class _FakeState:
    pass


class _FakeRequest:
    def __init__(
        self,
        method: str = "GET",
        path: str = "/items",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.method = method
        self.path = path
        self.headers = _FakeHeaders(headers or {})
        self.state = _FakeState()


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_before_request_starts_transaction() -> None:
    """before_request starts a Sentry transaction and stores it on request.state."""
    mock_tx = MagicMock()
    mock_tx.__enter__ = MagicMock(return_value=mock_tx)
    mock_tx.__exit__ = MagicMock(return_value=False)

    mw = SentryMiddleware(app=MagicMock())  # type: ignore[arg-type]
    req = _FakeRequest(method="GET", path="/items")

    with (
        patch("sentry_sdk.start_transaction", return_value=mock_tx),
        patch("sentry_sdk.add_breadcrumb"),
    ):
        result = await mw.before_request(req)  # type: ignore[arg-type]

    assert result is None
    assert getattr(req.state, "_sentry_tx", None) is mock_tx


@pytest.mark.asyncio
async def test_after_response_sets_status_tag() -> None:
    """after_response sets http.status_code tag on the transaction."""
    mock_tx = MagicMock()
    mock_tx.__enter__ = MagicMock(return_value=mock_tx)
    mock_tx.__exit__ = MagicMock(return_value=False)

    mw = SentryMiddleware(app=MagicMock())  # type: ignore[arg-type]
    req = _FakeRequest(method="POST", path="/data")
    req.state._sentry_tx = mock_tx  # type: ignore[attr-defined]

    result = await mw.after_response(req, _FakeResponse(status_code=201))  # type: ignore[arg-type]

    assert result is None
    mock_tx.set_tag.assert_any_call("http.status_code", "201")
    mock_tx.set_tag.assert_any_call("http.method", "POST")
    mock_tx.set_tag.assert_any_call("http.target", "/data")
    mock_tx.__exit__.assert_called_once_with(None, None, None)


@pytest.mark.asyncio
async def test_after_response_no_tx_is_noop() -> None:
    """after_response does nothing when no transaction is stored on state."""
    mw = SentryMiddleware(app=MagicMock())  # type: ignore[arg-type]
    req = _FakeRequest()
    result = await mw.after_response(req, _FakeResponse(status_code=200))  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_after_response_ok_status_for_2xx() -> None:
    """after_response calls set_status('ok') for 2xx responses."""
    mock_tx = MagicMock()
    mock_tx.__enter__ = MagicMock(return_value=mock_tx)
    mock_tx.__exit__ = MagicMock(return_value=False)

    mw = SentryMiddleware(app=MagicMock())  # type: ignore[arg-type]
    req = _FakeRequest()
    req.state._sentry_tx = mock_tx  # type: ignore[attr-defined]

    await mw.after_response(req, _FakeResponse(200))  # type: ignore[arg-type]
    mock_tx.set_status.assert_called_with("ok")


@pytest.mark.asyncio
async def test_after_response_internal_error_for_5xx() -> None:
    """after_response calls set_status('internal_error') for 5xx responses."""
    mock_tx = MagicMock()
    mock_tx.__enter__ = MagicMock(return_value=mock_tx)
    mock_tx.__exit__ = MagicMock(return_value=False)

    mw = SentryMiddleware(app=MagicMock())  # type: ignore[arg-type]
    req = _FakeRequest()
    req.state._sentry_tx = mock_tx  # type: ignore[attr-defined]

    await mw.after_response(req, _FakeResponse(500))  # type: ignore[arg-type]
    mock_tx.set_status.assert_called_with("internal_error")
