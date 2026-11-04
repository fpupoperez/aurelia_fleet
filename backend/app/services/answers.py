"""Answer a question from the manuals.

Order: metadata catalog, printed voltage or temperature readings, then hybrid search.
With ``LLM_PROVIDER=fake`` a comparison or a word match is returned as-is.
With ``litellm`` those readings become notes, and the chat model writes the sentences.
A citation is kept only when its chunk id was in the evidence sent to the model.
"""

from __future__ import annotations

import logging
import re
import time

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProviderUnavailable
from app.core.telemetry import record_llm, record_retrieval, span
from app.domain.errors import DomainError
from app.providers import (
    SYSTEM_PROMPT,
    asks_for_prompt,
    build_chat_provider,
    build_embedding_provider,
    call_with_retries,
)
from app.providers.parsing import AnswerParseError, parse_llm_answer
from app.retrieval.catalog import answer_catalog
from app.retrieval.compare import answer_comparison
from app.retrieval.search import Hit, SearchResult, feature_terms, lookup_terms, search
from app.schemas.answers import AnswerData, AskRequest, Citation, Confidence

logger = logging.getLogger(__name__)

_REFUSAL = "The manuals do not contain enough evidence to answer."
_UNAVAILABLE = "The model is unavailable. Here are the matching passages."


def _uses_model(settings: Settings) -> bool:
    """A real chat model writes the prose. The fake provider keeps the direct answers."""
    return settings.llm_provider != "fake"


