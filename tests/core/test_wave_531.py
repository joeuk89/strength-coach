from typing import Any

from support.exposures import an_exposure
from support.prescribe import a_line, a_rack, a_request, warm_up

from coach.core.exposure import Exposure
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    DecisionInForce,
    LinePrescription,
    NiggleConstraint,
    PlanOverride,
    Step,
)
from coach.core.program.form import Reps, SetGroup

RACK = a_rack(*[30 + 2.5 * i for i in range(37)])
WAVE = a_line(
    "bb_bench_press",
    warm_up(5),
    SetGroup(3, "working"),
    scheme="wave_531",
    start_load=100,
)


def derive(*exposures: Exposure, **request: Any) -> LinePrescription:
    built = a_request(WAVE, exposures=exposures, racks={"barbell": RACK}, **request)
    return prescribe(built).lines[0]


def working(line: LinePrescription) -> list[tuple[int, float | None, Reps | None]]:
    return [
        (g.count, None if g.load is None else g.load.amount, g.reps)
        for g in line.groups
        if g.type == "working"
    ]


def test_hard_week_count_0_prescribes_the_first_wave_of_the_training_max() -> None:
    line = derive(hard_week_count=0)

    assert working(line) == [(1, 65, 5), (1, 75, 5), (1, 85, "5+")]
    assert Step("scheme", 100, (65, 75, 85), "wave 1") in line.steps


def test_hard_week_count_1_prescribes_the_second_wave() -> None:
    assert working(derive(hard_week_count=1)) == [(1, 70, 3), (1, 80, 3), (1, 90, "3+")]


def test_hard_week_count_2_prescribes_the_third_wave() -> None:
    assert working(derive(hard_week_count=2)) == [(1, 75, 1), (1, 85, 1), (1, 95, "1+")]


def test_the_wave_cycles_after_the_third_hard_week() -> None:
    assert working(derive(hard_week_count=3)) == working(derive(hard_week_count=0))


def test_a_training_max_decision_replaces_the_start_load_and_loads_round_down() -> None:
    training_max = DecisionInForce(
        "d-0007", "training_max", exercise_id="bb_bench_press", params={"load": 110}
    )

    line = derive(decisions=(training_max,))

    # 71.5, 82.5 and 93.5 of 110, each down to a row
    assert working(line) == [(1, 70, 5), (1, 82.5, 5), (1, 92.5, "5+")]


def test_the_warm_ups_ramp_off_the_first_wave_load() -> None:
    line = derive()

    assert line.groups[0].load == Load(37.5, "total")


def wave_logged(on: str, loads: tuple[float, float, float], reps: int, rep_out: int) -> Exposure:
    sets = ((loads[0], reps, None), (loads[1], reps, None), (loads[2], rep_out, None))
    return an_exposure(on, *sets, session_id="lower")


THREE_WAVES = (
    wave_logged("2026-10-12", (65, 75, 85), 5, 8),
    wave_logged("2026-10-19", (70, 80, 90), 3, 6),
    wave_logged("2026-10-26", (75, 85, 95), 1, 3),
)


def test_after_three_rep_outs_at_one_training_max_it_warns_training_max_due() -> None:
    line = derive(*THREE_WAVES, hard_week_count=3)

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        ("training_max_due", {"training_max": 100, "source": "start_load", "rep_outs": [8, 6, 3]})
    ]
    assert working(line) == [(1, 65, 5), (1, 75, 5), (1, 85, "5+")]


def test_a_light_week_between_the_waves_is_skipped() -> None:
    light = an_exposure("2026-10-22", *[(60, 5, None)] * 3, session_id="lower", light_week=True)

    line = derive(*THREE_WAVES, light, hard_week_count=3)

    assert [f.code for f in line.flags] == ["training_max_due"]


def test_a_rep_out_short_of_its_wave_warns_rep_range_missed() -> None:
    line = derive(wave_logged("2026-10-26", (65, 75, 85), 5, 4), hard_week_count=1)

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "rep_range_missed",
            {"set_index": 3, "reps": 4, "range": [5, 5], "logged_rpe": None, "authored_rpe": None},
        )
    ]


def test_a_light_cut_and_a_niggle_cap_bind_each_wave_set() -> None:
    light = PlanOverride("light_week", params={"load_cut_pct": 10, "set_cut_pct": 0})
    cap = NiggleConstraint("n-0001", "load_cap", exercise_id="bb_bench_press", value=70)

    line = derive(overrides=(light,), niggle_constraints=(cap,))

    # 65, 75 and 85 × 0.90 are 58.5, 67.5 and 76.5; the cap lowers only the last
    assert Step("cut", (65, 75, 85), (58.5, 67.5, 76.5), "light") in line.steps
    assert Step("niggle", (58.5, 67.5, 76.5), (58.5, 67.5, 70), "load_cap niggle:n-0001") in (
        line.steps
    )
    assert working(line) == [(1, 57.5, 5), (1, 67.5, 5), (1, 70, 5)]


TRAINING_MAX_110 = DecisionInForce(
    "d-0007", "training_max", exercise_id="bb_bench_press", params={"load": 110}
)


def test_wave_loads_off_the_rack_still_name_the_wave_as_the_change() -> None:
    line = derive(*THREE_WAVES, decisions=(TRAINING_MAX_110,), hard_week_count=1)

    # 77, 88 and 99 of 110, each down to a row
    assert working(line) == [(1, 75, 3), (1, 87.5, 3), (1, 97.5, "3+")]
    assert line.change == "wave 2: training max 110"


def pin(load: float) -> PlanOverride:
    return PlanOverride(
        "pin_load", session_id="lower", exercise_id="bb_bench_press", params={"load": load}
    )


def test_a_pin_on_a_first_wave_leaves_only_the_last_set_open() -> None:
    line = derive(overrides=(pin(80),), hard_week_count=1)

    assert working(line) == [(1, 80, 3), (1, 80, 3), (1, 80, "3+")]


def test_a_pin_on_a_wave_after_an_exposure_leaves_only_the_last_set_open() -> None:
    line = derive(*THREE_WAVES, overrides=(pin(80),), hard_week_count=1)

    assert working(line) == [(1, 80, 3), (1, 80, 3), (1, 80, "3+")]


HOLD = PlanOverride("hold", "lower", "bb_bench_press")


def test_a_hold_after_a_logged_wave_repeats_that_wave() -> None:
    line = derive(
        wave_logged("2026-10-26", (65, 75, 85), 5, 8), overrides=(HOLD,), hard_week_count=1
    )

    assert working(line) == [(1, 65, 5), (1, 75, 5), (1, 85, "5+")]
    assert line.change == "held"
    assert not any(step.step == "scheme" for step in line.steps)


def test_a_hold_after_an_exposure_off_the_waves_repeats_its_loads_at_this_weeks_reps() -> None:
    line = derive(
        wave_logged("2026-10-26", (60, 70, 80), 5, 8), overrides=(HOLD,), hard_week_count=1
    )

    assert working(line) == [(1, 60, 3), (1, 70, 3), (1, 80, "3+")]
