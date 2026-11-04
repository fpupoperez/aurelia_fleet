"""Read maker, model, and title from a manual so the uploader does not have to type them."""

from __future__ import annotations

import re
from dataclasses import dataclass

import fitz

from app.domain.errors import DomainError
from app.retrieval.catalog import detect_maker
from app.schemas.documents import DocumentUploadRequest

_CODE = re.compile(r"\b(?:[A-Z]{1,6}-\d{1,4}[A-Z0-9]*|[A-Z]{1,6}\d{1,4}[A-Z0-9]*)\b")
_DATASHEET = re.compile(
    r"datasheet|key capabilities|key values|applications|valores clave|aplicaciones",
    re.IGNORECASE,
)
_LANGUAGE = re.compile(r"^(EN|ES|PT|FR|DE)[-_ ]", re.IGNORECASE)
_DOCUMENT_WORDS = frozenset(
    {
        "service",
        "manual",
        "manuals",
        "installation",
        "inspection",
        "note",
        "notes",
        "guide",
        "datasheet",
        "procedure",
        "ficha",
    }
)


@dataclass(frozen=True)
class TextSpan:
    """One run of PDF text with its font size and position. Size picks the title; x-gaps join split letters."""
    text: str
    size: float
    x0: float
    x1: float
    y0: float


@dataclass(frozen=True)
class ManualIdentity:
    """Names read from the file. A blank field means the file did not say, so the user must type it."""
    maker: str
    equipment_model: str
    title: str
    language: str | None = None


def read_identity(raw: bytes, filename: str, media_type: str) -> ManualIdentity:
    """Return the names printed on the file. Empty strings mean the file did not say."""
    if media_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return _from_pdf(raw, filename)
    return _from_text(_decode(raw), filename, pdf_title="")


def resolved_metadata(metadata: DocumentUploadRequest, identity: ManualIdentity) -> tuple[str, str, str, str | None]:
    """Prefer a name the user typed. Fill the rest from the file."""
    equipment_model = (metadata.equipment_model or "").strip() or identity.equipment_model
    maker = (metadata.maker or "").strip() or identity.maker
    title = (metadata.title or "").strip() or identity.title or equipment_model
    language = (metadata.language or "").strip() or identity.language
    if not equipment_model:
        raise DomainError(
            "This file does not name an equipment model. Enter the model and upload again.",
            status_code=422,
        )
    if not title:
        raise DomainError(
            "This file does not name a title. Enter a title and upload again.",
            status_code=422,
        )
    return equipment_model[:120], maker[:120], title[:250], language[:16] if language else None


def heading_from_spans(spans: list[TextSpan]) -> str:
    """Join the largest short text on the first page into one product name."""
    useful = [span for span in spans if _short_label(span.text)]
    if not useful:
        return ""
    largest = max(span.size for span in useful)
    chosen = [span for span in useful if span.size >= largest - 0.6]
    top = chosen[0].y0
    line = [span for span in chosen if abs(span.y0 - top) <= 6]
    return _join_spans(line)


def _from_pdf(raw: bytes, filename: str) -> ManualIdentity:
    """Read the first page's large heading and the text of the first eight pages."""
    try:
        document = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise DomainError("The PDF could not be opened.", status_code=400) from exc
    try:
        if document.page_count == 0:
            raise DomainError("The PDF has no pages.", status_code=400)
        spans = _page_spans(document[0])
        pages = [document[index].get_text("text") for index in range(min(8, document.page_count))]
        pdf_title = str((document.metadata or {}).get("title") or "")
    finally:
        document.close()
    heading = heading_from_spans(spans)
    return _from_text("\n".join(pages), filename, pdf_title=pdf_title, heading=heading)


def _from_text(text: str, filename: str, pdf_title: str, heading: str = "") -> ManualIdentity:
    """Choose model, title, maker, and language. A non-English filename adds a language tag to the title."""
    printed = heading or _markdown_heading(text)
    model = _model_name(printed, text)
    title = _title(printed, model, text)
    language = _language(pdf_title) or _language(filename)
    if language and language != "en" and title and f"({language.upper()})" not in title:
        title = f"{title} ({language.upper()})"
    return ManualIdentity(
        maker=detect_maker(text, pdf_title, filename),
        equipment_model=model,
        title=title[:250],
        language=language,
    )


def _model_name(heading: str, text: str) -> str:
    """Prefer the heading unless it is a generic word such as Manual. Otherwise use a product code."""
    if heading and not _is_document_title(heading):
        named = _usable(heading)
        if named:
            return named
    return _product_code(heading) or _product_code(text[:2500])


def _title(heading: str, model: str, text: str) -> str:
    """Use the heading when it is a document title, or '{model} datasheet' when the first pages look like one."""
    if heading and (_is_document_title(heading) or (model and model in heading and heading != model)):
        return heading
    if model and _DATASHEET.search(f"{heading}\n{text[:2500]}"):
        return f"{model} datasheet"
    return model


def _page_spans(page: fitz.Page) -> list[TextSpan]:
    """Text runs on one PDF page, in the order PyMuPDF returns them."""
    spans: list[TextSpan] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = str(span.get("text", ""))
                if not text.strip():
                    continue
                x0, y0, x1, _y1 = span.get("bbox", (0, 0, 0, 0))
                spans.append(TextSpan(text, float(span.get("size", 0)), float(x0), float(x1), float(y0)))
    return spans


def _join_spans(spans: list[TextSpan]) -> str:
    """Glue adjacent runs into one name. A tight gap joins 'C' 'FA' 'Adapter' into 'CFA Adapter'."""
    pieces: list[str] = []
    previous: TextSpan | None = None
    for span in spans:
        text = span.text.strip()
        if not text:
            continue
        if previous is None:
            pieces.append(text)
        else:
            gap = span.x0 - previous.x1
            tight = gap < 4 or (len(pieces[-1]) <= 2 and gap < 14 and " " not in text)
            if tight:
                pieces[-1] = f"{pieces[-1]}{text}"
            else:
                pieces.append(text)
        previous = span
    return _usable(" ".join(pieces))


def _markdown_heading(text: str) -> str:
    """The first Markdown heading, without the hash marks."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _product_code(text: str) -> str:
    """A token such as HX-200 or Pro5S."""
    match = _CODE.search(text or "")
    return match.group(0) if match else ""


def _is_document_title(heading: str) -> bool:
    """True when the heading is a generic document word rather than a product name."""
    words = {word.strip(".,:;") for word in heading.lower().split()}
    return bool(words & _DOCUMENT_WORDS)


def _language(name: str) -> str | None:
    """EN, ES, PT, FR, or DE taken from the start of a filename or PDF title."""
    match = _LANGUAGE.match(name.strip())
    if match is None:
        return None
    return match.group(1).lower()


def _short_label(text: str) -> bool:
    """True when the span is short enough to be a title rather than a paragraph."""
    stripped = text.strip()
    return bool(stripped) and len(stripped) <= 40 and any(character.isalpha() for character in stripped)


def _usable(value: str) -> str:
    """Strip a candidate name and drop ones that are only a document word."""
    cleaned = " ".join(value.split())
    if len(cleaned) < 2 or len(cleaned) > 40:
        return ""
    if not any(character.isalpha() for character in cleaned):
        return ""
    return cleaned


def _decode(raw: bytes) -> str:
    """UTF-8 text, with replacement characters for bytes that are not text."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DomainError("The file is not valid UTF-8 text.", status_code=400) from exc
