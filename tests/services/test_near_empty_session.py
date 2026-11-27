"""A matched session with one set of twenty logged, on the check-in card and in the closed week
(docs/spec/week.md, "The session gate"; docs/spec/check-in.md, "Views")."""

from typing import Any, cast

from support.check_in_cards import a_two_session_program, field_of, opened
from support.closed_weeks import closed_through, monday
from support.history import a_logged_workout, an_annotation
from support.plans import a_frozen_prescription, an_approved_plan, squat_logged

from coach.core.check_in_card import Ask, Card
from coach.services.closed_weeks import closed_weeks
from coach.store import exercises
from coach.store.connection import Connection

LOWER = f"planned_session:{monday(0)}/lower"
PUSH = "planned_session:2026-11-04/push"


def a_week_with_twenty_squat_sets(squat_sets: int, *, push_sets: int = 0) -> Connection:
    """`lower` prescribes 20 working squat sets on Monday 2 Nov and logs `squat_sets` of them;
    `push` prescribes 3 bench sets on the Wednesday and logs `push_sets`."""
    conn = a_two_session_program()
    plan_id = an_approved_plan(conn, monday(0))
    for session, day, exercise, count in (
        ("lower", monday(0), "bb_back_squat", 20),
        ("push", "2026-11-04", "bb_bench_press", 3),
    ):
        a_frozen_prescription(
            conn,
            plan_id,
            session,
            day,
            exercise,
            set_groups=[{"type": "working", "count": count, "range": [5, 8], "rpe": 8}],
            change="held",
        )
    squat_logged(conn, "h-1", monday(0), *[(120, 5, 10.0)] * squat_sets)
    if push_sets:
        with conn:
            exercises.update(conn, "bb_bench_press", {"hevy_template_id": "BP-0001"})
        a_logged_workout(conn, "h-2", "2026-11-04", ("BP-0001", ((60.0, 6, 8.0),) * push_sets))
    return conn


def core_rows(card: Card) -> dict[str, dict[str, Any]]:
    rows = cast(list[dict[str, Any]], field_of(card, "sessions").facts["core"])
    return {row["session"]: row for row in rows}


def week_line(card: Card) -> dict[str, Any]:
    [week] = cast(list[dict[str, Any]], field_of(card, "week_kind").facts["weeks"])
    return week


def test_one_of_twenty_sets_shows_both_counts_raises_the_warning_and_has_no_session_rpe() -> None:
    card = opened(a_week_with_twenty_squat_sets(1))

    lower = core_rows(card)[LOWER]
    [warning] = [w for w in card.warnings if w.code == "session_near_empty"]

    assert lower["state"] == "matched"
    assert (lower["sets_logged"], lower["sets_prescribed"], lower["gate_passed"]) == (1, 20, False)
    assert lower["session_rpe"] is None
    assert warning.params == {"date": monday(0), "sets_logged": 1, "sets_prescribed": 20}
    assert Ask("session_rpe", LOWER) not in field_of(card, "sessions").asks


def test_every_core_row_shows_its_counts_and_gate_result() -> None:
    card = opened(a_week_with_twenty_squat_sets(14))

    push = core_rows(card)[PUSH]
    lower = core_rows(card)[LOWER]

    assert (lower["sets_logged"], lower["sets_prescribed"], lower["gate_passed"]) == (14, 20, True)
    assert (push["state"], push["sets_logged"], push["sets_prescribed"]) == ("missed", 0, 3)
    assert push["gate_passed"] is False


def test_a_session_at_the_floor_raises_no_warning_and_keeps_its_session_rpe() -> None:
    card = opened(a_week_with_twenty_squat_sets(7))

    assert "session_near_empty" not in [w.code for w in card.warnings]
    assert core_rows(card)[LOWER]["session_rpe"] == 10.0


def test_with_no_answer_the_near_empty_session_stays_trained() -> None:
    card = opened(a_week_with_twenty_squat_sets(1))

    assert week_line(card)["trained"] == "1/2"
    assert week_line(card)["kind"] == "partial"


def test_a_miss_tag_on_it_reads_one_fewer_trained_session_and_the_week_kind_follows() -> None:
    conn = a_week_with_twenty_squat_sets(1)
    an_annotation(conn, "a-1", "miss_tag", LOWER)

    card = opened(conn)

    assert week_line(card)["trained"] == "0/2"
    assert week_line(card)["kind"] == "missed"
    assert core_rows(card)[LOWER]["state"] == "missed"
    assert "session_near_empty" not in [w.code for w in card.warnings]
    assert Ask("miss_tag", LOWER) not in field_of(card, "sessions").asks


def test_a_miss_tagged_session_leaves_the_adherence_numerator() -> None:
    conn = a_week_with_twenty_squat_sets(1, push_sets=3)
    an_annotation(conn, "a-1", "miss_tag", LOWER)
    closed_through(conn, 1)

    [week] = closed_weeks(conn).weeks

    assert (week.adherence_trained, week.adherence_planned) == (1, 2)
