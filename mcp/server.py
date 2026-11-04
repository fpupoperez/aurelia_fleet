"""MCP tools that call the Aurelia HTTP API. One tool per operationId."""

import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parents[1]
_HERE = Path(__file__).resolve().parent
# This directory is named mcp, which would hide the installed MCP SDK.
sys.path = [
    entry
    for entry in sys.path
    if entry and Path(entry).resolve() not in {_HERE, _ROOT}
]
sys.path.insert(0, str(_ROOT / "backend"))

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.telemetry import configure_telemetry, record_mcp, span

from mcp.server.fastmcp import FastMCP

settings = get_settings()
configure_logging(settings.log_level)
configure_telemetry(settings, "aurelia-mcp")

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
mcp = FastMCP("Aurelia Fleet", host=os.environ.get("MCP_HOST", "0.0.0.0"), port=int(os.environ.get("MCP_PORT", "8001")))


def _envelope_from_error(status: int, message: str) -> dict:
    """The same JSON envelope the API uses, for a failure that never reached a response body."""
    return {
        "session_auth": {},
        "errors": [{"code": status, "msg": message}],
        "success": False,
        "data": None,
    }


def _call(method: str, path: str, operation_id: str, **kwargs: Any) -> dict:
    """Perform one HTTP call, time it, and return the API envelope unchanged."""
    started = time.perf_counter()
    with span("mcp.tool", operation_id=operation_id) as current:
        try:
            response = httpx.request(method, f"{API_BASE_URL}{path}", timeout=120, **kwargs)
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            current.set_attribute("success", False)
            current.set_attribute("duration_ms", duration_ms)
            record_mcp(operation_id, success=False, duration_ms=duration_ms)
            return _envelope_from_error(503, f"The API is unreachable: {exc}")
        duration_ms = (time.perf_counter() - started) * 1000
        current.set_attribute("http_status", response.status_code)
        current.set_attribute("duration_ms", duration_ms)
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = _envelope_from_error(response.status_code, response.text[:500] or "Empty response")
        success = bool(body.get("success"))
        current.set_attribute("success", success)
        record_mcp(operation_id, success=success, duration_ms=duration_ms)
        return body


@mcp.tool(name="get_service_status")
def get_service_status() -> dict:
    """Check that the API process is serving requests. This tool takes no arguments."""
    return _call("GET", "/status", "get_service_status")


@mcp.tool(name="upload_document")
def upload_document(
    filename: str,
    content_base64: str,
    equipment_model: str,
    title: str,
    language: str | None = None,
) -> dict:
    """Upload one manual.

    filename includes the extension (.pdf, .md, or .txt).
    content_base64 is the raw file encoded as base64.
    equipment_model and title are required. The same bytes are not ingested twice.
    Read data.jobId and then call get_job.
    """
    raw = base64.b64decode(content_base64)
    metadata: dict[str, str] = {"equipmentModel": equipment_model, "title": title}
    if language:
        metadata["language"] = language
    return _call(
        "POST",
        "/documents",
        "upload_document",
        files={"file": (filename, raw, "application/octet-stream")},
        data={"metadata": json.dumps(metadata)},
    )


@mcp.tool(name="get_job")
def get_job(job_id: str) -> dict:
    """Read ingest status for job_id from upload_document.

    status is pending, processing, completed, or failed.
    failureReason is set only when status is failed. Poll until completed or failed.
    """
    return _call("GET", f"/jobs/{job_id}", "get_job")


@mcp.tool(name="list_documents")
def list_documents(equipment_model: str | None = None, limit: int = 50, offset: int = 1) -> dict:
    """List manuals for the tenant.

    equipment_model is optional. offset is a page number starting at 1.
    Follow data.next instead of guessing the next page.
    """
    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    if equipment_model:
        params["equipmentModel"] = equipment_model
    return _call("GET", "/documents", "list_documents", params=params)


@mcp.tool(name="list_equipment_models")
def list_equipment_models(q: str = "") -> dict:
    """Search equipment models already stored in the library.

    q is the text typed so far. An empty q returns every model. Use the stored spelling on upload.
    """
    return _call("GET", "/equipment-models", "list_equipment_models", params={"q": q})


@mcp.tool(name="list_makers")
def list_makers(q: str = "") -> dict:
    """Search makers already stored in the library.

    q is the text typed so far. An empty q returns every maker. Use the stored spelling on upload.
    """
    return _call("GET", "/makers", "list_makers", params={"q": q})


@mcp.tool(name="ask_question")
def ask_question(question: str, equipment_model: str | None = None, k: int = 5) -> dict:
    """Ask a question about the manuals.

    When success is true and data.answered is false, the manuals do not support an answer.
    Do not invent a fact in that case. Read errors[0].msg when success is false.
    equipment_model restricts retrieval. k is between 1 and 20.
    """
    body: dict[str, str | int] = {"question": question, "k": k}
    if equipment_model:
        body["equipmentModel"] = equipment_model
    return _call("POST", "/answers", "ask_question", json=body)


@mcp.tool(name="list_aliases")
def list_aliases() -> dict:
    """List alias groups for the tenant. Words in one group are the same feature during search."""
    return _call("GET", "/aliases", "list_aliases")


@mcp.tool(name="create_alias")
def create_alias(terms: list[str]) -> dict:
    """Add a group of equivalent words, such as bluetooth and ble.

    Each word is letters and digits, 2 to 40 characters. A word cannot be in two groups.
    """
    return _call("POST", "/aliases", "create_alias", json={"terms": terms})


@mcp.tool(name="update_alias")
def update_alias(alias_id: str, terms: list[str]) -> dict:
    """Replace every word in an alias group. Send the full list, not only the new word."""
    return _call("PUT", f"/aliases/{alias_id}", "update_alias", json={"terms": terms})


@mcp.tool(name="delete_alias")
def delete_alias(alias_id: str) -> dict:
    """Delete an alias group. Later questions no longer treat those words as the same feature."""
    return _call("DELETE", f"/aliases/{alias_id}", "delete_alias")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
