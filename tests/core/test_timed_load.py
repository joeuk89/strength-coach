import datetime

from support.prescribe import a_line, a_request

from coach.core.exposure import Exposure, ExposureSet, Matched
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import ExerciseFacts, LinePrescription, Step
from coach.core.program.form import SetGroup

CARRY = "custom_farmers_carry"
FACTS = {CARRY: ExerciseFacts("per_hand_x2", "dumbbell", "carry")}
LINE = a_line(CARRY, SetGroup(3, "working", None, 30, 8), scheme="timed_load")


def carry(on: str, *seconds: int | None, load: float = 40, rpe: float | None = None) -> Exposure:
    return Exposure(
        workout_id=f"w-{on}",
        exercise_id=CARRY,
        date=datetime.date.fromisoformat(on),
        sets=tuple(
            ExposureSet(i, "working", Load(load, "per_hand_x2"), None, rpe, held)
            for i, held in enumerate(seconds)
        ),
        match=Matched("lower"),
    )


def derive(*exposures: Exposure) -> LinePrescription:
    return prescribe(a_request(LINE, exposures=exposures, exercises=FACTS)).lines[0]


def test_every_set_held_at_the_target_effort_moves_one_rack_row_up() -> None:
    line = derive(carry("2026-10-26", 30, 31, 30, rpe=8))

    assert line.steps[0] == Step("scheme", 40, 45, "hit")
    assert line.groups[0].load == Load(45, "per_hand_x2")


def test_a_set_short_of_the_duration_holds_the_load() -> None:
    line = derive(carry("2026-10-26", 30, 22, 30, rpe=8))

    assert (line.change, line.groups[0].load) == ("held", Load(40, "per_hand_x2"))


def test_every_set_held_with_no_stored_effort_holds_the_load() -> None:
    line = derive(carry("2026-10-26", 30, 30, 30))

    assert (line.change, line.groups[0].load) == ("held", Load(40, "per_hand_x2"))


def test_an_effort_over_the_target_holds_the_load() -> None:
    line = derive(carry("2026-10-26", 30, 30, 30, rpe=9))

    assert (line.change, line.groups[0].load) == ("held", Load(40, "per_hand_x2"))


def test_fewer_sets_than_authored_hold_the_load() -> None:
    line = derive(carry("2026-10-26", 30, 30, rpe=8))

    assert line.groups[0].load == Load(40, "per_hand_x2")


def codes(line: LinePrescription) -> list[str]:
    return [f.code for f in line.flags]


def test_three_weeks_held_with_no_effort_reading_warns() -> None:
    line = derive(
        carry("2026-10-12", 30, 30, 30), carry("2026-10-19", 30, 30, 30), carry("2026-10-26", 30)
    )

    [flag] = [f for f in line.flags if f.code == "held_without_effort"]
    assert dict(flag.params) == {
        "weeks": 3,
        "load": 40,
        "exposures": [
            "exposure:w-2026-10-12/custom_farmers_carry",
            "exposure:w-2026-10-19/custom_farmers_carry",
            "exposure:w-2026-10-26/custom_farmers_carry",
        ],
    }


def test_two_weeks_held_with_no_effort_reading_raise_nothing() -> None:
    line = derive(carry("2026-10-19", 30, 30, 30), carry("2026-10-26", 30, 30, 30))

    assert "held_without_effort" not in codes(line)


def test_an_effort_reading_inside_the_three_weeks_raises_nothing() -> None:
    line = derive(
        carry("2026-10-12", 30, 30, 30),
        carry("2026-10-19", 30, 30, 30, rpe=9),
        carry("2026-10-26", 30, 30, 30),
    )

    assert "held_without_effort" not in codes(line)


def test_a_load_change_inside_the_three_weeks_raises_nothing() -> None:
    line = derive(
        carry("2026-10-12", 30, 30, 30, load=35),
        carry("2026-10-19", 30, 30, 30),
        carry("2026-10-26", 30, 30, 30),
    )

    assert "held_without_effort" not in codes(line)


def test_two_exposures_in_one_week_count_as_one_week() -> None:
    line = derive(
        carry("2026-10-19", 30, 30, 30),
        carry("2026-10-22", 30, 30, 30),
        carry("2026-10-26", 30, 30, 30),
    )

    assert "held_without_effort" not in codes(line)


def test_a_load_bearing_hold_line_held_three_weeks_unrated_warns() -> None:
    squat = a_line("bb_back_squat", SetGroup(3, "working", 5), scheme="hold")
    held = [
        Exposure(
            f"w-{on}",
            "bb_back_squat",
            datetime.date.fromisoformat(on),
            (ExposureSet(0, "working", Load(100, "total"), 5, None),),
            Matched("lower"),
        )
        for on in ("2026-10-12", "2026-10-19", "2026-10-26")
    ]

    line = prescribe(a_request(squat, exposures=tuple(held))).lines[0]

    assert "held_without_effort" in codes(line)


def test_three_exposures_at_one_load_and_the_same_seconds_raise_a_stall() -> None:
    line = derive(
        carry("2026-10-12", 30, 30, 25, rpe=9),
        carry("2026-10-19", 30, 30, 25, rpe=9),
        carry("2026-10-26", 30, 30, 25, rpe=9),
    )

    assert "stall_streak" in codes(line)


def test_more_seconds_at_one_load_is_a_gain_and_raises_no_stall() -> None:
    line = derive(
        carry("2026-10-12", 30, 30, 20, rpe=9),
        carry("2026-10-19", 30, 30, 25, rpe=9),
        carry("2026-10-26", 30, 30, 25, rpe=9),
    )

    assert "stall_streak" not in codes(line)
