"""Shared pytest fixtures for hawkapi-sentry tests."""

from __future__ import annotations

from typing import Any

import pytest
import sentry_sdk
import sentry_sdk.transport


class CapturingTransport(sentry_sdk.transport.Transport):
    """In-memory Sentry transport that records envelopes instead of sending."""

    def __init__(self) -> None:
        super().__init__()
        self.captured: list[Any] = []

    def capture_envelope(self, envelope: Any) -> None:  # type: ignore[override]
        self.captured.append(envelope)


@pytest.fixture()
def capturing_transport() -> CapturingTransport:
    """Return a fresh CapturingTransport instance."""
    return CapturingTransport()


@pytest.fixture(autouse=True)
def reset_sentry() -> Any:
    """Isolate each test: re-init Sentry to a no-op client after the test."""
    yield
    sentry_sdk.init()  # resets to no-op client
