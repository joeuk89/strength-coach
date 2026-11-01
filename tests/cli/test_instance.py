from pathlib import Path

from support.instances import ATHLETE, an_instance

from coach.cli.instance import load_instance

PIN = "0.3.0"


def test_a_loaded_instance_carries_the_athletes_units_and_cadence(tmp_path: Path) -> None:
    athlete = {**ATHLETE, "units": "lb", "bodyweight_units": "kg", "checkin_cadence_days": 7}
    root = an_instance(tmp_path, pin=PIN, athlete=athlete)

    instance, _ = load_instance(root, PIN)

    assert instance.units == "lb"
    assert instance.bodyweight_units == "kg"
    assert instance.checkin_cadence_days == 7
