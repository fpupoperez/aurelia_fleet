"""Answer numeric comparisons from the supply values printed in the manuals."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChunkRow, DocumentRow
from app.schemas.answers import AnswerData, Citation, Confidence

_WORD = re.compile(r"[a-z0-9]+")
_CONSTRAINT = re.compile(
    r"(?P<op>more than|greater than|higher than|above|over|at least|less than|lower than|under|below|at most|m[aá]s de|menos de)"
    r"\s+(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>°\s*c|degrees?|grados?|celsius|celcius|v|volt|volts|nm|mm)\b",
    re.IGNORECASE,
)
_RANGE = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*[-–—]\s*(?P<high>\d+(?:\.\d+)?)\s*(?P<unit>V|Nm|mm)\b",
    re.IGNORECASE,
)
_TEMP_RANGE = re.compile(
    r"(?P<low>[+-]?\d+(?:\.\d+)?)\s*(?:°\s*C)?"
    r"\s+(?:to|hasta|a)\s+"
    r"(?P<high>[+-]?\d+(?:\.\d+)?)\s*°\s*C",
    re.IGNORECASE,
)
_MAXIMUM = re.compile(
    r"(?:do not exceed|not exceed|maximum of|max\.?)\s*(?P<high>\d+(?:\.\d+)?)\s*(?P<unit>V|Nm|mm)\b",
    re.IGNORECASE,
)
_SUPPLY = re.compile(
    r"power supply|supply range|supply input|supply rail|suministro|alimentaci[oó]n",
    re.IGNORECASE,
)
_OPERATING = re.compile(
    r"operating|operaci[oó]n|without battery|sin bater[ií]a",
    re.IGNORECASE,
)
_NOT_OPERATING = re.compile(
    r"storage|almacenamiento|charg|cargando|discharg|descarga",
    re.IGNORECASE,
)
_UNITS = {
    "v": "V",
    "volt": "V",
    "volts": "V",
    "nm": "Nm",
    "mm": "mm",
    "degree": "°C",
    "degrees": "°C",
    "grado": "°C",
    "grados": "°C",
    "celsius": "°C",
    "celcius": "°C",
    "°c": "°C",
    "° c": "°C",
}
_GREATER = {"more than", "greater than", "higher than", "above", "over"}
_AT_LEAST = {"at least"}
_PHRASE = {"gt": "more than", "gte": "at least", "lt": "less than"}
_EXTREME = re.compile(
    r"\b(?P<op>higher|highest|maximum|max|lower|lowest|minimum|min|mayor|m[aá]ximo|menor|m[ií]nimo)\b",
    re.IGNORECASE,
)
_VOLTAGE_WORD = re.compile(r"\b(voltages?|volts?|tensi[oó]n|voltaje)\b", re.IGNORECASE)
_TEMPERATURE_WORD = re.compile(r"\b(temperatures?|temp|grados|degrees)\b", re.IGNORECASE)
_MINIMUM_WORDS = {"lower", "lowest", "minimum", "min", "menor", "mínimo", "minimo"}


@dataclass(frozen=True)
class Constraint:
    """A bound parsed from the question, such as greater than 12 V."""
    op: str
    number: float
    unit: str


@dataclass(frozen=True)
class Reading:
    """One range printed in a chunk. Supply and operating flags decide whether it counts."""
    high: float
    unit: str
    excerpt: str
    supply: bool
    operating: bool = False
    low: float | None = None


def parse_constraint(question: str) -> Constraint | None:
    """Parse 'more than 12 V' or 'menos de 60 grados'. None when the question has no numbered bound."""
    match = _CONSTRAINT.search(question)
    if match is None:
        return None
    op = match.group("op").lower()
    if op in _GREATER or op in {"más de", "mas de"}:
        kind = "gt"
    elif op in _AT_LEAST:
        kind = "gte"
    else:
        kind = "lt"
    unit_key = re.sub(r"\s+", " ", match.group("unit").lower())
    return Constraint(kind, float(match.group("number")), _UNITS[unit_key])


def readings_in(text: str) -> list[Reading]:
    """Find supply ranges and operating temperature ranges. Storage and charging ranges are skipped."""
    found: list[Reading] = []
    for pattern in (_RANGE, _MAXIMUM):
        for match in pattern.finditer(text):
            start = max(0, match.start() - 90)
            window = text[start : match.end() + 48]
            supply_at = _SUPPLY.search(window)
            if supply_at is not None and supply_at.start() < (match.start() - start):
                window = window[supply_at.start() :]
            excerpt = " ".join(window.split())
            found.append(
                Reading(
                    high=float(match.group("high")),
                    unit=match.group("unit").upper() if match.group("unit").lower() != "nm" else "Nm",
                    excerpt=excerpt,
                    supply=_SUPPLY.search(window) is not None,
                    low=float(match.group("low")) if match.groupdict().get("low") else None,
                )
            )
    for match in _TEMP_RANGE.finditer(text):
        label = _label_before(text, match.start())
        if _NOT_OPERATING.search(label):
            continue
        if _OPERATING.search(label) is None:
            continue
        excerpt = " ".join(f"{label}{match.group(0)}".split())
        found.append(
            Reading(
                high=float(match.group("high")),
                unit="°C",
                excerpt=excerpt,
                supply=False,
                operating=True,
                low=float(match.group("low")),
            )
        )
    return found


def _label_before(text: str, start: int) -> str:
    """The words in front of a temperature range, where 'operating' or 'storage' usually sits."""
    previous = text.rfind("°", 0, start)
    cut = previous + 1 if previous >= 0 and start - previous < 80 else max(0, start - 70)
    return re.sub(r"^C\b", "", text[cut:start])


def reading_qualifies(reading: Reading, constraint: Constraint) -> bool:
    """True when this printed upper bound meets the question's comparison."""
    if reading.unit.lower() != constraint.unit.lower():
        return False
    if constraint.op == "gt":
        return reading.high > constraint.number
    if constraint.op == "gte":
        return reading.high >= constraint.number
    return reading.high < constraint.number


