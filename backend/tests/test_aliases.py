"""Alias words are normalized before they are stored."""

import pytest

from app.domain.errors import DomainError
from app.services.aliases import normalize_terms


def test_terms_are_folded_and_deduplicated() -> None:
    assert normalize_terms([" Bluetooth ", "BLE", "ble"]) == ["bluetooth", "ble"]


def test_a_phrase_is_rejected() -> None:
    with pytest.raises(DomainError):
        normalize_terms(["bluetooth le", "ble"])
