from coach.core.load import Load, from_hevy_kg


def test_hevy_kg_doubles_a_per_hand_load_and_converts_pounds() -> None:
    assert Load(15, "per_hand_x2").hevy_kg("kg") == 30
    assert Load(25, "per_hand_x2").hevy_kg("lb") == round(50 * 0.45359237, 4)
    assert Load(120, "total").hevy_kg("lb") == 54.4311


def test_a_kg_athlete_reads_the_logged_kilograms() -> None:
    assert from_hevy_kg(102.5, "total", "kg") == Load(102.5, "total")


def test_a_lb_athlete_reads_pounds() -> None:
    assert from_hevy_kg(45.359237, "total", "lb") == Load(100, "total")


def test_per_hand_doubled_reads_the_hand() -> None:
    assert from_hevy_kg(50, "per_hand_x2", "kg") == Load(25, "per_hand_x2")


def test_a_mode_with_no_load_reads_none() -> None:
    assert from_hevy_kg(10, "bodyweight", "kg") is None
    assert from_hevy_kg(None, "total", "kg") is None


def test_a_pound_load_survives_the_round_trip_through_hevy_kilograms() -> None:
    for quarter in range(0, 571):
        for mode in ("total", "per_hand_x2"):
            load = Load(quarter / 4, mode)
            assert from_hevy_kg(load.hevy_kg("lb"), mode, "lb") == load