def parse_extreme(question: str) -> tuple[str, str] | None:
    """A question such as 'the higher voltage' asks for the max, not 'higher than 12 V'."""
    if _CONSTRAINT.search(question):
        return None
    match = _EXTREME.search(question)
    if match is None:
        return None
    kind = "min" if match.group("op").lower() in _MINIMUM_WORDS else "max"
    if _VOLTAGE_WORD.search(question):
        return kind, "V"
    if _TEMPERATURE_WORD.search(question):
        return kind, "°C"
    return None


def answer_comparison(session: Session, *, tenant_id: str, question: str) -> AnswerData | None:
    """Answer a numeric comparison or a highest/lowest question. None when the question is not one of those."""
    constraint = parse_constraint(question)
    extreme = parse_extreme(question) if constraint is None else None
    if constraint is None and extreme is None:
        return None
    documents = session.execute(
        select(DocumentRow).where(DocumentRow.tenant_id == tenant_id)
    ).scalars().all()
    maker = _named_maker(question, {document.maker for document in documents if document.maker})
    allowed = {document.id for document in documents if not maker or document.maker.lower() == maker.lower()}
    if not allowed:
        return None
    rows = session.execute(
        select(ChunkRow, DocumentRow)
        .join(DocumentRow, DocumentRow.id == ChunkRow.document_id)
        .where(ChunkRow.document_id.in_(allowed))
    ).all()
    if constraint is not None:
        unit = constraint.unit
    else:
        assert extreme is not None
        unit = extreme[1]
    chosen: dict[str, tuple[Reading, ChunkRow, DocumentRow]] = {}
    for chunk, document in rows:
        supply_readings = [
            reading
            for reading in readings_in(chunk.content)
            if (unit == "°C" and reading.operating) or (unit != "°C" and reading.supply)
        ]
        for reading in supply_readings:
            if reading.unit.lower() != unit.lower():
                continue
            current = chosen.get(document.equipment_model)
            if current is None or _prefer_reading(reading, current[0], extreme):
                chosen[document.equipment_model] = (reading, chunk, document)
    if not chosen:
        return None
    if extreme is not None:
        return _answer_extreme(extreme, chosen, maker)
    assert constraint is not None
    matches = [
        (reading, chunk, document)
        for reading, chunk, document in chosen.values()
        if reading_qualifies(reading, constraint)
    ]
    matches.sort(key=lambda item: item[2].equipment_model)
    if not matches:
        checked = ", ".join(sorted(chosen))
        phrase = _PHRASE[constraint.op]
        return AnswerData(
            answered=False,
            answer=(
                f"None of the {_aspect(constraint)} limits are {phrase} {constraint.number:g} {constraint.unit}. "
                f"Checked {checked}."
            ),
            citations=[_citation(reading, chunk, document) for reading, chunk, document in chosen.values()],
            confidence=Confidence.high,
            refusal_reason=f"No {_aspect(constraint)} range is {phrase} {constraint.number:g} {constraint.unit}.",
        )
    lines = [
        f"{document.equipment_model} ({document.maker}): {reading.excerpt}" if document.maker else f"{document.equipment_model}: {reading.excerpt}"
        for reading, _chunk, document in matches
    ]
    subject = f"{maker} devices" if maker else "Devices"
    phrase = _PHRASE[constraint.op]
    return AnswerData(
        answered=True,
        answer=(
            f"{subject} whose {_aspect(constraint)} is {phrase} {constraint.number:g} {constraint.unit}:\n"
            + "\n".join(lines)
        ),
        citations=[_citation(reading, chunk, document) for reading, chunk, document in matches],
        confidence=Confidence.high,
        refusal_reason=None,
    )


