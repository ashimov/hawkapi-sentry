"""SentryMiddleware — per-request Sentry transaction and breadcrumb."""

from __future__ import annotations

from typing import Any

import sentry_sdk
from hawkapi.middleware.base import Middleware
from hawkapi.requests.request import Request
from hawkapi.responses.json_response import JSONResponse
from hawkapi.responses.response import Response

from hawkapi_sentry._context import status_class


class SentryMiddleware(Middleware):
    """Starts a Sentry performance transaction for every HTTP request."""

    async def before_request(self, request: Request) -> Request | Response | JSONResponse | None:
        """Start a Sentry transaction and add a breadcrumb."""
        method: str = request.method
        path: str = request.path

        # Extract traceparent for distributed tracing
        traceparent = request.headers.get("sentry-trace") or request.headers.get("traceparent")

        transaction = sentry_sdk.start_transaction(
            op="http.server",
            name=f"{method} {path}",
            source="url",
        )
        if traceparent:
            transaction.continuing_trace({"sentry-trace": traceparent})  # type: ignore[attr-defined]

        request.state._sentry_tx = transaction  # type: ignore[attr-defined]
        transaction.__enter__()  # type: ignore[attr-defined]

        sentry_sdk.add_breadcrumb(
            category="request",
            message=f"{method} {path}",
            level="info",
        )

        return None

    async def after_response(
        self, request: Request, response: Response | JSONResponse
    ) -> Response | JSONResponse | None:
        """Finish the Sentry transaction with HTTP metadata."""
        tx: Any = getattr(getattr(request, "state", None), "_sentry_tx", None)
        if tx is None:
            return None

        status_code: int = response.status_code
        tx.set_tag("http.method", request.method)
        tx.set_tag("http.status_code", str(status_code))
        tx.set_tag("http.target", request.path)
        tx.set_status(status_class(status_code))
        tx.__exit__(None, None, None)  # type: ignore[attr-defined]

        return None
