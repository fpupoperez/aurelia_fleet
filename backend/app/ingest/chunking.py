"""Split extracted pages into overlapping chunks that do not cross a page."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkDraft:
    """One window of text, the printed page it came from, and its index within the document."""
    page: int
    index: int
    content: str


def chunk_pages(pages: list[tuple[int, str]], *, size: int, overlap: int) -> list[ChunkDraft]:
    """Pack each page on its own so a citation page stays honest."""
    drafts: list[ChunkDraft] = []
    index = 0
    for page, text in pages:
        normalized = " ".join(text.split())
        if not normalized:
            continue
        for piece in _windows(normalized, size=size, overlap=overlap):
            drafts.append(ChunkDraft(page=page, index=index, content=piece))
            index += 1
    return drafts


def markdown_sections(text: str) -> list[tuple[int, str]]:
    """Treat each Markdown heading as a page, because Markdown has no printed page."""
    lines = text.splitlines()
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("#") and current:
            sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)
    pages = []
    number = 1
    for section in sections:
        body = "\n".join(section).strip()
        if body:
            pages.append((number, body))
            number += 1
    return pages


def plain_pages(text: str) -> list[tuple[int, str]]:
    """Treat a whole text file as page 1. Plain text has no headings to split on."""
    body = text.strip()
    if not body:
        return []
    return [(1, body)]


def _windows(text: str, *, size: int, overlap: int) -> list[str]:
    """Slice one page into size-character windows. Overlap stays inside the page, and a cut prefers a space."""
    if overlap >= size:
        overlap = size // 5
    pieces: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + size)
        if end < length:
            space = text.rfind(" ", start + size // 2, end)
            if space != -1:
                end = space
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= length:
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start
    return pieces
