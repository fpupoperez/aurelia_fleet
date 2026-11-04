"""Questions that name a library manual stay on that manual."""

from app.retrieval.search import (
    _affirmative_mention,
    asks_which_devices,
    concept_in_text,
    feature_terms,
    is_name_only_question,
    question_names_document,
    term_in_text,
)


def test_product_name_matches_the_uploaded_manual() -> None:
    assert question_names_document(
        "Ruptela CFA-FMS-BLE",
        title="Ruptela CFA-FMS-BLE",
        equipment_model="CFA-FMS-BLE",
    )


def test_unrelated_question_does_not_name_another_manual() -> None:
    assert not question_names_document(
        "What is the cabin paint color of the ZX-1?",
        title="HX-200 hydraulic service",
        equipment_model="HX-200",
    )


def test_short_product_name_matches_that_manual() -> None:
    assert question_names_document(
        "Pro-5S",
        title="Ruptela pro-5S",
        equipment_model="Pro-5S",
    )
    assert not question_names_document(
        "Pro-5S",
        title="Ruptela CFA-FMS-BLE",
        equipment_model="CFA-FMS-BLE",
    )


def test_free_question_keeps_the_phrase_words() -> None:
    terms = feature_terms("Devices supporting fleet efficiency optimization")
    assert "fleet" in terms
    assert "efficiency" in terms
    assert "optimization" in terms
    assert term_in_text("Fleet efficiency optimization Driver behavior monitoring", "efficiency")
    assert not term_in_text("Real-time monitoring of fleets and cargo", "fleet")
    assert term_in_text("Fleet efficiency optimization", "efficiency")


def test_can_bus_terms_match_a_compound_and_a_separate_word() -> None:
    terms = feature_terms("Which devices support CAN bus?")
    assert "can" in terms
    assert "canbus" in terms
    assert term_in_text("CANbus data reading", "canbus")
    assert term_in_text("CAN output: 1 x CAN 2.0", "can")
    assert not term_in_text("CANbus data reading", "can")


def test_a_typo_in_supporting_does_not_hide_nb_iot() -> None:
    terms = feature_terms("Devices supoorting nb-iot")
    assert "supoorting" not in terms
    assert "supporting" not in terms
    assert "iot" in terms
    assert "nbiot" in terms
    assert asks_which_devices("Devices supoorting nb-iot")
    assert term_in_text("LTE Cat M1/NB-IoT (4G) network", "iot")
    assert _affirmative_mention("available with the LTE Cat M1/NB-IoT (4G) network", ["iot"], ())
    assert not _affirmative_mention("no está disponible para la opción LTE Cat M1/NB-IoT", ["iot"], ())
    assert "optimization" in feature_terms("Devices supporting fleet efficiency optimization")


def test_bluetooth_and_ble_are_one_feature() -> None:
    terms = feature_terms("Devices supporting bluetooth")
    assert terms == ["bluetooth"]
    assert asks_which_devices("Devices supporting bluetooth")
    groups = (frozenset({"bluetooth", "ble"}),)
    assert concept_in_text("Key values: BLE 5.1", "bluetooth", groups)
    assert concept_in_text("broadcasts basic parameters via Bluetooth LE", "ble", groups)
    assert not concept_in_text("assembled", "ble", groups)


def test_a_one_letter_typo_uses_the_alias_group() -> None:
    groups = (frozenset({"unplug", "disconnection", "desconexion", "desconexiones"}),)
    terms = feature_terms("Devices able to detect battery desconnection")
    assert "desconnection" in terms
    assert "able" not in terms
    assert "detect" not in terms
    assert concept_in_text("Security unplug detection, backup battery", "desconnection", groups)
    assert concept_in_text("desconexiones y manipulaciones, batería de respaldo", "desconnection", groups)
    assert not concept_in_text("Internal battery LiPo 3.7 V", "desconnection", groups)


def test_name_only_question_has_no_extra_subject_words() -> None:
    titles = ["Ruptela pro-5S", "HX-200 brake service"]
    models = ["Pro-5S", "HX-200"]
    assert is_name_only_question("Pro-5S", titles=titles, equipment_models=models)
    assert is_name_only_question("HX-200", titles=titles, equipment_models=models)
    assert not is_name_only_question(
        "What is the minimum brake pad thickness on the HX-200?",
        titles=titles,
        equipment_models=models,
    )
