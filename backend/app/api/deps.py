"""Request dependencies."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.auth import Caller, get_caller
from app.core.config import Settings


def get_settings_from_app(request: Request) -> Settings:
    """The settings object stored on the app at startup."""
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    """A database session for one request. It is closed when the request finishes."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_request_caller(request: Request) -> Caller:
    """The tenant from the bearer token, or the default tenant when auth is off."""
    return get_caller(request, request.app.state.settings)


def bind_sessions(settings: Settings):
    """Create the engine after settings are fixed, including in tests."""
    from app.db.session import session_factory as factory

    return factory()
