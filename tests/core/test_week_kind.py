import datetime

from support.exposures import an_exposure

from coach.core.closed_week.kind import is_return_week, week_kind
from coach.core.closed_week.match import WeekWorkout
from coach.core.closed_week.sessions import (
    PlannedWork,
    SessionOutcome,
    TargetSet,
    session_outcome,
)
from coach.core.prescription import PlannedSession, StatusSpan

MONDAY = datetime.date(2026, 11, 2)
SETS = (TargetSet(6, 8),) * 3


def a_session(
    n: int, workout: WeekWorkout | None, spans: tuple[StatusSpan, ...] = ()
) -> SessionOutcome:
    on = MONDAY + datetime.timedelta(days=n)
    work = PlannedWork(PlannedSession(f"s{n}", on, "home", "lifting", ()), {"bb_bench_press": SETS})
    return session_outcome(work, workout=workout, spans=spans)


def passed(n: int) -> SessionOutcome:
    exposure = an_exposure(MONDAY.isoformat(), *[(60, 6, 8)] * 3, workout_id=f"h-{n}")
    return a_session(n, workout=WeekWorkout(f"h-{n}", MONDAY, (exposure,)))


def failed(n: int) -> SessionOutcome:
    exposure = an_exposure(MONDAY.isoformat(), (60, 6, 8), workout_id=f"h-{n}")
    return a_session(n, workout=WeekWorkout(f"h-{n}", MONDAY, (exposure,)))


def missed(n: int) -> SessionOutcome:
    return a_session(n, workout=None)


def ill(n: int) -> SessionOutcome:
    on = MONDAY + datetime.timedelta(days=n)
    return a_session(n, workout=None, spans=(StatusSpan("ill", on, on),))


HARD = (passed(0), passed(1), passed(2), failed(3))


def test_a_plan_carrying_light_week_is_light_whatever_else_held() -> None:
    assert week_kind(HARD, carried={"light_week"}, returned=True) == "light"


def test_a_layoff_over_ten_days_is_return_when_no_light_week_was_carried() -> None:
    assert week_kind(HARD, carried=set(), returned=True) == "return"
    assert week_kind(HARD, carried={"minimum_week"}, returned=True) == "return"


def test_every_core_session_untrained_on_a_span_day_is_break_and_not_return() -> None:
    sessions = (ill(0), ill(1))

    assert week_kind(sessions, carried=set(), returned=False) == "break"
    assert week_kind(sessions, carried=set(), returned=True) == "return"


def test_minimum_and_one_off_weeks_hold_below_break() -> None:
    assert week_kind(HARD, carried={"minimum_week"}, returned=False) == "minimum"
    assert week_kind(HARD, carried={"one_off_week"}, returned=False) == "one_off"
    assert week_kind((ill(0),), carried={"minimum_week"}, returned=False) == "break"


def test_three_quarters_passing_is_hard_below_the_carried_kinds() -> None:
    assert week_kind(HARD, carried=set(), returned=False) == "hard"
    assert week_kind(HARD, carried={"one_off_week"}, returned=False) == "one_off"


def test_under_half_trained_is_missed_when_the_week_was_not_hard() -> None:
    assert week_kind((passed(0), missed(1), missed(2)), carried=set(), returned=False) == "missed"
    assert week_kind((passed(0), missed(1)), carried=set(), returned=False) != "missed"


def test_otherwise_the_week_is_partial() -> None:
    assert week_kind((passed(0), missed(1)), carried=set(), returned=False) == "partial"
    assert week_kind((failed(0), failed(1)), carried=set(), returned=False) == "partial"


def test_a_week_with_nothing_planned_is_partial() -> None:
    assert week_kind((), carried=set(), returned=False) == "partial"


def test_a_status_span_prorates_the_denominator() -> None:
    sessions = (passed(0), passed(1), passed(2), ill(3))

    assert week_kind(sessions, carried=set(), returned=False) == "hard"


def test_return_reads_the_gap_before_the_weeks_first_lifting_workout() -> None:
    dates = [datetime.date(2026, 10, 21), MONDAY + datetime.timedelta(days=1)]

    assert is_return_week(MONDAY, dates) is True
    assert is_return_week(MONDAY, [datetime.date(2026, 10, 23), MONDAY]) is False
    assert is_return_week(MONDAY, [datetime.date(2026, 10, 21)]) is False
