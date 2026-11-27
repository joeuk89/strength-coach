import datetime
from typing import cast

import pytest

from coach.core import check_in_card as card
from coach.core.check_in_card import Ask
from coach.core.closed_week.match import WeekWorkout
from coach.core.closed_week.sessions import PlannedWork, session_outcome
from coach.core.closed_week.week import ClosedWeek
from coach.core.exposure import Exposure, ExposureSet
from coach.core.load import Load
from coach.core.prescription import PlannedSession

MONDAY = datetime.date(2026, 11, 2)
PT = PlannedSession("pt", MONDAY, "gym", "coach_led", ())
REF = "planned_session:2026-11-02/pt"


def a_workout(
    *rpes: float | None,
    session_rpe: float | None = None,
    id_: str = "w-1",
    minutes: int | None = 60,
    started: str = "",
) -> WeekWorkout:
    sets = tuple(ExposureSet(i, "working", Load(60, "total"), 8, rpe) for i, rpe in enumerate(rpes))
    exposures = (Exposure(id_, "bb_bench_press", MONDAY, sets),) if sets else ()
    return WeekWorkout(
        id_, MONDAY, exposures, minutes=minutes, session_rpe=session_rpe, started=started
    )


def a_read(*workouts: WeekWorkout) -> card.SessionRead:
    outcome = session_outcome(PlannedWork(PT), workouts=workouts)
    return card.SessionRead(outcome, closes=True)


def test_a_matched_coach_led_session_prefills_minutes_and_the_mean_working_set_rpe() -> None:
    found = card.sessions([a_read(a_workout(7, 8, 9))])

    assert found is not None
    [row] = cast(list[dict[str, object]], found.facts["core"])
    assert (row["state"], row["workouts"], row["minutes"], row["session_rpe"]) == (
        "matched",
        ["w-1"],
        60,
        8.0,
    )
    assert found.asks == ()


def test_a_session_split_across_two_workouts_lists_both_and_sums_their_minutes() -> None:
    morning = a_workout(7, 7, id_="w-1", minutes=40, started="07:00")
    afternoon = a_workout(9, 9, id_="w-2", minutes=25, started="15:00")

    found = card.sessions([a_read(afternoon, morning)])

    assert found is not None
    [row] = cast(list[dict[str, object]], found.facts["core"])
    assert (row["workouts"], row["minutes"], row["session_rpe"]) == (["w-1", "w-2"], 65, 8.0)


def test_session_rpe_is_asked_only_when_the_sets_carry_none() -> None:
    found = card.sessions([a_read(a_workout(None, None))])

    assert found is not None
    assert found.asks == (Ask("session_rpe", REF),)


def test_a_hand_entered_workout_carries_its_own_session_rpe() -> None:
    found = card.sessions([a_read(a_workout(session_rpe=9))])

    assert found is not None
    assert found.asks == ()


def test_an_untrained_session_is_a_miss_only_once_its_week_closes() -> None:
    outcome = session_outcome(PlannedWork(PT))

    assert card.SessionRead(outcome, closes=True).state == "missed"
    assert card.SessionRead(outcome, closes=False).state == "to_come"


SQUAT = card.LiftRead("bb_back_squat", False, True, (100, 5, 8), 120, 115)
BENCH = card.LiftRead("bb_bench_press", True, True, (80, 5, 8), 95, 95)
CURL = card.LiftRead("db_curl", False, False, (15, 12, 8), 20, 20)


def test_priority_lifts_lead_then_compounds_and_only_soreness_and_niggles_is_asked() -> None:
    found = card.lifts([CURL, SQUAT, BENCH], emphasis="strength")

    assert found is not None
    rows = cast(list[dict[str, object]], found.facts["rows"])
    assert [r["exercise"] for r in rows] == ["bb_bench_press", "bb_back_squat", "db_curl"]
    assert found.asks == (Ask("soreness_and_niggles"),)


def test_a_timed_lift_unmatched_to_a_session_shows_its_seconds_and_no_prescription() -> None:
    hang = card.LiftRead("dead_hang", False, False, (None, None, None), seconds=(25, 21))

    found = card.lifts([hang], emphasis="strength")

    assert found is not None
    (row,) = cast(list[dict[str, object]], found.facts["rows"])
    assert (row["seconds"], row["prescribed_seconds"]) == ([25, 21], None)


@pytest.mark.parametrize("emphasis", ["hypertrophy", "strength", "maintenance"])
def test_every_emphasis_asks_soreness_and_niggles_and_nothing_the_log_answers(
    emphasis: str,
) -> None:
    found = card.lifts([CURL, SQUAT, BENCH], emphasis=emphasis)

    assert found is not None
    assert found.asks == (Ask("soreness_and_niggles"),)


def a_dosed_week(weeks_ago: int, pull_up: int) -> ClosedWeek:
    return ClosedWeek(
        MONDAY - datetime.timedelta(weeks=weeks_ago),
        "hard",
        dose={"lats": 12.5},
        dose_target=10,
        lift_dose={"pull_up": pull_up},
        lift_dose_target={"pull_up": 8},
    )


def test_the_dose_field_gives_each_lift_its_figure_target_and_trailing_mean() -> None:
    weeks = [a_dosed_week(3, 6), a_dosed_week(2, 8), a_dosed_week(1, 9), a_dosed_week(0, 11)]

    found = card.dose(weeks[-1:], weeks)

    assert found is not None
    assert found.facts["lifts"] == [
        {"lift": "pull_up", "delivered": 11, "target": 8, "mean": 8.5},
    ]
    assert found.facts["muscles"] == [{"muscle": "lats", "delivered": 12.5, "mean": 12.5}]


CHECK_IN = datetime.date(2026, 11, 11)


def test_the_sleep_count_reads_the_seven_nights_before_the_check_in_on_a_ten_day_window() -> None:
    nights = {
        datetime.date(2026, 11, 1): 5.0,
        datetime.date(2026, 11, 2): 5.0,
        datetime.date(2026, 11, 3): 5.0,
        datetime.date(2026, 11, 4): 6.0,
        datetime.date(2026, 11, 6): 6.5,
        datetime.date(2026, 11, 8): 8.0,
        datetime.date(2026, 11, 10): 6.9,
        datetime.date(2026, 11, 11): 4.0,
    }

    found = card.sleep(nights, CHECK_IN)

    assert found.facts == {"nights": 4, "short_nights": 3, "short_sleep_week": False}
    assert found.asks == ()


def test_four_short_nights_in_the_seven_read_make_the_card_a_short_sleep_week() -> None:
    nights = {datetime.date(2026, 11, d): 6.0 for d in (4, 5, 7, 10)}

    found = card.sleep(nights, CHECK_IN)

    assert found.facts == {"nights": 4, "short_nights": 4, "short_sleep_week": True}


def test_the_sleep_ask_states_the_threshold_and_the_nights_it_wants() -> None:
    found = card.sleep({datetime.date(2026, 11, 3): 5.0}, CHECK_IN)

    assert found.facts["nights"] == 0
    assert found.asks == (
        Ask(
            "sleep_nights",
            detail={
                "record": "sleep_night",
                "under_hours": 7,
                "nights": [f"2026-11-{d:02d}" for d in range(4, 11)],
                "give": "night and hours for every night under 7 hours; other nights optional",
            },
        ),
    )
