"""Hybrid retrieval over pgvector and full text.

Cosine distance and PostgreSQL ``simple`` full text are fused with reciprocal rank.
A passage that contains the question's content words is kept even past the cosine ceiling,
because the hash embedder sits far from a long page that merely contains a short name.
Search only reads chunks whose ``embedding_model`` is the active one, and always filters by tenant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ChunkRow, DocumentRow
from app.providers import EmbeddingProvider, active_embedding_model
from app.services.aliases import load_alias_groups

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "for",
        "to",
        "on",
        "in",
        "about",
        "what",
        "whats",
        "is",
        "are",
        "was",
        "were",
        "tell",
        "me",
        "give",
        "all",
        "we",
        "have",
        "know",
        "show",
        "describe",
        "please",
        "information",
        "info",
        "details",
        "detail",
        "device",
        "devices",
        "product",
        "products",
        "manual",
        "manuals",
        "machine",
        "machines",
        "unit",
        "units",
        "do",
        "does",
        "did",
        "you",
        "your",
        "our",
        "any",
        "there",
        "this",
        "that",
        "with",
        "from",
        "and",
        "or",
    }
)


@dataclass
class Hit:
    """One retrieved chunk, already joined to its document title and maker."""

    chunk_id: UUID
    document_id: UUID
    title: str
    equipment_model: str
    maker: str
    page: int
    content: str
    distance: float
    fused_score: float


@dataclass
class SearchResult:
    """Hits plus the flags the answer path uses to choose a direct quote or a model prompt.

    ``name_only`` means the question is just a product name, so every page of that manual is returned.
    ``feature_list`` means the question asks which devices have a capability.
    ``text_match`` means the kept pages literally contain the question's content words.
    """

    hits: list[Hit]
    abstained: bool
    top_distance: float | None
    fused_score: float | None
    candidate_count: int
    name_only: bool = False
    feature_list: bool = False
    text_match: bool = False
    alias_groups: tuple[frozenset[str], ...] = ()


def search(
    session: Session,
    *,
    settings: Settings,
    embedder: EmbeddingProvider,
    tenant_id: str,
    question: str,
    equipment_model: str | None,
    k: int,
) -> SearchResult:
    """Find passages for one question. Abstain when nothing is near enough and the words are absent."""
    vector = embedder.embed([question])[0]
    model_name = active_embedding_model(settings)
    distance = ChunkRow.embedding.cosine_distance(vector)
    library = _library(session, tenant_id)
    named_ids = [
        row.id
        for row in library
        if question_names_document(question, title=row.title, equipment_model=row.equipment_model)
    ]
    name_only = is_name_only_question(
        question,
        titles=[row.title for row in library],
        equipment_models=[row.equipment_model for row in library],
    )
    # A caller filter or a question that names a library manual already says which
    # document to read. The hash embedder puts a short product name near distance
    # 0.8 from a long page even when that page contains the name, so the global
    # ceiling would refuse the manual the user just asked for.
    scoped = bool(equipment_model) or bool(named_ids)
    filters = [
        ChunkRow.tenant_id == tenant_id,
        ChunkRow.embedding_model == model_name,
    ]
    if equipment_model:
        filters.append(ChunkRow.equipment_model == equipment_model)
    if named_ids:
        filters.append(ChunkRow.document_id.in_(named_ids))
    terms = feature_terms(question)
    groups = load_alias_groups(session, tenant_id)
    # A long word such as "desconnection" has to occur. Searching the short
    # word "battery" as well would keep a nearer page that never mentions it.
    distinctive = [term for term in _word_terms(terms) if len(term) >= 8]
    spelled = lookup_terms(distinctive or terms, groups)
    which_devices = asks_which_devices(question) and not name_only
    # Any question, not only "which devices", can name a fact that is in a manual.
    # The hash embedder often sits past the ceiling on that page, so a passage that
    # actually contains the words is kept. "CAN bus" still matches "CANbus".
    lexical = (
        _lexical_rows(session, filters, distance, spelled, settings.retrieval_candidates)
        if terms and not name_only
        else []
    )
    survivors = _best_per_document(lexical, terms, groups) if lexical else []
    feature_list = False
    text_match = False
    if survivors:
        top_distance = min(row[2] for row in survivors)
        feature_list = which_devices
        text_match = True
        unpacked_count = len(lexical)
    else:
        vector_rows = session.execute(
            select(ChunkRow, DocumentRow, distance.label("distance"))
            .join(DocumentRow, DocumentRow.id == ChunkRow.document_id)
            .where(*filters)
            .order_by(distance)
            .limit(settings.retrieval_candidates)
        ).all()
        unpacked = [(chunk, document, float(distance_value)) for chunk, document, distance_value in vector_rows]
        unpacked_count = len(unpacked)
        top_distance = unpacked[0][2] if unpacked else None
        if top_distance is None or (not scoped and top_distance > settings.max_cosine_distance):
            return SearchResult([], True, top_distance, None, unpacked_count, name_only)
        if scoped:
            survivors = unpacked
        else:
            # The nearest hit already cleared the ceiling. Keep its near neighbors too, so a
            # question that asks for everything about one machine is not cut down to one page
            # that landed 0.01 closer.
            neighbor_limit = top_distance + settings.retrieval_neighbor_margin
            survivors = [row for row in unpacked if row[2] <= max(settings.max_cosine_distance, neighbor_limit)]

    query = func.plainto_tsquery("simple", question)
    text_rows = session.execute(
        select(ChunkRow.id)
        .where(*filters, ChunkRow.tsv.op("@@")(query))
        .order_by(func.ts_rank_cd(ChunkRow.tsv, query).desc())
        .limit(settings.retrieval_candidates)
    ).all()
    survivor_ids = [chunk.id for chunk, _, _ in survivors]
    text_ids = [row[0] for row in text_rows if row[0] in set(survivor_ids)]
    scores = _rrf([survivor_ids, text_ids], settings.rrf_k)
    best = max(scores.values()) if scores else 0.0
    if best < settings.min_fused_score:
        return SearchResult([], True, top_distance, best, unpacked_count, name_only)

    by_id = {chunk.id: (chunk, document, distance_value) for chunk, document, distance_value in survivors}
    # A bare product name should see every page of that manual, not the first few
    # hash neighbors. k still caps a normal fact question.
    take = len(scores) if name_only or feature_list else k
    ordered = sorted(scores, key=lambda item: scores[item], reverse=True)[:take]
    hits = []
    for chunk_id in ordered:
        chunk, document, distance_value = by_id[chunk_id]
        hits.append(
            Hit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                title=document.title,
                equipment_model=chunk.equipment_model,
                maker=document.maker,
                page=chunk.page,
                content=chunk.content,
                distance=distance_value,
                fused_score=scores[chunk_id],
            )
        )
    return SearchResult(
        hits, False, top_distance, best, unpacked_count, name_only, feature_list, text_match, groups
    )


def compact_label(value: str) -> str:
    """Lowercase and drop punctuation so ``Pro5-S`` and ``pro5s`` compare as the same label."""
    return _NON_ALNUM.sub("", value.lower())


def content_words(text: str) -> list[str]:
    """Question words that can identify a fact. Stopwords such as 'what' and 'the' are dropped."""
    return [word for word in _WORD.findall(text.lower()) if word not in _STOPWORDS]


def question_names_document(question: str, *, title: str, equipment_model: str) -> bool:
    """True when the question contains a library title, model, or only words from them."""
    needle = compact_label(question)
    if needle:
        for label in (equipment_model, title):
            token = compact_label(label)
            if len(token) >= 3 and token in needle:
                return True
    words = content_words(question)
    if not words:
        return False
    labels = set(content_words(f"{title} {equipment_model}"))
    return all(word in labels for word in words) and any(len(word) >= 3 for word in words)


def is_name_only_question(question: str, *, titles: list[str], equipment_models: list[str]) -> bool:
    """True when the question mentions products and no other subject words."""
    words = content_words(question)
    if not words:
        return False
    labels: set[str] = set()
    named = False
    for title, equipment_model in zip(titles, equipment_models, strict=True):
        if question_names_document(question, title=title, equipment_model=equipment_model):
            named = True
            labels.update(content_words(f"{title} {equipment_model}"))
    return named and all(word in labels for word in words)


_FEATURE_WORDS = frozenset(
    {
        "which",
        "who",
        "where",
        "when",
        "how",
        "why",
        "whose",
        "support",
        "supports",
        "supported",
        "supporting",
        "use",
        "uses",
        "using",
        "used",
        "include",
        "includes",
        "including",
        "have",
        "has",
        "having",
        "capable",
        "capability",
        "capabilities",
        "feature",
        "features",
        "available",
        "provide",
        "provides",
        "provided",
        "work",
        "works",
        "working",
        "compatible",
        "compatibility",
        "able",
        "detect",
        "detects",
        "detecting",
    }
)
_DEVICE_WORDS = frozenset(
    {
        "device",
        "devices",
        "product",
        "products",
        "machine",
        "machines",
        "manual",
        "manuals",
        "unit",
        "units",
        "model",
        "models",
        "equipment",
        "vehicle",
        "vehicles",
        "tracker",
        "trackers",
    }
)


def _canonical_word(word: str) -> str:
    """Fold a one-letter typo of a question word, such as supoorting, back to supporting."""
    pools = (_FEATURE_WORDS, _DEVICE_WORDS, _STOPWORDS)
    if any(word in pool for pool in pools):
        return word
    if len(word) < 6:
        return word
    matches = [
        known
        for pool in pools
        for known in pool
        if len(known) >= 6 and _edit_distance_at_most_one(word, known)
    ]
    if not matches:
        return word
    matches.sort(key=lambda known: (abs(len(known) - len(word)), known))
    return matches[0]


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    """True for one substitution, insertion, or deletion. Used for typos, not for short words."""
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    index = 0
    other = 0
    edits = 0
    while index < len(left) and other < len(right):
        if left[index] == right[other]:
            index += 1
            other += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(left) == len(right):
            index += 1
        other += 1
    return edits + (len(left) - index) + (len(right) - other) <= 1


def _spellings(term: str, groups: tuple[frozenset[str], ...]) -> frozenset[str]:
    """The term plus every alias in its group. A long word one letter off joins that group too."""
    for group in groups:
        if term in group or any(
            len(term) >= 8 and len(item) >= 8 and _edit_distance_at_most_one(term, item) for item in group
        ):
            return frozenset(set(group) | {term})
    return frozenset({term})


def feature_terms(question: str) -> list[str]:
    """Content words, plus compounds such as CAN + bus -> canbus."""
    raw = [_canonical_word(word) for word in _WORD.findall(question.lower())]
    skipped = _STOPWORDS | _FEATURE_WORDS | _DEVICE_WORDS
    kept = [word for word in raw if word not in skipped and len(word) >= 3]
    terms: list[str] = []
    for word in kept:
        if word not in terms:
            terms.append(word)
    for left, right in zip(kept, kept[1:]):
        compound = left + right
        if compound not in terms:
            terms.append(compound)
    for left, right in re.findall(r"([a-z0-9]+)-([a-z0-9]+)", question.lower()):
        compound = left + right
        if compound not in terms and compound not in skipped:
            terms.append(compound)
    return terms


def asks_which_devices(question: str) -> bool:
    """A capability question should name every matching manual, not the first k."""
    words = {_canonical_word(word) for word in _WORD.findall(question.lower())}
    if not (words & _DEVICE_WORDS):
        return False
    if words & ({"which", "who", "what"} | _FEATURE_WORDS):
        return True
    return bool(feature_terms(question))


def _fold_text(text: str) -> str:
    """PDF text sometimes uses ligatures, so 'efficiency' is the word efficiency."""
    return (
        text.lower()
        .replace("fi", "fi")
        .replace("fl", "fl")
        .replace("ff", "ff")
        .replace("ffi", "ffi")
        .replace("ffl", "ffl")
    )


_NEGATION = re.compile(r"(?:^|[^a-z0-9])(?:not|no|sin|without)(?:[^a-z0-9]|$)")


def _affirmative_mention(content: str, terms: list[str], groups: tuple[frozenset[str], ...]) -> bool:
    """True when a feature word is not in the shadow of a nearby 'not' or 'no'."""
    folded = _fold_text(content)
    for term in terms:
        for spelling in _spellings(term, groups):
            pattern = rf"(?:^|[^a-z0-9]){re.escape(spelling)}(?:[^a-z0-9]|$)"
            for match in re.finditer(pattern, folded):
                window = folded[max(0, match.start() - 60) : match.start()]
                if _NEGATION.search(window) is None:
                    return True
    return False


def term_in_text(text: str, term: str) -> bool:
    """Whole-word match. A hyphen is a boundary, so ``nbiot`` matches ``NB-IoT``."""
    return re.search(rf"(^|[^a-z0-9]){re.escape(term)}([^a-z0-9]|$)", _fold_text(text)) is not None


def concept_in_text(text: str, term: str, groups: tuple[frozenset[str], ...] = ()) -> bool:
    """True when the page uses this word or another spelling of the same feature."""
    return any(term_in_text(text, spelling) for spelling in _spellings(term, groups))


def lookup_terms(terms: list[str], groups: tuple[frozenset[str], ...] = ()) -> list[str]:
    """Expand each term to the spellings search should look for, without duplicates."""
    lookup: list[str] = []
    for term in terms:
        for spelling in sorted(_spellings(term, groups)):
            if spelling not in lookup:
                lookup.append(spelling)
    return lookup


def _content_matches(term: str):
    """SQL regex for a whole word, including the PDF ligature form of fi and fl."""
    variants = {term, term.replace("fi", "fi").replace("fl", "fl")}
    return or_(*[ChunkRow.content.op("~*")(rf"(^|[^[:alnum:]]){variant}([^[:alnum:]]|$)") for variant in variants])


def _lexical_rows(session: Session, filters: list, distance, terms: list[str], limit: int):
    """Chunks that contain a content word, ordered by vector distance.

    The limit is wider than the usual candidate count so a later manual is not dropped
    just because another manual's chunks hashed closer.
    """
    # One page per manual is chosen later. A global "nearest 20 chunks" cut drops a device whose
    # only spelling, such as BLE, sits farther from the question vector.
    distance_col = distance.label("distance")
    rows = session.execute(
        select(ChunkRow, DocumentRow, distance_col)
        .join(DocumentRow, DocumentRow.id == ChunkRow.document_id)
        .where(*filters, or_(*[_content_matches(term) for term in terms]))
        .order_by(distance_col)
        .limit(limit * 4)
    ).all()
    return [(chunk, document, float(distance_value)) for chunk, document, distance_value in rows]


def _word_terms(terms: list[str]) -> list[str]:
    """Drop compounds that were built by joining two other terms, such as canbus from can and bus."""
    joined = {left + right for left in terms for right in terms}
    return [term for term in terms if term not in joined]


def _best_per_document(rows: list[tuple], terms: list[str], groups: tuple[frozenset[str], ...]) -> list[tuple]:
    """Keep the strongest chunk of each manual. An affirmative mention outranks a nearby negation."""
    words = _word_terms(terms)
    # A multi-word question must hit at least half of its words, or the joined
    # form (CAN + bus matches CANbus). One stray word such as "fleet" inside
    # "fleets" is not enough.
    needed = max(1, (len(words) + 1) // 2)
    best: dict[UUID, tuple[int, tuple]] = {}
    for row in rows:
        chunk, _document, distance_value = row
        word_hits = sum(concept_in_text(chunk.content, term, groups) for term in words)
        compound_hits = sum(concept_in_text(chunk.content, term, groups) for term in terms if term not in words)
        if any(len(term) >= 8 and not concept_in_text(chunk.content, term, groups) for term in words):
            continue
        if word_hits < needed and compound_hits == 0:
            continue
        score = word_hits + compound_hits
        if _affirmative_mention(chunk.content, terms, groups):
            score += 10
        current = best.get(chunk.document_id)
        if current is None or score > current[0] or (score == current[0] and distance_value < current[1][2]):
            best[chunk.document_id] = (score, row)
    ordered = sorted(best.values(), key=lambda item: (-item[0], item[1][2]))
    return [item[1] for item in ordered]


def _library(session: Session, tenant_id: str) -> list[DocumentRow]:
    """Every manual in the tenant. Used to notice when the question names one of them."""
    return list(
        session.scalars(select(DocumentRow).where(DocumentRow.tenant_id == tenant_id)).all()
    )


def _rrf(rankings: list[list[UUID]], k: int) -> dict[UUID, float]:
    """Reciprocal rank fusion. A chunk in both the vector list and the text list scores higher."""
    scores: dict[UUID, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores
