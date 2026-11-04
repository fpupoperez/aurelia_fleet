"""Errors that cross the HTTP boundary with the standard response envelope."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """A failed request that already has an HTTP status and a client message."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        session: dict[str, Any] | None = None,
    ) -> None:
        """Store the HTTP status and the envelope message."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.session = session or {}


class ProviderUnavailable(Exception):
    """The chat provider did not answer. Citations may still be shown."""

    def __init__(self, message: str, *, session: dict[str, Any], citations: list[Any]) -> None:
        """Store the passages the UI can still show while the model is down."""
        super().__init__(message)
        self.message = message
        self.session = session
        self.citations = citations
