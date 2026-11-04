"""Model and maker questions are answered from metadata."""

from app.retrieval.catalog import CatalogEntry, _answer_text


ENTRIES = [
    CatalogEntry("Pro-5S", "Ruptela", "Ruptela pro-5S"),
    CatalogEntry("HCV5", "Ruptela", "HCV5"),
    CatalogEntry("HX-200", "Aurelia", "HX-200 brake service"),
    CatalogEntry("TU-9", "Aurelia", "TU-9 antenna installation"),
]


def test_maker_models_are_listed_without_a_model_call() -> None:
    text = _answer_text("Which Ruptela models do we have?", ENTRIES)
    assert text is not None
    assert "Pro-5S" in text
    assert "HCV5" in text
    assert "HX-200" not in text


def test_who_makes_a_model() -> None:
    assert _answer_text("Who makes the Pro-5S?", ENTRIES) == "Pro-5S is made by Ruptela."


def test_a_fact_question_is_not_a_catalog_lookup() -> None:
    assert _answer_text("Devices supporting fleet efficiency optimization", ENTRIES) is None
    assert _answer_text("What is the minimum brake pad thickness on the HX-200?", ENTRIES) is None
