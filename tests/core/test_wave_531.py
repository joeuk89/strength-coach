import dataclasses

from support.exposures import an_exposure
from support.prescribe import a_line, a_request, warm_up

from coach.core.exposure import Exposure
from coach.core.prescribe import prescribe
from coach.core.prescription import DecisionInForce, LinePrescription
from coach.core.program.form import SetGroup

SQUAT = a_line("bb_back_squat", warm_up(5), SetGroup(3), scheme="wave_531")
TRAINING_MAX = DecisionInForce(
    "d-0001", "training_max", exercise_id="bb_back_squat", params={"load": 200}
)


def squat(count: int, *exposures: Exposure, start_load: float | None = None) -> LinePrescription:
    line = dataclasses.replace(SQUAT, start_load=start_load)
    request = a_request(line, exposures=exposures)
    decisions = () if start_load is not None else (TRAINING_MAX,)
    request = dataclasses.replace(request, hard_week_count=count, decisions=decisions)
    return prescribe(request).lines[0]


def working(line: LinePrescription) -> list[tuple[int, float | None, object]]:
    return [
        (g.count, None if g.load is None else g.load.amount, g.reps)
        for g in line.groups
        if g.type == "working"
    ]


def test_count_0_1_and_2_prescribe_the_three_waves_of_the_training_max() -> None:
    assert working(squat(0)) == [(1, 130, 5), (1, 150, 5), (1, 170, "5+")]
    assert working(squat(1)) == [(1, 140, 3), (1, 160, 3), (1, 180, "3+")]
    assert working(squat(2)) == [(1, 150, 1), (1, 170, 1), (1, 190, "1+")]


def test_the_wave_cycles_on_the_hard_week_count() -> None:
    assert working(squat(3)) == working(squat(0))


def test_the_warm_ups_ramp_off_the_first_wave_load() -> None:
    line = squat(0)

    assert [step.from_ for step in line.steps if step.step == "warm_up"] == [(78,)]


def test_with_no_training_max_decision_the_start_load_is_the_training_max() -> None:
    assert working(squat(0, start_load=200)) == [(1, 130, 5), (1, 150, 5), (1, 170, "5+")]


def test_a_line_with_neither_is_start_load_missing() -> None:
    line = prescribe(a_request(SQUAT)).lines[0]

    assert [f.code for f in line.flags] == ["start_load_missing"]


def wave(on: str, *sets: tuple[float, int]) -> Exposure:
    return an_exposure(
        on, *((load, reps, None) for load, reps in sets), exercise_id="bb_back_squat"
    )


WAVE_1 = wave("2026-10-12", (130, 5), (150, 5), (170, 8))
WAVE_2 = wave("2026-10-19", (140, 3), (160, 3), (180, 5))
WAVE_3 = wave("2026-10-26", (150, 1), (170, 1), (190, 3))


def test_after_the_third_wave_at_one_training_max_it_warns_training_max_due() -> None:
    line = squat(3, WAVE_1, WAVE_2, WAVE_3)

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        ("training_max_due", {"training_max": 200, "source": "d-0001", "rep_outs": [8, 5, 3]})
    ]
    assert working(line) == [(1, 130, 5), (1, 150, 5), (1, 170, "5+")]


def test_two_waves_at_the_training_max_are_not_due() -> None:
    line = squat(2, WAVE_1, WAVE_2)

    assert [f.code for f in line.flags] == []


def test_a_rep_out_below_its_waves_reps_warns_rep_range_missed() -> None:
    short = wave("2026-10-19", (140, 3), (160, 3), (180, 2))

    line = squat(2, WAVE_1, short)

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "rep_range_missed",
            {"set_index": 3, "reps": 2, "range": [3, 3], "logged_rpe": None, "authored_rpe": None},
        )
    ]
