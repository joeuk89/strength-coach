"""An exposure logged with no positive load never anchors a load-bearing line
(docs/spec/prescription.md, "The anchor exposure")."""

from support.exposures import an_exposure
from support.prescribe import a_line, a_request

from coach.core.exposure import Exposure
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import LinePrescription, PlanOverride
from coach.core.program.form import Line

ZERO = ((0, 8, 8), (0, 8, 8), (0, 8, 8), (0, 8, 8))
HELD = ((120, 8, 8), (120, 8, 8), (120, 7, 8), (120, 6, 8))


def squat_on(on: str, *sets: tuple[float, int, float], workout_id: str) -> Exposure:
    return an_exposure(
        on, *sets, workout_id=workout_id, exercise_id="bb_back_squat", session_id="lower"
    )


def derive(line: Line, *exposures: Exposure) -> LinePrescription:
    return prescribe(a_request(line, exposures=exposures)).lines[0]


def codes(line: LinePrescription) -> list[str]:
    return [f.code for f in line.flags]


def unusable(line: LinePrescription) -> list[tuple[str, dict[str, object]]]:
    return [(f.severity, dict(f.params)) for f in line.flags if f.code == "anchor_load_unusable"]


def test_a_line_whose_only_exposure_is_logged_at_zero_starts_from_its_start_load() -> None:
    line = derive(a_line(start_load=100), squat_on("2026-10-26", *ZERO, workout_id="h-0"))

    assert line.derived_from == "start_load"
    assert line.groups[-1].load == Load(100, "total")
    assert "offgrid_anchor_ignored" not in codes(line)
    assert unusable(line) == [
        (
            "warning",
            {
                "exposure": "exposure:h-0/bb_back_squat",
                "logged_load": 0,
                "anchor_used": "start_load",
            },
        )
    ]


def test_behind_a_zero_logged_exposure_the_older_positive_one_anchors() -> None:
    older = squat_on("2026-10-19", *HELD, workout_id="h-1")
    zero = squat_on("2026-10-26", *ZERO, workout_id="h-2")

    line = derive(a_line(start_load=100), older, zero)

    assert line.derived_from == "exposure:h-1/bb_back_squat"
    assert line.groups[-1].load == Load(120, "total")
    assert unusable(line) == [
        (
            "warning",
            {
                "exposure": "exposure:h-2/bb_back_squat",
                "logged_load": 0,
                "anchor_used": "exposure:h-1/bb_back_squat",
            },
        )
    ]


def test_every_exposure_skipped_and_no_start_load_is_start_load_missing() -> None:
    line = derive(a_line(), squat_on("2026-10-26", *ZERO, workout_id="h-0"))

    assert "start_load_missing" in codes(line)
    assert line.derived_from == "start_load"


def test_the_skipped_exposure_still_counts_as_a_day_trained() -> None:
    before_the_layoff = squat_on("2026-10-03", *HELD, workout_id="h-1")
    zero = squat_on("2026-10-26", *ZERO, workout_id="h-2")

    skipped = derive(a_line(), before_the_layoff, zero)
    unlogged = derive(a_line(), before_the_layoff)

    assert skipped.derived_from == unlogged.derived_from == "exposure:h-1/bb_back_squat"
    assert [s.step for s in skipped.steps if s.step == "cut"] == []
    assert skipped.groups[-1].load == Load(120, "total")
    assert next(s.cause for s in unlogged.steps if s.step == "cut") == "return 22–42, 30 days off"


CARRY = a_line("goblet_squat", start_load=40)


def carry_on(on: str) -> Exposure:
    return an_exposure(
        on, *ZERO, workout_id="h-0", exercise_id="goblet_squat", mode="single_implement"
    )


def test_a_pin_on_the_start_load_is_honoured_with_no_layoff() -> None:
    pin = PlanOverride("pin_load", "lower", "goblet_squat", params={"load": 40})

    line = prescribe(a_request(CARRY, exposures=(carry_on("2026-10-26"),), overrides=(pin,)))

    [carry] = line.lines
    assert carry.derived_from == "start_load"
    assert carry.groups[-1].load == Load(40, "single_implement")
    assert "return_band_disagrees" not in codes(carry)


def test_after_a_layoff_the_band_measures_from_the_start_load_and_still_binds_a_pin() -> None:
    pin = PlanOverride("pin_load", "lower", "goblet_squat", params={"load": 40})

    line = prescribe(a_request(CARRY, exposures=(carry_on("2026-09-14"),), overrides=(pin,)))

    [carry] = line.lines
    assert carry.derived_from == "start_load"
    assert carry.groups[-1].load == Load(30, "single_implement")
    assert [dict(f.params)["load"] for f in carry.flags if f.code == "return_band_disagrees"] == [
        34
    ]
