import datetime

from coach.core.closed_week.match import (
    Activity,
    WeekWorkout,
    conditioning_activity,
    match_week,
    workout_class,
)
from coach.core.exposure import LibraryEntry
from coach.core.log import StoredSet
from coach.core.prescription import PlannedSession

MONDAY = datetime.date(2026, 11, 2)


def day(n: int) -> datetime.date:
    return MONDAY + datetime.timedelta(days=n)


def a_planned(session_id: str, on: int, cadence: str = "weekly") -> PlannedSession:
    return PlannedSession(session_id, day(on), "home", "lifting", (), cadence)


def a_workout(id_: str, on: int, routine: str | None = None, start: str = "") -> WeekWorkout:
    return WeekWorkout(id_, day(on), routine_id=routine, started=start)


def matched(
    planned: list[PlannedSession],
    workouts: list[WeekWorkout],
    routines: dict[str, str] | None = None,
    claims: dict[str, tuple[datetime.date, str]] | None = None,
) -> dict[str, str]:
    found = match_week(planned, workouts, routines=routines or {}, claims=claims or {})
    return {workout: session.session_id for workout, session in found.items()}


def test_a_workout_on_the_planned_date_from_the_sessions_routine_matches_it() -> None:
    found = matched([a_planned("lower", 0)], [a_workout("h-1", 0, "r-lower")], {"lower": "r-lower"})

    assert found == {"h-1": "lower"}


def test_a_second_workout_that_day_is_unmatched() -> None:
    workouts = [a_workout("h-2", 0, start="18:00"), a_workout("h-1", 0, start="07:00")]

    assert matched([a_planned("lower", 0)], workouts) == {"h-1": "lower"}


def test_a_workout_from_a_routine_on_a_day_no_window_covers_is_unmatched() -> None:
    found = matched([a_planned("lower", 0)], [a_workout("h-1", 1, "r-lower")], {"lower": "r-lower"})

    assert found == {}


def test_the_routine_breaks_the_tie_inside_the_window() -> None:
    planned = [a_planned("lower", 0), a_planned("mobility", 0, "standing")]

    found = matched(planned, [a_workout("h-1", 0, "r-mob")], {"mobility": "r-mob"})

    assert found == {"h-1": "mobility"}


def test_without_a_routine_a_workout_takes_the_first_candidate_in_session_order() -> None:
    planned = [a_planned("lower", 0), a_planned("mobility", 0, "standing")]

    assert matched(planned, [a_workout("h-1", 0), a_workout("h-2", 0)]) == {
        "h-1": "lower",
        "h-2": "mobility",
    }


def test_a_standing_session_covers_any_day_of_the_week_and_a_daily_one_its_day() -> None:
    planned = [a_planned("mobility", 0, "standing"), a_planned("hang", 3, "daily")]

    assert matched(planned, [a_workout("h-1", 6)]) == {"h-1": "mobility"}
    assert matched(planned[1:], [a_workout("h-1", 4)]) == {}
    assert matched(planned[1:], [a_workout("h-1", 3)]) == {"h-1": "hang"}


def test_a_match_claim_moves_a_workout_to_the_session_it_names() -> None:
    planned = [a_planned("lower", 0), a_planned("push", 2)]
    workouts = [a_workout("h-1", 0, start="07:00"), a_workout("h-2", 0, start="18:00")]

    found = matched(planned, workouts, claims={"h-1": (day(2), "push")})

    assert found == {"h-1": "push", "h-2": "lower"}


def a_set(template: str) -> StoredSet:
    return StoredSet(0, template, None, "working", None, None, 1200, None, None, None)


LIBRARY = {
    "RUN": LibraryEntry("run", "distance"),
    "ROW": LibraryEntry("rower", "duration"),
    "SQ": LibraryEntry("bb_back_squat", "total"),
}


def test_an_unmatched_workout_is_classed_by_its_content() -> None:
    assert workout_class([a_set("RUN"), a_set("ROW")], LIBRARY) == "conditioning"
    assert workout_class([a_set("RUN"), a_set("SQ")], LIBRARY) == "lifting"
    assert workout_class([a_set("UNKNOWN")], LIBRARY) == "unmapped"


def test_a_conditioning_workout_is_an_activity_rated_7_when_unrated() -> None:
    assert conditioning_activity(MONDAY, 30, []) == Activity(MONDAY, 30, 7.0, True)
    assert conditioning_activity(MONDAY, 40, [5.0, 6.0]) == Activity(MONDAY, 40, 5.5, False)