def _prefer_reading(reading: Reading, current: Reading, extreme: tuple[str, str] | None) -> bool:
    """True when this reading is a better extreme than the one already chosen for the same manual."""
    if extreme is not None and extreme[0] == "min":
        left = reading.low if reading.low is not None else reading.high
        right = current.low if current.low is not None else current.high
        return left < right
    return reading.high > current.high


def _answer_extreme(
    extreme: tuple[str, str],
    chosen: dict[str, tuple[Reading, ChunkRow, DocumentRow]],
    maker: str | None,
) -> AnswerData | None:
    """State the max or min and name only the devices whose excerpt shows that value."""
    kind, unit = extreme
    if kind == "min":
        usable = [item for item in chosen.values() if item[0].low is not None]
        if not usable:
            return None
        target = min(item[0].low for item in usable if item[0].low is not None)
        winners = [item for item in usable if item[0].low == target]
        label = "lowest supply voltage" if unit == "V" else "lowest operating temperature"
    else:
        target = max(item[0].high for item in chosen.values())
        winners = [item for item in chosen.values() if item[0].high == target]
        label = "highest supply voltage" if unit == "V" else "highest operating temperature"
    winners.sort(key=lambda item: item[2].equipment_model)
    subject = f"{maker} devices" if maker else "the devices"
    lines = [
        f"{document.equipment_model} ({document.maker}): {reading.excerpt}"
        if document.maker
        else f"{document.equipment_model}: {reading.excerpt}"
        for reading, _chunk, document in winners
    ]
    winner_models = {document.equipment_model for _reading, _chunk, document in winners}
    others = [item for item in chosen.values() if item[2].equipment_model not in winner_models]
    if kind == "max" and others:
        grouped: dict[float, list[str]] = {}
        for reading, _chunk, document in others:
            grouped.setdefault(reading.high, []).append(document.equipment_model)
        rest = "; ".join(
            f"{value:g} {unit}: {', '.join(sorted(models))}"
            for value, models in sorted(grouped.items(), reverse=True)
        )
        lines.append(f"Other upper limits: {rest}.")
    return AnswerData(
        answered=True,
        answer=f"The {label} {subject} support is {target:g} {unit}.\n" + "\n".join(lines),
        citations=[
            _citation(reading, chunk, document) for reading, chunk, document in [*winners, *others]
        ],
        confidence=Confidence.high,
        refusal_reason=None,
    )


def _aspect(constraint: Constraint) -> str:
    """The noun used in the sentence, such as supply voltage or operating temperature."""
    if constraint.unit == "°C":
        return "operating temperature"
    return "supply"


def _named_maker(question: str, makers: set[str]) -> str | None:
    """A maker name that appears in the question, so other makers' ranges are left out."""
    words = set(_WORD.findall(question.lower()))
    for maker in sorted(makers, key=len, reverse=True):
        tokens = _WORD.findall(maker.lower())
        if tokens and all(token in words for token in tokens):
            return maker
    return None


def _citation(reading: Reading, chunk: ChunkRow, document: DocumentRow) -> Citation:
    """The chunk that contained the winning range, quoted as the citation excerpt."""
    return Citation(
        chunk_id=chunk.id,
        document_id=document.id,
        title=document.title,
        equipment_model=document.equipment_model,
        page=chunk.page,
        excerpt=reading.excerpt,
    )
