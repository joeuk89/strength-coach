import datetime

from support.blocks import BOUNDARY, WHY, two_closed_blocks
from support.clock import FixedClock, at
from support.ledger import a_weigh_in

from coach.services.progress import Progress, progress
from coach.store.connection import Connection

RISING = (100, 105, 105, 110, 115, 115)


def report(conn: Connection, *, full: bool = False) -> Progress:
    return progress(conn, FixedClock(at(BOUNDARY)), units="lb", bodyweight_units="kg", full=full)


def a_store() -> Connection:
    conn = two_closed_blocks(bench_tops=RISING, pull_up_reps=(6, 6, 7, 7, 8, 8))
    a_weigh_in(conn, "2026-11-10", 80.0, id_="wi-0001")
    a_weigh_in(conn, "2026-11-28", 80.0, id_="wi-0002")
    a_weigh_in(conn, "2026-12-05", 80.2, id_="wi-0003")
    a_weigh_in(conn, "2026-12-12", 80.4, id_="wi-0004")
    return conn


def test_the_report_shows_bench_e1rm_over_each_closed_block() -> None:
    bench = next(lift for lift in report(a_store()).lifts if lift.exercise_id == "bb_bench_press")

    assert bench.e1rm_by_block == (("b-2026-10-30", 129.5), ("b-2026-11-23", 141.83))
    assert bench.e1rm_now == 141.83
    assert (bench.scheme, bench.stall_streak, bench.resets, bench.signal) == (
        "top_backoff",
        0,
        0,
        None,
    )


def test_the_report_shows_the_pull_ups_best_reps() -> None:
    pull_up = next(lift for lift in report(a_store()).lifts if lift.exercise_id == "pull_up")

    assert pull_up.best is not None
    assert (pull_up.best.reps, pull_up.best.load, pull_up.best.date) == (
        8,
        None,
        datetime.date(2026, 11, 30),
    )


def test_the_report_shows_dose_by_muscle_and_lift_for_each_week_of_the_closed_block() -> None:
    found = report(a_store())

    assert [(w.monday.isoformat(), w.kind) for w in found.dose] == [
        ("2026-11-23", "hard"),
        ("2026-11-30", "hard"),
        ("2026-12-07", "light"),
    ]
    first = found.dose[0]
    assert first.muscles["chest"] == 4
    assert first.lifts == {"bb_bench_press": 4, "pull_up": 3}


def test_the_report_shows_the_phase_trend_and_the_goals_why_verbatim() -> None:
    found = report(a_store())

    assert found.goal is not None
    assert (found.goal.kind, found.goal.why, found.goal.adopted) == (
        "hypertrophy",
        WHY,
        "2026-10-01",
    )
    assert found.phase is not None
    assert (found.phase.kind, found.phase.observed_rate, found.phase.met) == (
        "maintenance",
        0.09,
        False,
    )


def test_the_report_shows_milestones_reached_and_to_go() -> None:
    found = report(a_store())

    assert [(m.reached, m.to_go, m.computable) for m in found.milestones] == [
        (datetime.date(2026, 11, 23), None, True),
        (datetime.date(2026, 12, 7), None, True),
    ]
