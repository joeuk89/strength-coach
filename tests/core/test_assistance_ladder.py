from support.exposures import an_exposure
from support.prescribe import a_line, a_request, working

from coach.core.exposure import Exposure
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import LinePrescription, Step

RUNGS = [60, 50, 40, 30, 20, 10, 0]
PULL_UP = a_line("assisted_pull_up", working(4, 8), scheme="assistance_ladder", rungs=RUNGS)


def pull_up(rung: float, *sets: tuple[int, float]) -> Exposure:
    return an_exposure(
        "2026-10-26",
        *[(rung, reps, rpe) for reps, rpe in sets],
        exercise_id="assisted_pull_up",
        mode="assisted",
        session_id="lower",
    )


def derive(*exposures: Exposure) -> LinePrescription:
    return prescribe(a_request(PULL_UP, exposures=exposures)).lines[0]


def test_a_full_hit_moves_one_rung_up() -> None:
    line = derive(pull_up(40, *[(8, 8)] * 4))

    assert line.steps[0] == Step("scheme", 40, 30, "hit")
    assert line.groups[0].load == Load(30, "assisted")
    assert line.flags == ()


def test_a_short_set_holds_the_rung() -> None:
    line = derive(pull_up(40, (8, 8), (8, 8), (8, 8), (7, 9)))

    assert (line.change, line.groups[0].load, line.flags) == ("held", Load(40, "assisted"), ())


def test_a_set_at_rpe_two_over_holds_and_warns_rep_range_missed() -> None:
    line = derive(pull_up(40, (8, 8), (8, 8), (8, 8), (8, 10)))

    assert line.groups[0].load == Load(40, "assisted")
    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "rep_range_missed",
            {"set_index": 4, "reps": 8, "range": [8, 8], "logged_rpe": 10, "authored_rpe": 8},
        )
    ]


def test_a_hit_on_the_last_rung_holds_with_cause_rack_top() -> None:
    line = derive(pull_up(0, *[(8, 8)] * 4))

    assert line.steps[0] == Step("scheme", 0, 0, "rack_top")
    assert (line.change, line.groups[0].load) == ("held", Load(0, "assisted"))


def test_a_logged_load_between_rungs_stands_on_the_rung_with_more_assistance() -> None:
    line = derive(pull_up(35, (8, 8), (8, 8), (8, 8), (7, 9)))

    assert line.groups[0].load == Load(40, "assisted")
    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "offgrid_anchor_ignored",
            {
                "exposure": "exposure:w-2026-10-26/assisted_pull_up",
                "logged_load": 35,
                "anchor_used": 40,
            },
        )
    ]


def test_with_no_exposure_the_ladder_opens_on_the_first_rung() -> None:
    line = derive()

    assert line.groups[0].load == Load(60, "assisted")
    assert line.flags == ()
