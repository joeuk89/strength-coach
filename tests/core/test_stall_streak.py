from support.exposures import an_exposure
from support.prescribe import a_line, a_rack, a_request, working

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


BENCH = a_line("bb_bench_press", working(4, 5), scheme="linear")
BENCH_RACK = a_rack(100, 105, 107.5, 110, 115, 120, 125)


def bench_on(on: str, load: float, last_reps: int) -> Exposure:
    return an_exposure(on, (load, 5, 8), (load, 5, 8), (load, 5, 8), (load, last_reps, 8))


def bench_stalls(*exposures: Exposure) -> list[dict[str, object]]:
    request = a_request(BENCH, exposures=exposures, racks={"barbell": BENCH_RACK})
    return [dict(f.params) for f in prescribe(request).lines[0].flags if f.code == "stall_streak"]


def test_a_linear_hit_at_the_reset_load_is_not_a_stall() -> None:
    found = bench_stalls(
        bench_on("2026-10-12", 120, 4),
        bench_on("2026-10-19", 120, 4),
        bench_on("2026-10-26", 107.5, 5),
    )

    assert found == []


def test_three_consecutive_linear_misses_raise_stall_streak_whatever_the_load() -> None:
    found = bench_stalls(
        bench_on("2026-10-12", 120, 4),
        bench_on("2026-10-19", 120, 4),
        bench_on("2026-10-26", 107.5, 4),
    )

    assert [p["streak"] for p in found] == [3]


def test_three_linear_hits_at_one_load_are_not_a_stall() -> None:
    found = bench_stalls(
        *(bench_on(on, 120, 5) for on in ("2026-10-12", "2026-10-19", "2026-10-26"))
    )

    assert found == []


def test_a_lighter_double_progression_load_starts_a_new_run() -> None:
    lighter = ((110, 8, 8), (110, 8, 8), (110, 7, 8), (110, 6, 8))

    assert (
        stalls(squat_on("2026-10-12"), squat_on("2026-10-19"), squat_on("2026-10-26", *lighter))
        == []
    )


def test_an_older_best_does_not_pull_three_rising_exposures_into_a_stall() -> None:
    best = ((120, 9, 8),) * 4
    rising = [((120, reps, 8),) * 4 for reps in (6, 7, 8)]

    found = stalls(
        squat_on("2026-10-05", *best),
        *(
            squat_on(on, *sets)
            for on, sets in zip(("2026-10-12", "2026-10-19", "2026-10-26"), rising, strict=True)
        ),
    )

    assert found == []


def test_a_top_backoff_line_rising_back_toward_an_old_best_e1rm_is_not_a_stall() -> None:
    line = a_line(
        "bb_bench_press", working(1, 3, 8), working(3, 5, 8), scheme="top_backoff", pct_of_top=85
    )
    old_best = an_exposure("2026-09-28", (150, 3, 8), (125, 5, 7), workout_id="w-0")
    rising = [
        an_exposure(on, (top, 3, 8), (top - 20, 5, 7), workout_id=f"w-{i}")
        for i, (on, top) in enumerate(
            (("2026-10-12", 120), ("2026-10-19", 125), ("2026-10-26", 130)), 1
        )
    ]

    flags = prescribe(a_request(line, exposures=(old_best, *rising))).lines[0].flags

    assert [f.code for f in flags if f.code == "stall_streak"] == []
