"""Parse the structured answer the chat provider must return."""

import json
import re

from pydantic import ValidationError

from app.schemas.answers import LlmAnswer


def _prose(value: object) -> str:
    """Turn a nested JSON answer into lines a technician can read."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(piece for piece in (_prose(item) for item in value) if piece)
    if isinstance(value, dict):
        if "value" in value and not any(isinstance(item, (dict, list)) for item in value.values()):
            unit = value.get("unit") or ""
            return f"{value['value']} {unit}".strip()
        lines: list[str] = []
        for key, item in value.items():
            label = str(key).replace("_", " ").capitalize()
            rendered = _prose(item)
            if isinstance(item, dict) and "value" not in item:
                lines.append(f"{label}\n{rendered}")
            else:
                lines.append(f"{label}: {rendered}")
        return "\n".join(lines)
    return str(value)


class AnswerParseError(Exception):
    """The model text was not the JSON object the prompt required."""
    def __init__(self, message: str) -> None:
        """Keep the reason the parser rejected the payload."""
        super().__init__(message)
        self.message = message


def parse_llm_answer(payload: str) -> LlmAnswer:
    """Validate a model payload. Accepts a raw object or a fenced JSON block."""
    text = payload.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AnswerParseError("The model did not return a JSON object.")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AnswerParseError("The model returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise AnswerParseError("The model JSON must be an object.")
    answer = data.get("answer")
    if isinstance(answer, (dict, list)):
        data["answer"] = _prose(answer)
    if data.get("refusalReason") == "":
        data["refusalReason"] = None
    try:
        return LlmAnswer.model_validate(data)
    except ValidationError as exc:
        raise AnswerParseError(f"The model JSON does not match the answer schema: {exc.errors()[0]['msg']}") from exc
