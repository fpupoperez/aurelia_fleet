"""Maker and model are read from the manual."""

import fitz

from app.domain.errors import DomainError
from app.ingest.identity import TextSpan, heading_from_spans, read_identity, resolved_metadata
from app.schemas.documents import DocumentUploadRequest


def test_a_markdown_manual_names_its_model_and_maker() -> None:
    raw = (
        b"# HX-200 brake service\n\n"
        b"The Aurelia Hauler HX-200 service brake pad minimum thickness is 4.2 mm.\n"
    )
    identity = read_identity(raw, "hx-200-brakes.md", "text/markdown")
    assert identity.equipment_model == "HX-200"
    assert identity.maker == "Aurelia"
    assert identity.title == "HX-200 brake service"


def test_split_heading_letters_form_one_model() -> None:
    heading = heading_from_spans(
        [
            TextSpan("C", 28, 72, 88, 40),
            TextSpan("FA", 28, 90, 120, 40),
            TextSpan("Adapter", 28, 140, 230, 40),
            TextSpan("Key capabilities:", 14, 72, 220, 100),
        ]
    )
    assert heading == "CFA Adapter"


def test_a_datasheet_names_the_product_and_the_maker() -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 80), "Pro5S", fontsize=32)
    page.insert_text((72, 140), "Key values: visit www.ruptela.com", fontsize=11)
    spanish = document.new_page()
    spanish.insert_text((72, 72), "Copyright Ruptela", fontsize=10)
    raw = document.tobytes()
    document.close()
    identity = read_identity(raw, "ES-Pro5S-datasheet.pdf", "application/pdf")
    assert identity.equipment_model == "Pro5S"
    assert identity.maker == "Ruptela"
    assert identity.title == "Pro5S datasheet (ES)"
    assert identity.language == "es"


def test_a_typed_name_wins_and_a_blank_name_comes_from_the_file() -> None:
    identity = read_identity(
        b"# HX-200 brake service\n\nAurelia HX-200.\n",
        "brakes.md",
        "text/markdown",
    )
    typed = DocumentUploadRequest(equipmentModel="TU-9", title="Custom", maker="Aurelia")
    assert resolved_metadata(typed, identity)[:3] == ("TU-9", "Aurelia", "Custom")
    assert resolved_metadata(DocumentUploadRequest(), identity)[:3] == (
        "HX-200",
        "Aurelia",
        "HX-200 brake service",
    )


def test_a_file_without_a_model_asks_for_one() -> None:
    identity = read_identity(b"Torque the bolts.\n", "note.txt", "text/plain")
    try:
        resolved_metadata(DocumentUploadRequest(), identity)
    except DomainError as exc:
        assert exc.status_code == 422
        assert "equipment model" in exc.message
    else:
        raise AssertionError("expected a missing model to be rejected")
