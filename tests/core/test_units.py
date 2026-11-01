from coach.core.units import to_kg


def test_kilograms_pass_through_and_pounds_convert_to_hevy_kilograms() -> None:
    assert to_kg(120, "kg") == 120
    assert to_kg(120, "lb") == 54.431
    assert to_kg(45, "lb") == 20.412