def ask(
    session: Session,
    settings: Settings,
    *,
    tenant_id: str,
    body: AskRequest,
) -> AnswerData:
    """Run the ask path for one tenant and return a structured answer or a refusal."""
    if asks_for_prompt(body.question):
        return AnswerData(
            answered=False,
            answer=_REFUSAL,
            citations=[],
            confidence=Confidence.none,
            refusal_reason="The question asks for instructions that are not in the manuals.",
        )
    catalog = answer_catalog(session, tenant_id=tenant_id, question=body.question)
    if catalog is not None:
        return catalog
    compared = answer_comparison(session, tenant_id=tenant_id, question=body.question)
    real_model = _uses_model(settings)
    if compared is not None and not real_model:
        return compared
    embedder = build_embedding_provider(settings)
    started = time.perf_counter()
    with span(
        "retrieval.search",
        k=body.k,
        equipment_model=body.equipment_model or "",
        tenant_id=tenant_id,
    ) as current:
        result = search(
            session,
            settings=settings,
            embedder=embedder,
            tenant_id=tenant_id,
            question=body.question,
            equipment_model=body.equipment_model,
            k=body.k,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        current.set_attribute("candidate_count", result.candidate_count)
        current.set_attribute("abstained", result.abstained)
        current.set_attribute("duration_ms", duration_ms)
        if result.top_distance is not None:
            current.set_attribute("top_cosine_distance", result.top_distance)
        if result.fused_score is not None:
            current.set_attribute("fused_score", result.fused_score)
        record_retrieval(duration_ms, abstained=result.abstained)
    evidence = _evidence(result, compared if real_model else None)
    if not evidence:
        return AnswerData(
            answered=False,
            answer=_REFUSAL,
            citations=[],
            confidence=Confidence.none,
            refusal_reason=_REFUSAL,
        )
    if not real_model and result.text_match and not result.name_only:
        return _text_match_answer(body.question, result)
    citations = [_citation(hit) for hit in evidence]
    user = _user_message(
        body.question,
        evidence,
        name_only=result.name_only,
        feature_list=result.feature_list,
        text_match=result.text_match,
        synthesize=real_model,
        notes=compared.answer if real_model and compared is not None and compared.answered else "",
    )
    chat = build_chat_provider(settings)
    try:
        parsed, completion = _complete(chat, user, settings)
    except RuntimeError as exc:
        logger.warning("Chat provider failed: %s", exc)
        fallback = _direct_answer(body.question, compared, result)
        if fallback is not None:
            return fallback
        raise ProviderUnavailable(_UNAVAILABLE, session={}, citations=citations) from exc
    except DomainError:
        fallback = _direct_answer(body.question, compared, result)
        if fallback is not None:
            return fallback
        if evidence and (result.name_only or result.feature_list or result.text_match):
            logger.warning("Answer was unreadable; returning the manual passages.")
            return _passages_answer(citations)
        raise
    if (not parsed.answered or not parsed.answer.strip()) and compared is not None and compared.answered:
        return compared
    by_id = {hit.chunk_id: hit for hit in evidence}
    used: list[Citation] = []
    for item in parsed.citations:
        hit = by_id.get(item.chunk_id)
        if hit is not None and all(existing.chunk_id != hit.chunk_id for existing in used):
            used.append(_citation(hit))
    if evidence and (result.name_only or result.feature_list or result.text_match or compared is not None) and (
        not parsed.answered or not parsed.answer.strip()
    ):
        return _passages_answer(citations)
    if parsed.answered and not used:
        if evidence and (result.name_only or result.feature_list or result.text_match or compared is not None):
            return _passages_answer(citations, parsed.answer)
        return AnswerData(
            answered=False,
            answer=_REFUSAL,
            citations=citations,
            confidence=Confidence.none,
            refusal_reason="The model did not cite a retrieved passage.",
        )
    if not parsed.answered:
        return AnswerData(
            answered=False,
            answer=parsed.answer or _REFUSAL,
            citations=used,
            confidence=Confidence.none,
            refusal_reason=parsed.refusal_reason or _REFUSAL,
        )
    return AnswerData(
        answered=True,
        answer=parsed.answer,
        citations=used or citations,
        confidence=parsed.confidence,
        refusal_reason=None,
    )


def _complete(chat, user: str, settings: Settings):
    """Call the chat model and parse its JSON. One unreadable payload is retried, then 502."""
    started = time.perf_counter()
    with span("answer.generate", model=getattr(chat, "model_name", "")) as current:
        last_parse: AnswerParseError | None = None
        completion = None
        for attempt in range(2):
            try:
                completion = call_with_retries(chat, system=SYSTEM_PROMPT, user=user, settings=settings)
                parsed = parse_llm_answer(completion.text)
            except AnswerParseError as exc:
                last_parse = exc
                if attempt == 1:
                    raise DomainError(
                        "The model returned an unreadable answer.",
                        status_code=502,
                    ) from exc
                continue
            duration_ms = (time.perf_counter() - started) * 1000
            current.set_attribute("input_tokens", completion.input_tokens)
            current.set_attribute("output_tokens", completion.output_tokens)
            current.set_attribute("duration_ms", duration_ms)
            current.set_attribute("answered", parsed.answered)
            current.set_attribute("confidence", parsed.confidence.value)
            current.set_attribute("citation_count", len(parsed.citations))
            record_llm(
                duration_ms,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                model=completion.model,
            )
            return parsed, completion
        raise DomainError("The model returned an unreadable answer.", status_code=502) from last_parse


def _text_match_answer(question: str, result: SearchResult) -> AnswerData:
    """The words are already in the pages, so this does not wait for the chat model."""
    terms = lookup_terms(feature_terms(question), result.alias_groups)
    lines = []
    for hit in result.hits:
        label = f"{hit.equipment_model} ({hit.maker})" if hit.maker else hit.equipment_model
        lines.append(f"{label}: {_supporting_sentence(hit.content, terms)}")
    return AnswerData(
        answered=True,
        answer="\n".join(lines),
        citations=[_citation(hit) for hit in result.hits],
        confidence=Confidence.high,
        refusal_reason=None,
    )


def _supporting_sentence(content: str, terms: list[str]) -> str:
    """Return a short window around the first matching term, including PDF ligatures such as fi."""
    variants = []
    for term in terms:
        variants.append(term)
        ligature = term.replace("fi", "fi").replace("fl", "fl")
        if ligature != term:
            variants.append(ligature)
    pattern = "|".join(rf"(?:(?<=^)|(?<=[^a-z0-9])){re.escape(variant)}(?=[^a-z0-9]|$)" for variant in variants)
    matches = list(re.finditer(pattern, content, flags=re.IGNORECASE)) if pattern else []
    if not matches:
        return content.strip()[:180]
    start = max(0, matches[0].start() - 48)
    end = min(len(content), matches[-1].end() + 48)
    if end - start > 220:
        end = start + 220
    snippet = content[start:end].strip(" -\n")
    if start > 0 and " " in snippet:
        snippet = snippet.split(" ", 1)[1]
    return snippet


def _citation(hit: Hit) -> Citation:
    """Copy a search hit into the citation the API returns. The excerpt is the whole chunk."""
    return Citation(
        chunk_id=hit.chunk_id,
        document_id=hit.document_id,
        title=hit.title,
        equipment_model=hit.equipment_model,
        page=hit.page,
        excerpt=hit.content,
    )


def _evidence(result: SearchResult, compared: AnswerData | None) -> list[Hit]:
    """Prefer the passages a structured reading already selected, then the search hits."""
    if compared is not None and compared.citations:
        return [
            Hit(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                title=item.title,
                equipment_model=item.equipment_model,
                maker="",
                page=item.page,
                content=item.excerpt,
                distance=0.0,
                fused_score=1.0,
            )
            for item in compared.citations
        ]
    if result.abstained:
        return []
    return list(result.hits)


def _direct_answer(question: str, compared: AnswerData | None, result: SearchResult) -> AnswerData | None:
    """Use the checked reading or the quoted sentences when the chat model fails or refuses."""
    if compared is not None and compared.answered:
        return compared
    if result.text_match and result.hits and not result.name_only:
        return _text_match_answer(question, result)
    return None


def _user_message(
    question: str,
    hits: list[Hit],
    *,
    name_only: bool,
    feature_list: bool,
    text_match: bool,
    synthesize: bool = False,
    notes: str = "",
) -> str:
    """Build the user prompt. Passages sit inside untrusted_manual so they stay data, not orders.

    ``synthesize`` asks for prose and, when ``notes`` is set, forbids contradicting the checked reading.
    The other branches tell the fake overlap model which kind of question it is answering.
    """
    blocks = []
    for hit in hits:
        blocks.append(
            f"[chunk id={hit.chunk_id} page={hit.page} equipment={hit.equipment_model} title={hit.title}]\n"
            f"{hit.content}\n[/chunk]"
        )
    joined = "\n".join(blocks)
    if synthesize:
        instruction = (
            "Answer in plain sentences a technician can read. "
            "When the question asks for the highest or lowest value, state that value first, "
            "then name only the equipment whose excerpt shows that value."
        )
        if notes:
            instruction += f" Checked reading, which you must not contradict: {notes}"
    elif name_only:
        instruction = (
            "The question only names a product or device. Set answered to true. "
            "List every specification and procedure from every excerpt."
        )
    elif feature_list:
        instruction = (
            "The question asks which devices have a capability. Set answered to true. "
            "Name every equipment model whose excerpt mentions that capability, and quote the supporting phrase."
        )
    elif text_match:
        instruction = (
            "The excerpts contain the words from the question. Set answered to true. "
            "Name the equipment and quote the supporting phrase."
        )
    else:
        instruction = ""
    prefix = f"Question: {question}\n{instruction}\n\n" if instruction else f"Question: {question}\n\n"
    return f"{prefix}<untrusted_manual>\n{joined}\n</untrusted_manual>"


def _passages_answer(citations: list[Citation], answer: str | None = None) -> AnswerData:
    """A bare product name is answered from the manuals even if the model refuses."""
    text = (answer or "").strip()
    if not text:
        parts = [f"{item.title}, page {item.page}: {item.excerpt.strip()}" for item in citations]
        text = "\n\n".join(parts)
    return AnswerData(
        answered=True,
        answer=text,
        citations=citations,
        confidence=Confidence.medium,
        refusal_reason=None,
    )
