import datetime

from support.exposures import an_exposure
from support.prescribe import a_line, working

from coach.core.cadence import BlockSpan, CadenceRead, cadence_signal
from coach.core.exposure import Exposure
from coach.core.program.form import Line

BEFORE = BlockSpan("b-2026-09-07", datetime.date(2026, 9, 7), datetime.date(2026, 10, 4))
CLOSED = BlockSpan("b-2026-10-05", datetime.date(2026, 10, 5), datetime.date(2026, 11, 1))
LINEAR = a_line("bb_bench_press", working(3, 5), scheme="linear")
MISSED = ((100, 5, 8), (100, 5, 9), (100, 4, 10))


def bench(on: str, *sets: tuple[float, int, float]) -> Exposure:
    return an_exposure(on, *sets)


def a_read(line: Line, *exposures: Exposure, adherence: float | None = 0.9) -> CadenceRead:
    return CadenceRead(line, (BEFORE, CLOSED), exposures, adherence)


def two_resets() -> tuple[Exposure, ...]:
    return (
        bench("2026-09-08", *MISSED),
        bench("2026-09-15", *MISSED),
        bench("2026-09-22", *[(90, 5, 8)] * 3),
        bench("2026-10-06", *MISSED),
        bench("2026-10-13", *MISSED),
        bench("2026-10-20", *[(90, 5, 8)] * 3),
    )


def test_two_resets_on_a_linear_line_in_two_blocks_raise_cadence_slow() -> None:
    flag = cadence_signal(a_read(LINEAR, *two_resets()))

    assert flag is not None
    assert (flag.code, flag.scope.exercise_id, flag.rn) == (
        "cadence_slow",
        "bb_bench_press",
        "rn:training-level §2",
    )
    assert flag.params["metric"] == {"resets": 2}
    assert flag.params["blocks"] == ["b-2026-09-07", "b-2026-10-05"]


def test_one_reset_in_two_blocks_raises_nothing() -> None:
    assert cadence_signal(a_read(LINEAR, *two_resets()[3:])) is None


def test_adherence_under_the_floor_raises_nothing() -> None:
    assert cadence_signal(a_read(LINEAR, *two_resets(), adherence=0.75)) is None
    assert cadence_signal(a_read(LINEAR, *two_resets(), adherence=None)) is None


def test_the_signal_carries_its_switching_row() -> None:
    flag = cadence_signal(a_read(LINEAR, *two_resets()))

    assert flag is not None
    assert flag.params["may_schemes"] == ["double_progression", "top_backoff"]
    assert flag.params["never"] == "keep resetting"
    assert "double_progression" in str(flag.params["may"])


DOUBLE = a_line("bb_bench_press", working(3, (6, 8)))
TOP_BACKOFF = a_line(
    "bb_bench_press", working(1, 5, 8), working(3, 5, 7), scheme="top_backoff", pct_of_top=85
)
FLAT = ((100, 7, 8), (100, 7, 8), (100, 6, 8))
WEEKS = (
    "2026-09-08",
    "2026-09-15",
    "2026-09-22",
    "2026-09-29",
    "2026-10-06",
    "2026-10-13",
    "2026-10-20",
    "2026-10-27",
)


def flat_weeks(*days: str) -> tuple[Exposure, ...]:
    return tuple(bench(on, *FLAT) for on in days or WEEKS)


def test_a_double_progression_stall_open_at_both_block_ends_raises_cadence_slow() -> None:
    flag = cadence_signal(a_read(DOUBLE, *flat_weeks()))

    assert flag is not None
    assert (flag.code, flag.params["metric"]) == ("cadence_slow", {"stall_streak": 3})
    assert flag.params["may_schemes"] == []


def test_a_gain_at_the_end_of_the_closed_block_leaves_double_progression_unsignalled() -> None:
    exposures = (*flat_weeks(*WEEKS[:-1]), bench("2026-10-27", *[(105, 6, 8)] * 3))

    assert cadence_signal(a_read(DOUBLE, *exposures)) is None


def test_a_gain_between_two_stalls_is_progress_across_the_blocks() -> None:
    heavier = tuple(bench(on, *[(105, 7, 8)] * 3) for on in WEEKS[4:])

    assert cadence_signal(a_read(DOUBLE, *flat_weeks(*WEEKS[:4]), *heavier)) is None


def top_sets(load: float, *days: str) -> tuple[Exposure, ...]:
    return tuple(bench(on, (load, 5, 8), *[(85, 5, 7)] * 3) for on in days)


