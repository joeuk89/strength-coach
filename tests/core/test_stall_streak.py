from support.exposures import an_exposure
from support.prescribe import a_line, a_request

from coach.core.exposure import Exposure
from coach.core.prescribe import prescribe

SQUAT = a_line()
UNDER = ((120, 8, 8), (120, 8, 8), (120, 7, 8), (120, 6, 8))


def squat_on(on: str, *sets: tuple[float, int, float], light_week: bool = False) -> Exposure:
    return an_exposure(
        on, *(sets or UNDER), exercise_id="bb_back_squat", session_id="lower", light_week=light_week
    )


def stalls(*exposures: Exposure) -> list[dict[str, object]]:
    line = prescribe(a_request(SQUAT, exposures=exposures)).lines[0]
    return [dict(f.params) for f in line.flags if f.code == "stall_streak"]


def test_three_ordinary_exposures_with_no_gain_raise_stall_streak_with_their_refs() -> None:
    found = stalls(squat_on("2026-10-12"), squat_on("2026-10-19"), squat_on("2026-10-26"))

    assert found == [
        {
            "streak": 3,
            "exposures": [
                "exposure:w-2026-10-12/bb_back_squat",
                "exposure:w-2026-10-19/bb_back_squat",
                "exposure:w-2026-10-26/bb_back_squat",
            ],
        }
    ]


def test_two_exposures_with_no_gain_are_not_a_stall() -> None:
    assert stalls(squat_on("2026-10-19"), squat_on("2026-10-26")) == []


def test_a_gain_on_reps_at_the_load_breaks_the_streak() -> None:
    better = ((120, 8, 8), (120, 8, 8), (120, 8, 8), (120, 6, 8))

    assert (
        stalls(squat_on("2026-10-12"), squat_on("2026-10-19"), squat_on("2026-10-26", *better))
        == []
    )


def test_a_light_week_or_return_week_exposure_in_between_is_skipped_and_does_not_count() -> None:
    light = squat_on("2026-10-15", (100, 3, 6), light_week=True)
    returned = an_exposure(
        "2026-10-22",
        (110, 3, 6),
        exercise_id="bb_back_squat",
        session_id="lower",
        return_band_lines=frozenset({"bb_back_squat"}),
    )

    found = stalls(
        squat_on("2026-10-12"), light, squat_on("2026-10-19"), returned, squat_on("2026-10-26")
    )

    assert [p["exposures"] for p in found] == [
        [
            "exposure:w-2026-10-12/bb_back_squat",
            "exposure:w-2026-10-19/bb_back_squat",
            "exposure:w-2026-10-26/bb_back_squat",
        ]
    ]


def test_a_light_week_exposure_does_not_make_up_the_three() -> None:
    light = squat_on("2026-10-22", (100, 3, 6), light_week=True)

    assert stalls(squat_on("2026-10-19"), light, squat_on("2026-10-26")) == []
