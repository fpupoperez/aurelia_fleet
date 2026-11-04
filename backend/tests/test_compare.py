"""Supply ranges are compared with the number in the question."""

from app.retrieval.compare import parse_constraint, reading_qualifies, readings_in


def test_more_than_12v_uses_the_upper_supply_bound() -> None:
    constraint = parse_constraint("Ruptela devices that support more than 12V")
    assert constraint is not None
    assert constraint.op == "gt"
    assert constraint.number == 12
    assert constraint.unit == "V"
    wide = readings_in("Power supply range 9 – 32 V DC Internal battery LiPo 3.7 V")
    supply = [reading for reading in wide if reading.supply]
    assert supply
    assert reading_qualifies(supply[0], constraint)
    limit = readings_in("Do not exceed 12 V on the supply rail.")
    assert limit[0].supply
    assert not reading_qualifies(limit[0], constraint)


def test_more_than_60_degrees_uses_the_operating_range() -> None:
    constraint = parse_constraint("Device suport more than 60 degrees")
    assert constraint is not None
    assert constraint.op == "gt"
    assert constraint.number == 60
    assert constraint.unit == "°C"
    hot = readings_in("Temperature Operating: -30 °C to +70 °C Ordering information")
    assert hot[0].operating
    assert reading_qualifies(hot[0], constraint)
    limit = readings_in("Temperature Operating: -20 to +60 °C Storage: -20 to +45 °C")
    assert limit[0].high == 60
    assert not reading_qualifies(limit[0], constraint)
    wider = readings_in("Operating (without battery): -20 to +70 °C Storage (without battery): -20 to +70 °C")
    assert [reading.high for reading in wider] == [70]
    stored = readings_in("Storage: -20 to +80 °C")
    assert stored == []


def test_a_plain_fact_question_is_not_a_comparison() -> None:
    assert parse_constraint("What is the minimum brake pad thickness on the HX-200?") is None


def test_higher_voltage_asks_for_the_maximum_supply() -> None:
    from app.retrieval.compare import parse_extreme

    question = "what's the higher voltage our Ruptela devices support?"
    assert parse_constraint(question) is None
    assert parse_extreme(question) == ("max", "V")
    assert parse_extreme("Ruptela devices that support more than 12V") is None
    wide = readings_in("Power supply range 9 – 32 V DC")
    narrow = readings_in("Power supply 9-30 V DC")
    assert wide[0].high == 32
    assert wide[0].low == 9
    assert narrow[0].high == 30
    assert narrow[0].supply
