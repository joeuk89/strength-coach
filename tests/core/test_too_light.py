import datetime
from typing import Any

from support.exposures import an_exposure
from support.prescribe import a_line, a_rack, a_request, warm_up, working

from coach.core.exposure import Exposure
from coach.core.flag import Flag
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    DecisionInForce,
    LinePrescription,
    PlanOverride,
    StatusSpan,
    Step,
)

SQUAT = a_line(
    "bb_back_squat",
    warm_up(5),
    working(1, 5, 8),
    working(3, 5, None),
    scheme="top_backoff",
    pct_of_top=90,
)
TOO_LIGHT = "load_too_light@line:2026-11-02/lower/bb_back_squat"


def squat(on: str, *sets: tuple[float, int, float | None], session_id: str = "lower") -> Exposure:
    return an_exposure(on, *sets, exercise_id="bb_back_squat", session_id=session_id)


HOME_SQUAT = squat("2026-10-30", (110, 5, 6), *[(100, 5, 6)] * 3)
PT_SQUAT = squat("2026-10-27", (175, 5, 8), session_id="pt-legs")


def derive(*exposures: Exposure, line: Any = SQUAT, **request: Any) -> LinePrescription:
    return prescribe(a_request(line, exposures=exposures, **request)).lines[0]


def flag(line: LinePrescription, code: str) -> Flag | None:
    return next((f for f in line.flags if f.code == code), None)


def pin(load: float) -> PlanOverride:
    return PlanOverride("pin_load", "lower", "bb_back_squat", params={"load": load})


def test_a_top_backoff_line_far_under_another_sessions_e1rm_steps_one_row_and_warns() -> None:
    # e1RM 175 × (1 + 7/30) = 215.83 from the PT session; five at RPE 8 is 175
    line = derive(PT_SQUAT, HOME_SQUAT)

    assert line.steps[0] == Step(
        "scheme",
        110,
        115,
        "one_row_cap, e1rm 215.83 from exposure:w-2026-10-27/bb_back_squat, model 175",
    )
    warning = flag(line, "load_too_light")
    assert warning is not None
    assert warning.key == TOO_LIGHT
    assert warning.severity == "warning"
    assert dict(warning.params) == {
        "anchor_exposure": "exposure:w-2026-10-30/bb_back_squat",
        "logged_sets": [
            {"load": 110, "reps": 5, "rpe": 6},
            {"load": 100, "reps": 5, "rpe": 6},
            {"load": 100, "reps": 5, "rpe": 6},
            {"load": 100, "reps": 5, "rpe": 6},
        ],
        "rpe_gap": -2.0,
        "e1rm": 215.83,
        "e1rm_exposure": "exposure:w-2026-10-27/bb_back_squat",
        "e1rm_date": "2026-10-27",
        "e1rm_session": "pt-legs",
        "model_load": 175.0,
        "suggested_load": 175.0,
    }


PRESS = a_line("bb_back_squat", warm_up(5), working(3, (6, 8), 8))
FINE_RACK = {"barbell": a_rack(*[100 + 2.5 * i for i in range(40)])}


def test_a_double_progression_line_logged_at_6_7_7_against_8_warns_with_a_suggested_load() -> None:
    # e1RM 130 × (1 + 12/30) = 182; eight at RPE 8 is 136.5, nearest row 137.5, two rows over 132.5
    logged = squat("2026-10-26", (130, 8, 6), (130, 8, 7), (130, 8, 7))

    line = derive(logged, line=PRESS, racks=FINE_RACK)

    warning = flag(line, "load_too_light")
    assert warning is not None
    assert (warning.params["rpe_gap"], warning.params["model_load"]) == (-1.33, 136.5)
    assert warning.params["suggested_load"] == 137.5
    assert line.change == "3×6–8 @8: 130 → 132.5"


def test_a_line_within_the_rpe_gap_and_one_row_of_the_model_raises_nothing() -> None:
    # e1RM 130 × (1 + 11/30) = 177.67; eight at RPE 8 is 133.25, nearest row 132.5, the step
    logged = squat("2026-10-26", (130, 8, 7), (130, 8, 7), (130, 8, 7.5))

    line = derive(logged, line=PRESS, racks=FINE_RACK)

    assert line.flags == ()


