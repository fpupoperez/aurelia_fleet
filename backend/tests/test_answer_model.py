"""A real chat model writes the answer. The fake provider keeps the direct reading."""

import json
from uuid import UUID

from app.core.config import Settings
from app.providers import Completion
from app.retrieval.search import SearchResult
from app.schemas.answers import AnswerData, AskRequest, Citation, Confidence
from app.services.answers import ask

CHUNK = UUID("00000000-0000-0000-0000-0000000000aa")
DOCUMENT = UUID("00000000-0000-0000-0000-0000000000bb")


def _citation() -> Citation:
    return Citation(
        chunk_id=CHUNK,
        document_id=DOCUMENT,
        title="HCV5 datasheet",
        equipment_model="HCV5",
        page=2,
        excerpt="Power supply range 9 – 32 V DC",
    )


def _structured() -> AnswerData:
    return AnswerData(
        answered=True,
        answer="The highest supply voltage Ruptela devices support is 32 V.",
        citations=[_citation()],
        confidence=Confidence.high,
        refusal_reason=None,
    )


class _Chat:
    model_name = "llama"

    def __init__(self) -> None:
        self.user = ""

    def complete(self, *, system: str, user: str) -> Completion:
        del system
        self.user = user
        payload = {
            "answered": True,
            "answer": "Ruptela devices support up to 32 V, from a 9–32 V supply.",
            "citations": [{"chunkId": str(CHUNK), "excerpt": "Power supply range 9 – 32 V DC"}],
            "confidence": "high",
            "refusalReason": None,
        }
        return Completion(text=json.dumps(payload), input_tokens=10, output_tokens=10, model="llama")


def test_the_fake_provider_returns_the_direct_reading(monkeypatch) -> None:
    monkeypatch.setattr("app.services.answers.answer_catalog", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.answers.answer_comparison", lambda *args, **kwargs: _structured())
    monkeypatch.setattr(
        "app.services.answers.search",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("search should not run")),
    )
    result = ask(
        None,  # type: ignore[arg-type]
        Settings(llm_provider="fake"),
        tenant_id="aurelia",
        body=AskRequest(question="what's the higher voltage our Ruptela devices support?"),
    )
    assert result.answer.startswith("The highest supply voltage")


def test_a_real_model_writes_the_answer_from_the_readings(monkeypatch) -> None:
    chat = _Chat()
    monkeypatch.setattr("app.services.answers.answer_catalog", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.answers.answer_comparison", lambda *args, **kwargs: _structured())
    monkeypatch.setattr(
        "app.services.answers.search",
        lambda *args, **kwargs: SearchResult([], True, None, None, 0),
    )
    monkeypatch.setattr("app.services.answers.build_embedding_provider", lambda settings: object())
    monkeypatch.setattr("app.services.answers.build_chat_provider", lambda settings: chat)
    result = ask(
        None,  # type: ignore[arg-type]
        Settings(llm_provider="litellm", llm_model="openai/llama3.1:8b", llm_api_base="http://localhost:11434/v1"),
        tenant_id="aurelia",
        body=AskRequest(question="what's the higher voltage our Ruptela devices support?"),
    )
    assert "32 V" in result.answer
    assert "9 – 32 V" in chat.user
    assert result.citations[0].equipment_model == "HCV5"
