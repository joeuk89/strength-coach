import datetime

from coach.core.closed_week.adherence import Adherence, adherence
from coach.core.closed_week.kind import WeekKind
from coach.core.closed_week.sessions import PlannedWork, SessionOutcome
from coach.core.closed_week.week import ClosedWeek
from coach.core.prescription import PlannedSession

TODAY = datetime.date(2026, 12, 6)
LAST_MONDAY = datetime.date(2026, 11, 30)


def outcome(trained: bool, tier: str = "core") -> SessionOutcome:
    session = PlannedSession("s", LAST_MONDAY, "home", "lifting", (), tier=tier)
    return SessionOutcome(PlannedWork(session), trained, True, tier == "core", trained)


def a_week(
    weeks_ago: int, trained: int, planned: int = 4, kind: WeekKind = "partial"
) -> ClosedWeek:
    sessions = tuple(outcome(n < trained) for n in range(planned))
    return ClosedWeek(LAST_MONDAY - datetime.timedelta(weeks=weeks_ago), kind, sessions)


def test_four_ordinary_weeks_at_75_percent_are_watch() -> None:
    weeks = [a_week(n, 3) for n in range(4)]

    assert adherence(weeks, TODAY) == Adherence("watch", 0.75, 4)


def test_three_ordinary_weeks_are_insufficient() -> None:
    weeks = [a_week(n, 4) for n in range(3)]

    assert adherence(weeks, TODAY).state == "insufficient"


def test_eighty_percent_is_ok_and_under_seventy_is_low() -> None:
    assert adherence([a_week(n, 4, 5) for n in range(4)], TODAY).state == "ok"
    assert adherence([a_week(n, 2, 3) for n in range(4)], TODAY).state == "low"


def test_only_the_last_four_ordinary_weeks_inside_eight_calendar_weeks_count() -> None:
    weeks = [
        a_week(0, 4),
        a_week(1, 0, kind="light"),
        a_week(2, 4),
        a_week(3, 4),
        a_week(4, 4),
        a_week(5, 0),
    ]
    assert adherence(weeks, TODAY) == Adherence("ok", 1.0, 4)

    stale = [a_week(0, 4), a_week(1, 4), a_week(2, 4), a_week(8, 4)]
    assert adherence(stale, TODAY).state == "insufficient"


def test_optional_sessions_never_enter_adherence() -> None:
    week = ClosedWeek(LAST_MONDAY, "hard", (outcome(True), outcome(False, "optional")))

    assert adherence([week] * 4, TODAY).figure == 1.0
