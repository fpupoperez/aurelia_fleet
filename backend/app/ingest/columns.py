"""Column-aware reading order for PDF text blocks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextBlock:
    """One positioned PDF block. Column order uses the box, not the order PyMuPDF streamed the characters."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def x_center(self) -> float:
        """Horizontal middle of the block, used to decide which column it belongs to."""
        return (self.x0 + self.x1) / 2


def order_blocks(blocks: list[TextBlock], page_width: float) -> tuple[str, bool]:
    """Read each column top to bottom, then the next column to the right.

    Returns the text and whether more than one column was detected.
    """
    usable = [block for block in blocks if block.text.strip()]
    if not usable:
        return "", False
    columns = _cluster(usable, page_width)
    multi = len(columns) > 1
    parts: list[str] = []
    for column in columns:
        ordered = sorted(column, key=lambda block: (block.y0, block.x0))
        parts.append("\n".join(block.text.strip() for block in ordered))
    return "\n\n".join(parts), multi


def _cluster(blocks: list[TextBlock], page_width: float) -> list[list[TextBlock]]:
    """Split blocks into columns at wide gaps between horizontal centers."""
    ordered = sorted(blocks, key=lambda block: block.x_center)
    gap_limit = max(page_width * 0.12, 40)
    columns: list[list[TextBlock]] = [[ordered[0]]]
    for previous, block in zip(ordered, ordered[1:], strict=False):
        if block.x_center - previous.x_center > gap_limit:
            columns.append([block])
        else:
            columns[-1].append(block)
    return columns


def tokens(text: str) -> set[str]:
    """Words in the geometric text. A reading-order result that adds a word is rejected."""
    return {piece for piece in _words(text) if piece}


def grounded(source: str, output: str) -> bool:
    """True when the model did not introduce words that were not on the page."""
    return tokens(output) <= tokens(source)


def _words(text: str) -> list[str]:
    """Lowercase words, so the grounding check ignores case and punctuation."""
    cleaned = []
    word = []
    for char in text.lower():
        if char.isalnum():
            word.append(char)
        elif word:
            cleaned.append("".join(word))
            word = []
    if word:
        cleaned.append("".join(word))
    return cleaned
