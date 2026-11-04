"""Reading-order output that adds words is discarded."""

from app.core.config import Settings
from app.ingest.extract import PageText
from app.ingest.pipeline import _reading_order
from app.providers import Completion


class _Inventing:
    model_name = "fake"

    def complete(self, *, system: str, user: str) -> Completion:
        del system, user
        return Completion(text="This page invents a torque of 999 Nm.", input_tokens=1, output_tokens=4, model="fake")


def test_reading_order_keeps_geometry_when_the_model_adds_words(monkeypatch) -> None:
    monkeypatch.setattr("app.ingest.pipeline.build_chat_provider", lambda settings: _Inventing())
    pages = [PageText(1, "Left column brake inspection.", True, "Left column brake inspection.")]
    settings = Settings(pdf_reading_order="llm", llm_max_attempts=1, llm_retry_backoff_seconds=0)
    result = _reading_order(pages, settings)
    assert result[0].text == "Left column brake inspection."
