"""Integration test: SentryPlugin + SentryMiddleware with a real HawkAPI app."""

from __future__ import annotations

import httpx
import pytest

from hawkapi_sentry import SentryMiddleware, SentryPlugin
from tests.conftest import CapturingTransport


@pytest.mark.asyncio
async def test_exception_captured_via_app(capturing_transport: CapturingTransport) -> None:
    """End-to-end: exception in a route handler is captured by SentryPlugin."""
    from hawkapi import HawkAPI

    app = HawkAPI(title="test-app")
    plugin = SentryPlugin(dsn="http://fake@localhost/1", transport=capturing_transport)
    app.add_plugin(plugin)
    app.add_middleware(SentryMiddleware)

    @app.get("/boom")
    async def _boom() -> dict[str, str]:
        raise RuntimeError("integration error")

    # Manually trigger startup so Sentry is initialised before the request
    plugin.on_startup()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/boom")

    assert resp.status_code == 500
    assert len(capturing_transport.captured) > 0
