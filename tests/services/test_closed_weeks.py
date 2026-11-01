from support.closed_weeks import (
    a_check_in,
    a_hard_squat_week,
    a_planned_squat_week,
    closed_through,
    monday,
)
from support.history import a_logged_workout, an_annotation
from support.plans import a_plan_override, a_squat_program, squat_logged

from coach.services.closed_weeks import closed_weeks
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
