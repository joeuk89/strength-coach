import datetime

from support.blocks import BENCH_LINE, BOUNDARY, PULL_UP_LINE, WHY, a_drill, two_closed_blocks
from support.clock import FixedClock, at
from support.kit_fixtures import kit_files
from support.ledger import a_weigh_in
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config

from coach.core.progress import LiftProgress, Progress
from coach.services.program import adopt
from coach.services.progress import progress
from coach.store.connection import Connection

RISING = (100, 105, 105, 110, 115, 115)


def report(conn: Connection, *, full: bool = False) -> Progress:
    return progress(conn, on=BOUNDARY, units="lb", bodyweight_units="kg", full=full)


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


def test_the_dose_target_is_the_one_the_blocks_newest_closed_week_carried() -> None:
    conn = a_store()
    later = a_draft(
        a_session("push", BENCH_LINE, PULL_UP_LINE),
        kind="amend",
        dose={"per_muscle": 12, "lift": {"bb_bench_press": 9, "pull_up": 7}},
    )
    adopt(
        conn,
        toml(later),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(at(BOUNDARY)),
    )

    assert report(conn).dose_target == {"per_muscle": 10, "bb_bench_press": 8, "pull_up": 8}


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


LINEAR_BENCH = a_line(
    "bb_bench_press",
    sets=[{"count": 4, "reps": 6, "rpe": 8}],
    scheme={"name": "linear"},
    start_load=100,
)
DROP_AFTER_MISSES = (100, 100, 100, 100, 90, 90)


def bench_in(found: Progress) -> LiftProgress:
    return next(lift for lift in found.lifts if lift.exercise_id == "bb_bench_press")


def test_a_load_drop_after_misses_on_linear_counts_as_a_reset() -> None:
    conn = two_closed_blocks(bench_tops=DROP_AFTER_MISSES, bench_line=LINEAR_BENCH)

    assert bench_in(report(conn)).resets == 1


def test_a_drop_before_the_lift_moved_to_linear_is_no_reset() -> None:
    conn = two_closed_blocks(bench_tops=DROP_AFTER_MISSES)
    adopt(
        conn,
        toml(a_draft(a_session("push", LINEAR_BENCH, PULL_UP_LINE), kind="amend", because="slow")),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(at(BOUNDARY)),
    )

    bench = bench_in(report(conn))

    assert (bench.scheme, bench.resets, bench.stall_streak) == ("linear", 0, 0)


def pull_up_in(found: Progress) -> LiftProgress:
    return next(lift for lift in found.lifts if lift.exercise_id == "pull_up")


def test_flat_pull_ups_that_predate_the_latest_redesign_show_no_stall_streak() -> None:
    conn = two_closed_blocks()
    assert pull_up_in(report(conn)).stall_streak == 3
    adopt(
        conn,
        toml(a_draft(a_session("push", BENCH_LINE, PULL_UP_LINE), because="new block")),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(at(BOUNDARY)),
    )

    assert pull_up_in(report(conn)).stall_streak == 0


def test_a_practice_line_shows_a_stall_streak_of_zero_on_flat_pull_ups() -> None:
    conn = two_closed_blocks(practice_pull_ups=True)

    assert pull_up_in(report(conn)).stall_streak == 0


def test_a_lift_on_a_practice_line_and_a_lifting_line_shows_the_lifting_lines_stall() -> None:
    conn = two_closed_blocks()
    adopt(
        conn,
        toml(a_draft(a_drill(PULL_UP_LINE), a_session("push", BENCH_LINE, PULL_UP_LINE))),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )

    assert pull_up_in(report(conn)).stall_streak == 3
