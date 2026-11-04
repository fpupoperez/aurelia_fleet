"""Answer model and maker questions from document metadata, without a model call."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentRow
from app.schemas.answers import AnswerData, Confidence

_WORD = re.compile(r"[a-z0-9]+")
_FILLER = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "for",
        "to",
        "on",
        "in",
        "by",
        "from",
        "and",
        "or",
        "do",
        "does",
        "did",
        "is",
        "are",
        "was",
        "were",
        "we",
        "our",
        "you",
        "your",
        "me",
        "all",
        "any",
        "there",
        "what",
        "whats",
        "which",
        "who",
        "whose",
        "list",
        "show",
        "tell",
        "have",
        "has",
        "had",
        "available",
        "library",
        "manual",
        "manuals",
        "about",
        "with",
    }
)
_NOUNS = frozenset(
    {
        "model",
        "models",
        "maker",
        "makers",
        "manufacturer",
        "manufacturers",
        "brand",
        "brands",
        "device",
        "devices",
        "product",
        "products",
        "equipment",
    }
)
_MAKER_VERBS = frozenset({"make", "makes", "made", "maker", "makers", "manufacturer", "manufacturers", "brand", "brands"})


@dataclass(frozen=True)
class CatalogEntry:
    """One manual's model, maker, and title. Catalog answers use only these fields."""
    equipment_model: str
    maker: str
    title: str


def detect_maker(*parts: str) -> str:
    """Read a manufacturer name from manual text. The upload value wins when it is set."""
    blob = "\n".join(parts).lower()
    if re.search(r"(^|[^a-z0-9])ruptela([^a-z0-9]|$)", blob):
        return "Ruptela"
    if re.search(r"(^|[^a-z0-9])aurelia([^a-z0-9]|$)", blob):
        return "Aurelia"
    return ""


def answer_catalog(session: Session, *, tenant_id: str, question: str) -> AnswerData | None:
    """Answer who-makes and which-models questions from metadata. None when this is not that kind of question."""
    entries = [
        CatalogEntry(row.equipment_model, row.maker or "", row.title)
        for row in session.execute(
            select(DocumentRow.equipment_model, DocumentRow.maker, DocumentRow.title).where(
                DocumentRow.tenant_id == tenant_id
            )
        ).all()
    ]
    text = _answer_text(question, entries)
    if text is None:
        return None
    return AnswerData(
        answered=True,
        answer=text,
        citations=[],
        confidence=Confidence.high,
        refusal_reason=None,
    )


def _answer_text(question: str, entries: list[CatalogEntry]) -> str | None:
    """Pick a catalog sentence, or None so the caller continues to comparison and search."""
    words = _WORD.findall(question.lower())
    if not words or not entries:
        return None
    nouns = [word for word in words if word in _NOUNS]
    content = [word for word in words if word not in _FILLER and word not in _NOUNS and word not in _MAKER_VERBS]
    makers = _mentioned(content, [entry.maker for entry in entries])
    models = _mentioned(content, [entry.equipment_model for entry in entries])
    covered = set(makers) | set(models)
    if any(word not in covered for word in content):
        return None
    asks_maker = bool(set(words) & _MAKER_VERBS) or any(word in {"maker", "makers", "manufacturer", "manufacturers", "brand", "brands"} for word in nouns)
    asks_models = any(word in {"model", "models", "device", "devices", "product", "products", "equipment"} for word in nouns)
    if models and asks_maker and not asks_models:
        return _who_makes(models, entries)
    if not nouns and not asks_maker:
        return None
    if makers and (asks_models or not asks_maker):
        return _list_models(entries, makers)
    if asks_maker and not models:
        return _list_makers(entries)
    if asks_models and not content:
        return _list_models(entries, set())
    return None


def _mentioned(words: list[str], labels: list[str]) -> set[str]:
    """Labels from the library that appear as words in the question."""
    found: set[str] = set()
    for label in labels:
        tokens = _WORD.findall(label.lower())
        if tokens and all(token in words for token in tokens):
            found.update(tokens)
    return found


def _who_makes(model_tokens: set[str], entries: list[CatalogEntry]) -> str | None:
    """The maker of a model the question names, when the question asks who makes it."""
    matched = [entry for entry in entries if set(_WORD.findall(entry.equipment_model.lower())) <= model_tokens and _WORD.findall(entry.equipment_model.lower())]
    if not matched:
        return None
    model = matched[0].equipment_model
    makers = sorted({entry.maker for entry in matched if entry.maker})
    if not makers:
        return f"The manuals do not name a maker for {model}."
    return f"{model} is made by {', '.join(makers)}."


def _list_models(entries: list[CatalogEntry], maker_tokens: set[str]) -> str | None:
    """The models stored for a maker the question names."""
    chosen = entries
    if maker_tokens:
        chosen = [entry for entry in entries if set(_WORD.findall(entry.maker.lower())) <= maker_tokens and entry.maker]
    seen: dict[str, str] = {}
    for entry in chosen:
        seen.setdefault(entry.equipment_model, entry.maker)
    if not seen:
        return None
    parts = [f"{model} ({maker})" if maker else model for model, maker in sorted(seen.items())]
    if maker_tokens:
        maker = next(entry.maker for entry in chosen if entry.maker)
        return f"{maker} models: {', '.join(parts)}."
    return f"Models: {', '.join(parts)}."


def _list_makers(entries: list[CatalogEntry]) -> str | None:
    """The distinct makers in the library, when the question asks which makers are indexed."""
    makers = sorted({entry.maker for entry in entries if entry.maker})
    if not makers:
        return None
    return f"Makers: {', '.join(makers)}."
