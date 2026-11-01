import json
import sqlite3

import pytest
from support.clock import FixedClock
from support.goals import STRENGTH, WORKED, opening, with_phase
from support.ledger import a_store

from coach.core.errors import Invalid
from coach.services.goal_adopt import GoalAdoptResult, goal_adopt
from coach.store.catalogue import seed_catalogue
from coach.store.connection import Connection


@pytest.fixture
def conn() -> Connection:
    store = a_store()
    with store:
        seed_catalogue(store)
    return store


def adopt(conn: Connection, text: str) -> GoalAdoptResult:
    return goal_adopt(conn, text.encode("utf-8"), file="g.toml", clock=FixedClock())


def refused(conn: Connection, text: str) -> Invalid:
    with pytest.raises(Invalid) as raised:
        adopt(conn, text)
    return raised.value


def rows(conn: Connection, sql: str) -> list[tuple[object, ...]]:
    return conn.execute(sql).fetchall()


def test_the_worked_draft_writes_the_goal_its_lifts_its_milestones_and_an_open_phase(
    conn: Connection,
) -> None:
    result = adopt(conn, WORKED)

    assert (result.goal_id, result.kind, result.priority_lifts) == (
        "g-0001",
        "hypertrophy",
        ("bb_bench_press", "pull_up"),
    )
    assert result.milestones == ("m-0001", "m-0002", "m-0003")
    assert (result.phase_opened, result.phase_closed, result.superseded) == ("ph-0001", None, None)
    assert rows(conn, "SELECT id, kind, because, adopted, status, superseded_by FROM goal") == [
        ("g-0001", "hypertrophy", "first goal at onboarding", "2026-10-30", "current", None)
    ]
    assert rows(
        conn, "SELECT goal_id, rank, exercise_id FROM goal_priority_lift ORDER BY rank"
    ) == [
        ("g-0001", 1, "bb_bench_press"),
        ("g-0001", 2, "pull_up"),
    ]
    milestones = rows(
        conn, "SELECT id, exercise_id, target_kind, target FROM milestone ORDER BY id"
    )
    assert [(m[0], m[1], m[2], json.loads(str(m[3]))) for m in milestones] == [
        ("m-0001", "bb_deadlift", "bodyweight_multiple", {"value": 2.0}),
        ("m-0002", "bb_bench_press", "bodyweight_multiple", {"value": 1.25}),
        ("m-0003", "pull_up", "load_x_reps", {"load": 0.0, "reps": 5}),
    ]
    assert rows(
        conn,
        "SELECT id, kind, rate_pct_bw_per_week, until_kind, until_value, opened, opened_by, "
        "opened_because, closed FROM phase",
    ) == [
        (
            "ph-0001",
            "maintenance",
            0.0,
            "coachs_call",
            None,
            "2026-10-30",
            "goal:g-0001",
            "recomp at maintenance since 11 Oct 2026",
            None,
        )
    ]


def test_a_first_goal_carries_no_diff(conn: Connection) -> None:
    assert adopt(conn, WORKED).diff is None


def test_a_second_adopt_supersedes_the_first_and_carries_the_diff(conn: Connection) -> None:
    adopt(conn, WORKED)

    result = adopt(conn, STRENGTH)

    assert (result.goal_id, result.superseded) == ("g-0002", "g-0001")
    assert rows(conn, "SELECT id, status, superseded_by FROM goal ORDER BY id") == [
        ("g-0001", "superseded", "g-0002"),
        ("g-0002", "current", None),
    ]
    assert result.diff is not None
    assert result.diff["kind"] == {"from": "hypertrophy", "to": "strength"}
    assert result.diff["priority_lifts"] == {
        "from": ["bb_bench_press", "pull_up"],
        "to": ["bb_bench_press"],
    }


def test_the_store_admits_exactly_one_current_goal(conn: Connection) -> None:
    adopt(conn, WORKED)
    adopt(conn, STRENGTH)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE goal SET status = 'current' WHERE id = 'g-0001'")
    assert rows(conn, "SELECT id FROM goal WHERE status = 'current'") == [("g-0002",)]


def test_the_same_draft_again_writes_nothing_and_returns_the_same_answer(
    conn: Connection,
) -> None:
    adopt(conn, WORKED)
    first = adopt(conn, STRENGTH)

    second = adopt(conn, STRENGTH)

    assert second == first
    assert rows(conn, "SELECT count(*) FROM goal") == [(2,)]


def test_the_worked_draft_again_is_a_no_op_though_its_phase_is_open(conn: Connection) -> None:
    first = adopt(conn, WORKED)

    assert adopt(conn, WORKED) == first
    assert rows(conn, "SELECT count(*) FROM phase") == [(1,)]


def test_an_omitted_rate_is_stored_as_the_kinds_default(conn: Connection) -> None:
    adopt(conn, with_phase(STRENGTH, opening("deficit")))

    assert rows(conn, "SELECT kind, rate_pct_bw_per_week FROM phase") == [("deficit", -0.5)]


def test_opening_a_phase_while_one_is_open_is_phase_already_open(conn: Connection) -> None:
    adopt(conn, WORKED)

    error = refused(conn, with_phase(STRENGTH, opening("surplus")))

    assert error.code == "phase_already_open"
    assert "ph-0001" in error.message
    assert rows(conn, "SELECT count(*) FROM goal") == [(1,)]


def test_closing_the_open_phase_and_opening_one_in_the_same_draft_succeeds(
    conn: Connection,
) -> None:
    adopt(conn, WORKED)

    result = adopt(
        conn, with_phase(STRENGTH, 'close = { because = "recomp done" }\n' + opening("surplus"))
    )

    assert (result.phase_closed, result.phase_opened) == ("ph-0001", "ph-0002")
    assert rows(conn, "SELECT id, closed, closed_by, closed_because FROM phase ORDER BY id") == [
        ("ph-0001", "2026-10-30", "goal:g-0002", "recomp done"),
        ("ph-0002", None, None, None),
    ]


def test_closing_with_no_open_phase_is_invalid_argument(conn: Connection) -> None:
    error = refused(conn, with_phase(STRENGTH, 'close = { because = "done" }'))

    assert error.code == "invalid_argument"


@pytest.mark.parametrize(
    "draft",
    [
        STRENGTH.replace('["bb_bench_press"]', '["bench"]'),
        STRENGTH
        + '\n[[milestones]]\nexercise = "deadlift"\ntarget = { kind = "e1rm", value = 200 }\n',
    ],
)
def test_an_exercise_outside_the_library_is_unknown_exercise(conn: Connection, draft: str) -> None:
    error = refused(conn, draft)

    assert error.code == "unknown_exercise"
    assert rows(conn, "SELECT count(*) FROM goal") == [(0,)]


def test_a_refused_draft_writes_nothing(conn: Connection) -> None:
    adopt(conn, WORKED)

    refused(conn, with_phase(STRENGTH, opening("surplus")))

    assert rows(conn, "SELECT id, status FROM goal") == [("g-0001", "current")]
    assert rows(conn, "SELECT count(*) FROM phase") == [(1,)]
