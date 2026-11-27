"""A matched core session with under one-third of its prescribed working sets logged
(docs/spec/week.md, "The session gate")."""

import datetime

from support.exposures import an_exposure

from coach.core.closed_week.against import TargetSet
from coach.core.closed_week.match import WeekWorkout
from coach.core.closed_week.sessions import PlannedWork, session_near_empty, session_outcome
from coach.core.flag import Scope
from coach.core.prescription import PlannedSession

MONDAY = datetime.date(2026, 11, 2)
FRIDAY = datetime.date(2026, 11, 6)
SET = TargetSet(5, 8)


def fri_squat(squat: int = 5, pull_up: int = 15) -> PlannedWork:
    session = PlannedSession("fri-squat", FRIDAY, "home", "lifting", (), "weekly", "core")
    return PlannedWork(session, {"bb_back_squat": (SET,) * squat, "pull_up": (SET,) * pull_up})


def a_workout(workout_id: str, started: str, **sets: int) -> WeekWorkout:
    exposures = tuple(
        an_exposure(
            FRIDAY.isoformat(), *[(100, 5, 10.0)] * count, workout_id=workout_id, exercise_id=e
        )
        for e, count in sets.items()
    )
    return WeekWorkout(workout_id, FRIDAY, exposures, started=started)


def test_one_of_twenty_prescribed_sets_logged_is_near_empty() -> None:
    outcome = session_outcome(fri_squat(), workouts=(a_workout("h-1", "07:00", pull_up=1),))

    assert (outcome.sets_logged, outcome.sets_prescribed) == (1, 20)
    assert outcome.near_empty is True
    assert outcome.trained is True


def test_exactly_one_third_of_the_sets_logged_is_not_near_empty() -> None:
    outcome = session_outcome(
        fri_squat(squat=3, pull_up=6), workouts=(a_workout("h-1", "07:00", pull_up=3),)
    )

    assert (outcome.sets_logged, outcome.sets_prescribed) == (3, 9)
    assert outcome.near_empty is False


def test_two_workouts_of_a_split_session_together_over_the_floor_are_not_near_empty() -> None:
    first = a_workout("h-1", "07:00", pull_up=4)
    second = a_workout("h-2", "15:00", bb_back_squat=3)

    outcome = session_outcome(fri_squat(), workouts=(first, second))

    assert outcome.sets_logged == 7
    assert outcome.near_empty is False


def test_sets_logged_beyond_a_lines_prescription_do_not_count_toward_the_floor() -> None:
    outcome = session_outcome(
        fri_squat(squat=2, pull_up=10), workouts=(a_workout("h-1", "07:00", bb_back_squat=5),)
    )

    assert outcome.sets_logged == 2
    assert outcome.near_empty is True


def test_an_untrained_session_is_not_near_empty() -> None:
    assert session_outcome(fri_squat()).near_empty is False


def test_a_coach_led_session_is_never_near_empty() -> None:
    session = PlannedSession("pt", FRIDAY, "gym", "coach_led", (), "weekly", "core")

    outcome = session_outcome(PlannedWork(session), workouts=(WeekWorkout("w-1", FRIDAY),))

    assert (outcome.sets_prescribed, outcome.near_empty) == (0, False)


def test_a_near_empty_session_raises_the_warning_with_its_coverage() -> None:
    outcome = session_outcome(fri_squat(), workouts=(a_workout("h-1", "07:00", pull_up=1),))

    flag = session_near_empty(outcome)

    assert flag is not None
    assert (flag.code, flag.severity) == ("session_near_empty", "warning")
    assert flag.scope == Scope("session", MONDAY, session_id="fri-squat")
    assert flag.params == {"date": "2026-11-06", "sets_logged": 1, "sets_prescribed": 20}


def test_a_session_over_the_floor_raises_no_warning() -> None:
    outcome = session_outcome(fri_squat(), workouts=(a_workout("h-1", "07:00", pull_up=7),))

    assert session_near_empty(outcome) is None


def test_a_miss_tag_untrains_a_matched_session_and_answers_the_warning() -> None:
    outcome = session_outcome(
        fri_squat(), workouts=(a_workout("h-1", "07:00", pull_up=1),), miss_tagged=True
    )

    assert (outcome.trained, outcome.passed, outcome.in_adherence) == (False, False, True)
    assert outcome.workout_ids == ("h-1",)
    assert session_near_empty(outcome) is None
