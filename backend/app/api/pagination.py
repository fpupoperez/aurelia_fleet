"""Build the next-page query string."""

from urllib.parse import urlencode

from fastapi import Request


def next_page(request: Request, *, offset: int, limit: int, total: int) -> str | None:
    """The query string for the next library page, or None on the last page."""
    if offset * limit >= total:
        return None
    params = dict(request.query_params)
    params["limit"] = str(limit)
    params["offset"] = str(offset + 1)
    return f"?{urlencode(params)}"
