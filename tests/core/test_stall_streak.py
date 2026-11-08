import datetime
from typing import Any

from support.exposures import an_exposure
from support.prescribe import a_line, a_request, working

from coach.core.exposure import Exposure
from coach.core.prescribe import prescribe
from coach.core.prescription import LinePrescription

HELD = ((120, 8, 8), (120, 8, 8), (120, 7, 8), (120, 6, 8))


def squat_on(on: str, *sets: tuple[float, int, float], **match: Any) -> Exposure:
    return an_exposure(
        on, *(sets or HELD), exercise_id="bb_back_squat", session_id="lower", **match
    )


def derive(
    *exposures: Exposure,
    line: Any = None,
    redesigned: datetime.date | None = None,
    kind: str = "lifting",
) -> LinePrescription:
    request = a_request(line or a_line(), exposures=exposures, redesigned=redesigned, kind=kind)
    return prescribe(request).lines[0]


def stalls(line: LinePrescription) -> list[dict[str, object]]:
    return [dict(f.params) for f in line.flags if f.code == "stall_streak"]


def ref(on: str) -> str:
    return f"exposure:w-{on}/bb_back_squat"


def test_three_ordinary_exposures_with_no_gain_raise_stall_streak_with_their_refs() -> None:
    line = derive(squat_on("2026-10-12"), squat_on("2026-10-19"), squat_on("2026-10-26"))

    assert stalls(line) == [
        {"streak": 3, "exposures": [ref("2026-10-12"), ref("2026-10-19"), ref("2026-10-26")]}
    ]


def test_a_practice_line_on_double_progression_raises_no_stall_streak() -> None:
    line = derive(
        squat_on("2026-10-12"), squat_on("2026-10-19"), squat_on("2026-10-26"), kind="practice"
    )

    assert stalls(line) == []


def test_two_exposures_with_no_gain_are_not_a_stall() -> None:
    assert stalls(derive(squat_on("2026-10-19"), squat_on("2026-10-26"))) == []


def test_a_gain_on_the_metric_inside_the_three_is_not_a_stall() -> None:
    better = ((120, 8, 8), (120, 8, 8), (120, 8, 8), (120, 6, 8))

    line = derive(squat_on("2026-10-12"), squat_on("2026-10-19", *better), squat_on("2026-10-26"))

    assert stalls(line) == []


def test_a_light_week_exposure_in_between_is_skipped_and_does_not_count() -> None:
    line = derive(
        squat_on("2026-10-05"),
        squat_on("2026-10-12"),
        squat_on("2026-10-19", (100, 8, 6), (100, 8, 6), light_week=True),
        squat_on("2026-10-26"),
    )

    assert stalls(line) == [
        {"streak": 3, "exposures": [ref("2026-10-05"), ref("2026-10-12"), ref("2026-10-26")]}
    ]


def test_a_return_week_exposure_in_between_is_skipped_and_does_not_count() -> None:
    returned = frozenset({"bb_back_squat"})

    line = derive(
        squat_on("2026-10-12"),
        squat_on("2026-10-19", (110, 8, 6), (110, 8, 6), (110, 8, 6), return_band_lines=returned),
        squat_on("2026-10-26"),
    )

    assert stalls(line) == []


def test_a_held_line_never_stalls() -> None:
    held = a_line("bb_back_squat", working(4, 8), scheme="hold")

    line = derive(squat_on("2026-10-12"), squat_on("2026-10-19"), squat_on("2026-10-26"), line=held)

    assert stalls(line) == []


LINEAR = a_line("bb_back_squat", working(4, 5), scheme="linear")


def test_a_linear_line_stalls_on_three_consecutive_misses() -> None:
    short = ((120, 5, 8), (120, 5, 8), (120, 5, 8), (120, 4, 8))
    dates = ("2026-10-12", "2026-10-19", "2026-10-26")

    line = derive(*(squat_on(on, *short) for on in dates), line=LINEAR)

    assert stalls(line) == [{"streak": 3, "exposures": [ref(on) for on in dates]}]


def test_a_linear_line_making_every_rep_over_the_authored_rpe_does_not_stall() -> None:
    hard = ((120, 5, 9.5),) * 4
    dates = ("2026-10-12", "2026-10-19", "2026-10-26")

    line = derive(*(squat_on(on, *hard) for on in dates), line=LINEAR)

    assert stalls(line) == []


REDESIGNED = datetime.date(2026, 10, 19)


def test_three_held_exposures_before_the_latest_redesign_raise_no_stall() -> None:
    line = derive(
        squat_on("2026-09-28"),
        squat_on("2026-10-05"),
        squat_on("2026-10-12"),
        redesigned=REDESIGNED,
    )

    assert stalls(line) == []


def test_two_held_exposures_before_the_latest_redesign_and_one_after_raise_no_stall() -> None:
    line = derive(
        squat_on("2026-10-05"),
        squat_on("2026-10-12"),
        squat_on("2026-10-19"),
        redesigned=REDESIGNED,
    )

    assert stalls(line) == []


def test_three_held_exposures_from_the_adoption_date_on_raise_stall_streak() -> None:
    dates = ("2026-10-19", "2026-10-22", "2026-10-26")

    line = derive(squat_on("2026-10-12"), *(squat_on(on) for on in dates), redesigned=REDESIGNED)

    assert stalls(line) == [{"streak": 3, "exposures": [ref(on) for on in dates]}]


def test_an_amend_between_the_held_exposures_does_not_reset_the_streak() -> None:
    amended = a_line("bb_back_squat", working(4, (6, 8), rpe=8.5))
    dates = ("2026-10-19", "2026-10-22", "2026-10-26")

    line = derive(*(squat_on(on) for on in dates), line=amended, redesigned=REDESIGNED)

    assert stalls(line) == [{"streak": 3, "exposures": [ref(on) for on in dates]}]
