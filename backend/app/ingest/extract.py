"""Extract text from PDF, Markdown, and plain text."""

from __future__ import annotations

from dataclasses import dataclass

import fitz

from app.domain.errors import PermanentIngestError
from app.ingest.chunking import markdown_sections, plain_pages
from app.ingest.columns import TextBlock, order_blocks


@dataclass(frozen=True)
class PageText:
    """One page of text, whether it had multiple columns, and the block text used to check a model reorder."""
    page: int
    text: str
    multi_column: bool
    source: str


def extract_document(path: str, media_type: str) -> list[PageText]:
    """Dispatch on media type. PDF, Markdown, and plain text are the only accepted kinds."""
    if media_type == "application/pdf" or path.lower().endswith(".pdf"):
        return extract_pdf(path)
    if media_type == "text/markdown" or path.lower().endswith((".md", ".markdown")):
        text = _read_text(path)
        return [PageText(page, body, False, body) for page, body in markdown_sections(text)]
    if media_type == "text/plain" or path.lower().endswith(".txt"):
        text = _read_text(path)
        return [PageText(page, body, False, body) for page, body in plain_pages(text)]
    raise PermanentIngestError("Unsupported file type. Send a PDF, Markdown, or plain text file.")


def extract_pdf(path: str) -> list[PageText]:
    """Read each page in column order. A page whose blocks form two columns is marked multi_column."""
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise PermanentIngestError("The PDF could not be opened.") from exc
    pages: list[PageText] = []
    try:
        if document.page_count == 0:
            raise PermanentIngestError("The PDF has no pages.")
        for index, page in enumerate(document, start=1):
            raw = page.get_text("dict")
            blocks = _blocks(raw)
            if not blocks and not page.get_text("text").strip():
                pages.append(PageText(index, "", False, ""))
                continue
            text, multi = order_blocks(blocks, page.rect.width)
            source = "\n".join(block.text for block in blocks)
            pages.append(PageText(index, text, multi, source or text))
    finally:
        document.close()
    return pages


def _blocks(raw: dict) -> list[TextBlock]:
    """Positioned text blocks on one page. Empty blocks are dropped."""
    blocks: list[TextBlock] = []
    for block in raw.get("blocks", []):
        lines = []
        for line in block.get("lines", []):
            pieces = [span.get("text", "") for span in line.get("spans", [])]
            line_text = "".join(pieces).strip()
            if line_text:
                lines.append(line_text)
        if not lines:
            continue
        x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
        blocks.append(TextBlock(" ".join(lines), float(x0), float(y0), float(x1), float(y1)))
    return blocks


def _read_text(path: str) -> str:
    """Read a text file as UTF-8. Unreadable bytes fail the job instead of being guessed."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except UnicodeDecodeError as exc:
        raise PermanentIngestError("The file is not valid UTF-8 text.") from exc
