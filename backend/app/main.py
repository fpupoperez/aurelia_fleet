"""Application factory.

The JSON error handlers live here so every route returns the same envelope.
File download is the exception: that route returns the file bytes itself.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.responses import Response

from app.api.openapi import OPENAPI_DESCRIPTION, OPENAPI_TAGS
from app.api.v1.answers import unavailable_body
from app.api.v1.router import router as v1_router
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ProviderUnavailable
from app.core.logging import configure_logging, job_id_var
from app.core.telemetry import configure_telemetry
from app.db.session import get_engine, session_factory
from app.schemas.envelope import ErrorResponse, failure
from app.services.seed import seed_corpus

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logs and traces, open the database, and seed the sample corpus when the library is empty."""
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)
    configure_telemetry(settings, settings.otel_service_name)
    get_engine()
    app.state.session_factory = session_factory()
    if settings.seed_corpus:
        try:
            seed_corpus(settings)
        except Exception:
            logger.exception("Corpus seed failed")
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app. Tests pass an explicit Settings instance."""
    resolved = settings or get_settings()
    app = FastAPI(
        title=resolved.app_name,
        summary="Manual assistant for Aurelia fleet technicians.",
        description=OPENAPI_DESCRIPTION,
        version="v1.0.0",
        openapi_tags=OPENAPI_TAGS,
        docs_url=f"{resolved.api_prefix}/docs",
        openapi_url=f"{resolved.api_prefix}/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=resolved.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(v1_router, prefix=resolved.api_prefix)
    _register_handlers(app)

    @app.middleware("http")
    async def add_request_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Give every request an id and return it on the response so logs and the client can match."""
        request_id = request.headers.get("x-request-id", str(uuid4()))
        token = job_id_var.set(request.headers.get("x-job-id", ""))
        try:
            response = await call_next(request)
        finally:
            job_id_var.reset(token)
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Send a browser that opens the host root to the interactive API docs."""
        return RedirectResponse(url=f"{resolved.api_prefix}/docs")

    return app


def _dump(body: ErrorResponse) -> dict[str, object]:
    """Serialize an error envelope as JSON."""
    return body.model_dump(mode="json", by_alias=True, exclude_unset=True)


def _validation_message(exc: RequestValidationError) -> str:
    """Turn a FastAPI validation error into one sentence for the envelope."""
    parts: list[str] = []
    for error in exc.errors():
        error_type = str(error.get("type", ""))
        location = error.get("loc", ())
        if error_type == "json_invalid":
            parts.append("Malformed JSON body")
            continue
        if location == ("body",) and error_type == "model_attributes_type":
            parts.append("JSON body must be an object")
            continue
        place = ".".join(str(part) for part in location)
        parts.append(f"{place}: {error.get('msg')}")
    return "; ".join(parts) or "Request validation failed"


def _register_handlers(app: FastAPI) -> None:
    """Map known failures to the JSON envelope and hide unexpected traces from the client."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        """Return the status and message a service already chose."""
        body = failure(exc.status_code, exc.message, exc.session)
        return JSONResponse(status_code=exc.status_code, content=_dump(body))

    @app.exception_handler(ProviderUnavailable)
    async def handle_provider(_request: Request, exc: ProviderUnavailable) -> JSONResponse:
        """Return 503 with the passages when the chat model is down."""
        citations = [item.model_dump(mode="json", by_alias=True) for item in exc.citations]
        return JSONResponse(
            status_code=503,
            content=unavailable_body(exc.session, citations, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        """Return 422 when the request body or a query parameter is invalid."""
        body = failure(422, _validation_message(exc), {})
        return JSONResponse(status_code=422, content=_dump(body))

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        """Return 500 without the exception text. The traceback stays in the server log."""
        logger.error("Unhandled request failure", exc_info=exc)
        body = failure(500, "Internal server error", {})
        return JSONResponse(status_code=500, content=_dump(body))


app = create_app()
