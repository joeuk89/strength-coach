from coach.core.load import Load


def test_hevy_kg_doubles_a_per_hand_load_and_converts_pounds() -> None:
    assert Load(15, "per_hand_x2").hevy_kg("kg") == 30
    assert Load(25, "per_hand_x2").hevy_kg("lb") == round(50 * 0.45359237, 4)
    assert Load(120, "total").hevy_kg("lb") == 54.4311