def test_a_line_held_on_a_missed_rep_is_not_read_as_too_light() -> None:
    # e1RM 120 × (1 + 12/30) = 168 from the first set; eight at RPE 8 is 126, one row over 120
    logged = squat("2026-10-26", (120, 8, 6), (120, 7, 8), (120, 6, 8))

    line = derive(logged, line=PRESS)

    assert line.change == "held"
    assert line.flags == ()


def test_an_rpe_gap_of_1_5_alone_warns_with_the_model_inside_one_row() -> None:
    logged = squat("2026-10-26", (130, 8, 6.5), (130, 8, 6.5), (130, 8, 6.5))

    line = derive(logged, line=PRESS)

    warning = flag(line, "load_too_light")
    assert warning is not None
    assert warning.params["rpe_gap"] == -1.5


def test_a_gap_with_no_e1rm_warns_with_no_suggested_load() -> None:
    # Twelve at RPE 6 is 16 reps to failure, past the e1RM's cap of 12
    logged = squat("2026-10-26", *[(130, 12, 6)] * 3)

    line = derive(logged, line=a_line("bb_back_squat", working(3, (10, 12), 8)))

    warning = flag(line, "load_too_light")
    assert warning is not None
    assert (warning.params["e1rm"], warning.params["suggested_load"]) == (None, None)


def test_a_pin_at_the_suggested_load_raises_no_increment_over_step() -> None:
    line = derive(PT_SQUAT, HOME_SQUAT, overrides=(pin(175),))

    assert [f.code for f in line.flags] == ["load_too_light"]
    assert line.groups[1].load == Load(175, "total")


def test_a_pin_above_the_suggested_load_still_raises_increment_over_step() -> None:
    line = derive(PT_SQUAT, HOME_SQUAT, overrides=(pin(180),))

    assert [f.code for f in line.flags] == ["load_too_light", "increment_over_step"]


def test_a_pin_at_the_suggested_load_is_still_bounded_by_the_illness_cap() -> None:
    # RPE 7 for five on the e1RM of 215.83 is 170.39, down to 170
    ill = StatusSpan("ill", datetime.date(2026, 10, 31), datetime.date(2026, 11, 1))

    line = derive(PT_SQUAT, HOME_SQUAT, overrides=(pin(175),), status_spans=(ill,))

    capped = flag(line, "pin_load_capped")
    assert capped is not None
    assert (capped.params["prescribed"], capped.params["outcome"]) == (170, "reduced")
    assert line.groups[1].load == Load(170, "total")
    assert flag(line, "increment_over_step") is None


def test_the_suggested_load_stays_under_a_safety_ceiling() -> None:
    ceiling = DecisionInForce(
        "d-0001", "safety_ceiling", exercise_id="bb_back_squat", params={"load": 152}
    )

    line = derive(PT_SQUAT, HOME_SQUAT, decisions=(ceiling,))

    warning = flag(line, "load_too_light")
    assert warning is not None
    assert (warning.params["model_load"], warning.params["suggested_load"]) == (175.0, 150.0)


def test_a_line_a_return_band_cuts_raises_no_too_light_warning() -> None:
    old = squat("2026-10-12", (110, 5, 6), *[(100, 5, 6)] * 3)

    line = derive(squat("2026-10-09", (175, 5, 8), session_id="pt-legs"), old)

    assert flag(line, "load_too_light") is None


def test_another_sessions_exposure_never_changes_the_anchor() -> None:
    line = derive(PT_SQUAT, HOME_SQUAT)

    assert line.derived_from == "exposure:w-2026-10-30/bb_back_squat"
    assert line.groups[1].load == Load(115, "total")


def test_a_return_week_anchor_logged_easy_under_its_rpe_cap_is_not_read_as_too_light() -> None:
    returned = an_exposure(
        "2026-10-26",
        *[(130, 8, 6.5)] * 3,
        exercise_id="bb_back_squat",
        session_id="lower",
        return_band_lines=frozenset({"bb_back_squat"}),
    )

    line = derive(returned, line=PRESS, racks=FINE_RACK)

    assert flag(line, "load_too_light") is None
