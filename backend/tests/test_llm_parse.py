"""The model payload must match the answer schema."""

import pytest

from app.providers.parsing import AnswerParseError, parse_llm_answer


def test_parses_json_object() -> None:
    parsed = parse_llm_answer(
        '{"answered": true, "answer": "4.2 mm.", "citations": [], "confidence": "high", "refusalReason": null}'
    )
    assert parsed.answered
    assert parsed.answer == "4.2 mm."


def test_parses_refusal() -> None:
    parsed = parse_llm_answer(
        '{"answered": false, "answer": "I do not know.", "citations": [], "confidence": "none", "refusalReason": "missing"}'
    )
    assert parsed.answered is False
    assert parsed.refusal_reason == "missing"


def test_parses_fenced_json() -> None:
    parsed = parse_llm_answer('```json\n{"answered": false, "answer": "no", "confidence": "none"}\n```')
    assert parsed.confidence.value == "none"


def test_nested_answer_becomes_lines() -> None:
    parsed = parse_llm_answer(
        """
        {
          "answered": true,
          "answer": {"brakes": {"min_pad_thickness": {"value": 4.2, "unit": "mm"}}},
          "citations": [],
          "confidence": "high",
          "refusalReason": ""
        }
        """
    )
    assert parsed.answered
    assert parsed.answer == "Brakes\nMin pad thickness: 4.2 mm"
    assert parsed.refusal_reason is None


def test_malformed_payload_raises() -> None:
    with pytest.raises(AnswerParseError):
        parse_llm_answer("not json")


def test_wrong_shape_raises() -> None:
    with pytest.raises(AnswerParseError):
        parse_llm_answer('{"answer": "missing required fields"}')
