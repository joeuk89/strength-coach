import datetime

from support.clock import FixedClock
from support.closed_weeks import (
    a_check_in,
    a_hard_squat_week,
    a_planned_squat_week,
    closed_through,
    monday,
)
from support.history import a_logged_workout, an_annotation
from support.ledger import an_exercise
from support.plans import a_plan_override, a_squat_program, squat_logged

from coach.core.closed_week.adherence import adherence
from coach.services.closed_weeks import closed_weeks
from coach.services.record import record
from coach.store.connection import Connection


def kinds(conn: Connection) -> list[tuple[str, str]]:
    return [(w.monday.isoformat(), w.kind) for w in closed_weeks(conn).weeks]


def test_a_week_is_closed_once_a_current_check_in_window_covers_its_sunday() -> None:
    conn = a_squat_program()
    a_hard_squat_week(conn, monday(0))
    a_hard_squat_week(conn, monday(1))
    a_check_in(conn, monday(0), "2026-11-10")

    assert kinds(conn) == [("2026-11-02", "hard")]


def test_a_match_annotation_moves_a_workout_logged_on_the_wrong_date() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-1", "2026-11-03", *[(120, 8, 8)] * 4)
    closed_through(conn, 1)
    assert kinds(conn) == [("2026-11-02", "missed")]

    an_annotation(
        conn, "a-0001", "match", "workout:h-1", planned_session="planned_session:2026-11-02/lower"
    )

    assert kinds(conn) == [("2026-11-02", "hard")]


def test_a_match_annotation_moves_a_workout_into_the_week_before_its_date() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    a_planned_squat_week(conn, monday(1))
    squat_logged(conn, "h-1", monday(1), *[(120, 8, 8)] * 4)
    an_annotation(
        conn, "a-0001", "match", "workout:h-1", planned_session="planned_session:2026-11-02/lower"
    )
    closed_through(conn, 2)

    first, second = closed_weeks(conn).weeks

    assert (first.kind, second.kind) == ("hard", "missed")
    assert first.dose
    assert second.dose == {}


def test_a_light_week_closes_the_block_and_the_next_hard_week_counts_1_in_a_new_one() -> None:
    conn = a_squat_program()
    a_hard_squat_week(conn, monday(0))
    plan_id = a_hard_squat_week(conn, monday(1))
    a_plan_override(conn, plan_id, "light_week", None, None)
    a_hard_squat_week(conn, monday(2))
    closed_through(conn, 3)

    found = closed_weeks(conn)

    assert [w.kind for w in found.weeks] == ["hard", "light", "hard"]
    assert [(b.id, b.hard_weeks) for b in found.blocks] == [
        ("b-2026-10-30", 1),
        ("b-2026-11-16", 1),
    ]


def test_a_trained_unlogged_session_is_a_lifting_date_so_the_next_week_is_no_return() -> None:
    conn = a_squat_program()
    a_hard_squat_week(conn, monday(0))
    a_planned_squat_week(conn, monday(1))
    an_annotation(conn, "a-0001", "trained_unlogged", f"planned_session:{monday(1)}/lower")
    a_hard_squat_week(conn, monday(2))
    closed_through(conn, 3)

    found = closed_weeks(conn)

    assert found.weeks[2].kind == "hard"
    assert [(b.id, b.hard_weeks) for b in found.blocks] == [("b-2026-10-30", 2)]


def test_a_hand_entered_workout_with_no_sets_is_a_lifting_date_so_the_next_week_is_no_return() -> (
    None
):
    conn = a_squat_program()
    a_hard_squat_week(conn, monday(0))
    a_planned_squat_week(conn, monday(1))
    a_logged_workout(conn, "w-1", monday(1), session_id="lower")
    a_hard_squat_week(conn, monday(2))
    closed_through(conn, 3)

    found = closed_weeks(conn)

    assert found.weeks[2].kind == "hard"
    assert [(b.id, b.hard_weeks) for b in found.blocks] == [("b-2026-10-30", 2)]


def a_core_rehab_niggle(conn: Connection, opened: str) -> None:
    an_exercise(conn, "band_external_rotation", load_mode="band", equipment_kind="band")
    niggle = f"""
[[niggle]]
site = "left shoulder"
date = {opened}
status = "reported"

[niggle.rehab]
session = "shoulder_rehab"
title = "Shoulder rehab"
tier = "core"
cadence = "standing"

[[niggle.rehab.line]]
exercise = "band_external_rotation"
rest_s = 30

[[niggle.rehab.line.sets]]
count = 2
reps = 15
"""
    record(conn, niggle.encode(), file="n.toml", clock=FixedClock())


def adherence_counts(conn: Connection) -> list[tuple[int, int]]:
    return [(w.adherence_trained, w.adherence_planned) for w in closed_weeks(conn).weeks]


def test_a_niggle_opened_after_the_weeks_closed_leaves_their_planned_sessions_alone() -> None:
    conn = a_squat_program()
    for n in range(4):
        a_hard_squat_week(conn, monday(n))
    closed_through(conn, 4)

    a_core_rehab_niggle(conn, "2026-11-30")

    assert adherence_counts(conn) == [(1, 1)] * 4
    assert adherence(closed_weeks(conn).weeks, datetime.date(2026, 11, 30)).state == "ok"


def test_resolving_a_niggle_keeps_its_rehab_session_in_the_weeks_planned_before() -> None:
    conn = a_squat_program()
    a_core_rehab_niggle(conn, "2026-10-24")
    for n in range(2):
        a_hard_squat_week(conn, monday(n))
    closed_through(conn, 2)

    resolved = '[[niggle]]\nniggle = "n-0001"\ndate = 2026-11-30\nstatus = "resolved"\n'
    record(conn, resolved.encode(), file="r.toml", clock=FixedClock())

    assert adherence_counts(conn) == [(1, 2)] * 2


def test_a_closed_week_carries_each_lifts_figure_and_target_from_the_version_in_force() -> None:
    lift = {"bb_bench_press": {"sets": 6, "counts": ["bb_back_squat"]}, "pull_up": 8}
    conn = a_squat_program(dose={"per_muscle": 10, "lift": lift})
    a_hard_squat_week(conn, monday(0))
    closed_through(conn, 1)

    [week] = closed_weeks(conn).weeks

    assert week.lift_dose == {"bb_bench_press": 4, "pull_up": 0}
    assert week.lift_dose_target == {"bb_bench_press": 6, "pull_up": 8}
