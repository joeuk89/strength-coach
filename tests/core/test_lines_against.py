import datetime

from support.exposures import an_exposure

from coach.core.closed_week.against import (
    AgainstPrescription,
    TargetSet,
    against,
    lines_against,
)
from coach.core.closed_week.match import WeekWorkout
from coach.core.exposure import Exposure, ExposureSet

MONDAY = datetime.date(2026, 11, 2)
SQUAT = (TargetSet(6, 8.0, 8, 120.0),) * 3


def a_workout(
    *exposures_: tuple[str, tuple[tuple[float | None, int, float | None], ...]],
) -> WeekWorkout:
    exposures = tuple(
        an_exposure("2026-11-02", *sets, workout_id="h-1", exercise_id=exercise)
        for exercise, sets in exposures_
    )
    return WeekWorkout("h-1", MONDAY, exposures)


def test_a_line_logged_at_rpe_6_against_an_authored_8_is_two_under() -> None:
    workout = a_workout(("bb_back_squat", ((120, 6, 6.0),) * 3))

    [line] = lines_against({"bb_back_squat": SQUAT}, frozenset(), workout)

    assert line.state == "logged"
    assert [s.rpe for s in line.logged] == [6.0, 6.0, 6.0]
    assert line.rpe_off == (-2.0, -2.0, -2.0)
    assert (line.sets_missing, line.rpe_missing, line.off) == (0, 0, True)


def test_a_prescribed_line_with_no_logged_set_is_not_logged() -> None:
    workout = a_workout(("bb_back_squat", ((120, 8, 8.0),) * 3))

    lines = lines_against({"bb_back_squat": SQUAT, "bb_bench_press": SQUAT}, frozenset(), workout)

    bench = lines[1]
    assert (bench.exercise, bench.state, bench.logged, bench.off) == (
        "bb_bench_press",
        "not_logged",
        (),
        True,
    )
    assert lines[0].off is False


def test_every_line_of_an_untrained_session_is_not_logged() -> None:
    [line] = lines_against({"bb_back_squat": SQUAT}, frozenset(), None)

    assert line.state == "not_logged"


def test_an_exercise_logged_and_not_prescribed_follows_the_prescribed_lines() -> None:
    workout = a_workout(("bb_curl", ((30, 12, 9.0),)), ("bb_back_squat", ((120, 8, 8.0),) * 3))

    lines = lines_against({"bb_back_squat": SQUAT}, frozenset(), workout)

    assert [(line.exercise, line.state) for line in lines] == [
        ("bb_back_squat", "logged"),
        ("bb_curl", "not_prescribed"),
    ]
    assert (lines[1].targets, [s.reps for s in lines[1].logged]) == ((), [12])
    assert (lines[1].rpe_off, lines[1].reps_short) == ((None,), (None,))


def test_sets_short_of_the_prescription_are_missing_and_extra_sets_are_unpaired() -> None:
    short = a_workout(("bb_back_squat", ((120, 5, 8.0),)))
    long = a_workout(("bb_back_squat", ((120, 8, 8.0),) * 4))

    [missing] = lines_against({"bb_back_squat": SQUAT}, frozenset(), short)
    [extra] = lines_against({"bb_back_squat": SQUAT}, frozenset(), long)

    assert (missing.sets_missing, missing.reps_short, missing.reps_missed) == (2, (1,), 1)
    assert (extra.sets_missing, extra.rpe_off, extra.off) == (0, (0.0, 0.0, 0.0, None), False)


def test_a_hold_line_is_paired_and_named_hold() -> None:
    plank = (TargetSet(seconds=30),) * 2
    exposure = Exposure(
        "h-1",
        "plank",
        MONDAY,
        tuple(
            ExposureSet(i, "working", None, None, None, duration_s=s)
            for i, s in enumerate((30, 25))
        ),
    )

    [line] = lines_against(
        {"plank": plank}, frozenset({"plank"}), WeekWorkout("h-1", MONDAY, (exposure,))
    )

    assert (line.hold, line.state) == (True, "logged")
    assert [s.duration_s for s in line.logged] == [30, 25]


def test_the_session_counts_derive_from_the_lines_and_leave_a_hold_line_out() -> None:
    workout = a_workout(
        ("bb_back_squat", ((120, 8, 8.0), (120, 5, 8.0), (120, 8, 6.0), (120, 8, None))),
        ("bb_bench_press", ((100, 8, None),) * 3),
    )

    lines = lines_against(
        {"bb_back_squat": SQUAT, "bb_bench_press": SQUAT}, frozenset({"bb_bench_press"}), workout
    )

    assert against(lines) == AgainstPrescription(reps_missed=1, effort_off=1, rpe_missing=0)
    assert lines[1].rpe_missing == 3