def test_a_flat_e1rm_across_two_blocks_on_top_backoff_raises_cadence_slow() -> None:
    flag = cadence_signal(a_read(TOP_BACKOFF, *top_sets(100, "2026-08-31", *WEEKS)))

    assert flag is not None
    assert flag.code == "cadence_slow"
    assert flag.params["metric"] == {"e1rm_from": 123.33, "e1rm_to": 123.33}
    assert flag.params["may_schemes"] == ["wave_531"]


def test_a_rising_e1rm_on_top_backoff_raises_nothing() -> None:
    exposures = (*top_sets(100, "2026-08-31", *WEEKS[:4]), *top_sets(105, *WEEKS[4:]))

    assert cadence_signal(a_read(TOP_BACKOFF, *exposures)) is None


def in_session(session_id: str, load: float, *days: str) -> tuple[Exposure, ...]:
    return tuple(
        an_exposure(on, (load, 5, 8), *[(85, 5, 7)] * 3, session_id=session_id) for on in days
    )


def test_a_rising_second_session_keeps_a_flat_first_session_line_from_cadence_slow() -> None:
    flat = in_session("push", 100, "2026-08-31", *WEEKS)
    rising = in_session("upper", 110, *WEEKS[4:])
    read = CadenceRead(TOP_BACKOFF, (BEFORE, CLOSED), (*flat, *rising), 0.9, session_id="push")

    assert cadence_signal(read) is None


def test_a_line_stall_is_read_on_its_own_session_only() -> None:
    stalled = tuple(an_exposure(on, *FLAT, session_id="push") for on in WEEKS)
    other = tuple(an_exposure(on, *[(105, 8, 8)] * 3, session_id="upper") for on in WEEKS[4:])
    read = CadenceRead(DOUBLE, (BEFORE, CLOSED), (*stalled, *other), 0.9, session_id="push")

    flag = cadence_signal(read)

    assert flag is not None
    assert flag.code == "cadence_slow"


def topped(*days: str) -> tuple[Exposure, ...]:
    return tuple(bench(on, *[(100 + 5 * i, 8, 8)] * 3) for i, on in enumerate(days))


def test_every_exposure_at_the_top_on_double_progression_raises_cadence_fast() -> None:
    flag = cadence_signal(a_read(DOUBLE, *topped(*WEEKS)))

    assert flag is not None
    assert (flag.code, flag.rn) == ("cadence_fast", "rn:training-level §2")
    assert flag.params["metric"] == {"exposures_at_top": 4}
    assert flag.params["may_schemes"] == ["linear"]
    assert "blocks" not in flag.params


def test_one_exposure_short_of_the_top_raises_no_cadence_fast() -> None:
    exposures = (*topped(*WEEKS[:-1]), bench("2026-10-27", (150, 8, 8), (150, 8, 8), (150, 7, 8)))

    assert cadence_signal(a_read(DOUBLE, *exposures)) is None


def test_the_top_reached_over_the_authored_rpe_raises_no_cadence_fast() -> None:
    exposures = (*topped(*WEEKS[:-1]), bench("2026-10-27", *[(150, 8, 9)] * 3))

    assert cadence_signal(a_read(DOUBLE, *exposures)) is None


def test_linear_and_hold_never_raise_cadence_fast() -> None:
    hold = a_line("bb_bench_press", working(3, (6, 8)), scheme="hold")

    assert cadence_signal(a_read(LINEAR, *topped(*WEEKS))) is None
    assert cadence_signal(a_read(hold, *topped(*WEEKS))) is None
    assert cadence_signal(a_read(hold, *flat_weeks())) is None


def test_the_one_row_cap_bound_on_every_top_backoff_prescription_raises_cadence_fast() -> None:
    rising = top_sets(100, "2026-08-31", *WEEKS[:4]), top_sets(105, *WEEKS[4:])
    exposures = tuple(e for part in rising for e in part)
    read = CadenceRead(TOP_BACKOFF, (BEFORE, CLOSED), exposures, 0.9, (True,) * 4)

    flag = cadence_signal(read)

    assert flag is not None
    assert (flag.code, flag.params["metric"]) == ("cadence_fast", {"capped": 4})
    uncapped = CadenceRead(TOP_BACKOFF, (BEFORE, CLOSED), exposures, 0.9, (True, False))
    assert cadence_signal(uncapped) is None
