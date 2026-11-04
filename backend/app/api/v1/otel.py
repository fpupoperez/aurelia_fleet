"""Forward browser spans to Langfuse without exposing keys."""

import logging

import httpx
from fastapi import APIRouter, Request, Response

from app.core.telemetry import langfuse_auth_header

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Telemetry"])


@router.post("/otel/v1/traces", include_in_schema=False)
async def forward_traces(request: Request) -> Response:
    """Accept an OTLP trace payload from the browser and forward it to Langfuse."""
    settings = request.app.state.settings
    authorization = langfuse_auth_header(settings)
    if authorization is None:
        return Response(status_code=204)
    body = await request.body()
    content_type = request.headers.get("content-type", "application/x-protobuf")
    url = f"{settings.langfuse_host.rstrip('/')}/api/public/otel/v1/traces"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            upstream = await client.post(
                url,
                content=body,
                headers={"Authorization": authorization, "Content-Type": content_type},
            )
    except httpx.HTTPError:
        logger.warning("Could not forward browser traces", exc_info=True)
        return Response(status_code=204)
    return Response(status_code=upstream.status_code, content=upstream.content)
