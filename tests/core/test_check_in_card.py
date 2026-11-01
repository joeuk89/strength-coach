import datetime
from typing import cast

from coach.core import check_in_card as card
from coach.core.check_in_card import Ask
from coach.core.closed_week.match import WeekWorkout
from coach.core.closed_week.sessions import PlannedWork, session_outcome
from coach.core.exposure import Exposure, ExposureSet
from coach.core.load import Load
from coach.core.prescription import PlannedSession

MONDAY = datetime.date(2026, 11, 2)
PT = PlannedSession("pt", MONDAY, "gym", "coach_led", ())
REF = "planned_session:2026-11-02/pt"


def a_workout(*rpes: float | None, session_rpe: float | None = None) -> WeekWorkout:
    sets = tuple(ExposureSet(i, "working", Load(60, "total"), 8, rpe) for i, rpe in enumerate(rpes))
    exposures = (Exposure("w-1", "bb_bench_press", MONDAY, sets),) if sets else ()
    return WeekWorkout("w-1", MONDAY, exposures, minutes=60, session_rpe=session_rpe)


def a_read(workout: WeekWorkout | None) -> card.SessionRead:
    outcome = session_outcome(PlannedWork(PT), workout=workout)
    return card.SessionRead(outcome, workout, closes=True)


def test_a_matched_coach_led_session_prefills_minutes_and_the_mean_working_set_rpe() -> None:
    found = card.sessions([a_read(a_workout(7, 8, 9))])

    assert found is not None
    [row] = cast(list[dict[str, object]], found.facts["core"])
    assert (row["state"], row["minutes"], row["session_rpe"]) == ("matched", 60, 8.0)
    assert found.asks == ()


def test_session_rpe_is_asked_only_when_the_sets_carry_none() -> None:
    found = card.sessions([a_read(a_workout(None, None))])

    assert found is not None
    assert found.asks == (Ask("session_rpe", REF),)


def test_a_hand_entered_workout_carries_its_own_session_rpe() -> None:
    found = card.sessions([a_read(a_workout(session_rpe=9))])

    assert found is not None
    assert found.asks == ()


def test_an_untrained_session_is_a_miss_only_once_its_week_closes() -> None:
    outcome = session_outcome(PlannedWork(PT), workout=None)

    assert card.SessionRead(outcome, None, closes=True).state == "missed"
    assert card.SessionRead(outcome, None, closes=False).state == "to_come"


SQUAT = card.LiftRead("bb_back_squat", False, True, (100, 5, 8), 120, 115)
BENCH = card.LiftRead("bb_bench_press", True, True, (80, 5, 8), 95, 95)
CURL = card.LiftRead("db_curl", False, False, (15, 12, 8), 20, 20)


def test_priority_lifts_lead_then_compounds_and_are_asked_how_the_top_set_felt() -> None:
    found = card.lifts([CURL, SQUAT, BENCH], emphasis="strength")

    assert found is not None
    rows = cast(list[dict[str, object]], found.facts["rows"])
    assert [r["exercise"] for r in rows] == ["bb_bench_press", "bb_back_squat", "db_curl"]
    assert found.asks == (Ask("top_set_feel", "exercise:bb_bench_press"),)


def test_hypertrophy_asks_reps_and_rir_on_the_lines_that_moved_and_a_pump_read() -> None:
    found = card.lifts([CURL, SQUAT], emphasis="hypertrophy")

    assert found is not None
    assert found.asks == (
        Ask("reps_and_rir", "exercise:bb_back_squat"),
        Ask("pump_and_soreness"),
    )


def test_maintenance_asks_whether_the_kept_lifts_held() -> None:
    found = card.lifts([SQUAT], emphasis="maintenance")

    assert found is not None
    assert found.asks == (Ask("kept_lifts_held"),)
