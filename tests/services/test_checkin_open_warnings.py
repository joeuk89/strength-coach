import datetime

from support.check_in_cards import opened
from support.clock import FixedClock
from support.ledger import a_store, a_weigh_in
from support.plans import a_squat_program

from coach.core.goal import PhaseOpen, Until
from coach.services.record import record
from coach.store import phases
from coach.store.connection import Connection

TODAY = datetime.date(2026, 11, 29)


def recorded(conn: Connection, text: str) -> None:
    record(conn, text.encode(), file="d.toml", clock=FixedClock())


def codes(conn: Connection) -> list[str]:
    return [w.code for w in opened(conn, TODAY).warnings]


def a_phase(conn: Connection, kind: str, rate: float, until: Until) -> None:
    with conn:
        phases.insert(
            conn,
            id_="ph-0001",
            phase=PhaseOpen(kind, rate, until, "cutting for the meet"),
            opened="2026-10-01",
            opened_by="goal:g-0001",
            draft_hash="sha256:ph",
            recorded_at="2026-10-01T09:00:00+00:00",
        )


def test_an_open_niggle_with_no_constraint_raises_niggle_unconstrained() -> None:
    conn = a_store()
    recorded(
        conn,
        '[[niggle]]\nsite = "left knee"\nopened = 2026-11-20\ndate = 2026-11-20\n'
        'status = "reported"\n',
    )

    [flag] = opened(conn, TODAY).warnings

    assert (flag.code, flag.params["niggle_id"]) == ("niggle_unconstrained", "n-0001")


def test_a_follow_up_past_due_raises_followup_due_and_one_not_yet_due_does_not() -> None:
    conn = a_store()
    recorded(conn, '[[follow_up]]\nraised = 2026-11-01\ntext = "retest"\ndue = 2026-11-28\n')
    recorded(conn, '[[follow_up]]\nraised = 2026-11-01\ntext = "later"\ndue = 2026-12-20\n')

    [flag] = opened(conn, TODAY).warnings

    assert (flag.code, flag.params) == (
        "followup_due",
        {"follow_up_id": "f-0001", "due": "2026-11-28"},
    )


def test_a_14_day_average_meeting_the_bodyweight_condition_raises_phase_condition_met() -> None:
    conn = a_store()
    a_phase(conn, "deficit", -0.5, Until("bodyweight_at_or_below", 80))
    a_weigh_in(conn, "2026-11-20", 80.4, id_="wi-0001")
    a_weigh_in(conn, "2026-11-27", 79.4, id_="wi-0002")

    assert codes(conn) == ["phase_condition_met"]


def test_an_average_above_the_condition_raises_nothing() -> None:
    conn = a_store()
    a_phase(conn, "deficit", -0.5, Until("bodyweight_at_or_below", 75))
    a_weigh_in(conn, "2026-11-27", 79.4, id_="wi-0001")

    assert codes(conn) == []


def test_the_bodyweight_condition_reads_bodyweight_units_not_the_lift_units() -> None:
    conn = a_store()
    a_phase(conn, "surplus", 0.25, Until("bodyweight_at_or_above", 170))
    a_weigh_in(conn, "2026-11-27", 79.4, id_="wi-0001")

    assert [w.code for w in opened(conn, TODAY, bodyweight_units="lb").warnings] == [
        "phase_condition_met"
    ]
    assert codes(conn) == []


def test_an_observed_rate_outside_the_band_after_28_days_raises_phase_trend_off() -> None:
    conn = a_store()
    a_phase(conn, "deficit", -0.5, Until("coachs_call"))
    a_weigh_in(conn, "2026-11-01", 80.0, id_="wi-0001")
    a_weigh_in(conn, "2026-11-29", 80.0, id_="wi-0002")

    assert codes(conn) == ["phase_trend_off"]


def test_under_28_days_of_weigh_ins_the_trend_is_not_judged() -> None:
    conn = a_store()
    a_phase(conn, "deficit", -0.5, Until("coachs_call"))
    a_weigh_in(conn, "2026-11-10", 80.0, id_="wi-0001")
    a_weigh_in(conn, "2026-11-29", 80.0, id_="wi-0002")

    assert codes(conn) == []


def test_a_training_max_on_a_lift_whose_scheme_reads_none_raises_training_max_unused() -> None:
    conn = a_squat_program()
    recorded(
        conn,
        '[[decision]]\nkind = "training_max"\nexercise = "bb_back_squat"\nload = 140\n'
        'because = "coach_judgement"\ntext = "tested single"\n',
    )

    [flag] = opened(conn, TODAY).warnings

    assert (flag.code, flag.scope.exercise_id, flag.params["scheme"]) == (
        "training_max_unused",
        "bb_back_squat",
        "double_progression",
    )


def an_activity(conn: Connection, on: str, *, rpe: float = 5, distance_km: float = 5) -> None:
    quality = "true" if rpe >= 7 else "false"
    recorded(
        conn,
        f'[[activity]]\ndate = {on}\nkind = "run"\nminutes = 40\nrpe = {rpe}\n'
        f"quality = {quality}\ndistance_km = {distance_km}\n",
    )


def test_three_quality_activities_in_a_week_raise_activity_cap_exceeded() -> None:
    conn = a_store()
    for on in ("2026-11-23", "2026-11-25", "2026-11-27"):
        an_activity(conn, on, rpe=8)

    assert codes(conn) == ["activity_cap_exceeded"]


def test_a_run_1_2_times_the_30_day_longest_with_14_days_of_history_raises_run_spike() -> None:
    conn = a_store()
    an_activity(conn, "2026-11-05", distance_km=10)
    an_activity(conn, "2026-11-29", distance_km=12)

    [flag] = opened(conn, TODAY).warnings

    assert (flag.code, flag.scope.workout_id, flag.params["ratio"]) == (
        "run_spike",
        "ac-0002",
        1.2,
    )


def test_without_14_days_of_activity_history_the_run_is_not_judged() -> None:
    conn = a_store()
    an_activity(conn, "2026-11-18", distance_km=10)
    an_activity(conn, "2026-11-29", distance_km=12)

    assert codes(conn) == []
