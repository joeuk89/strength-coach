import datetime

from support.plans import a_frozen_prescription, a_squat_program, an_approved_plan

from coach.services.query import QueryResult, flags, lines
from coach.store.connection import Connection

TODAY = datetime.date(2026, 10, 30)
STALL = {
    "key": "stall_streak@line:2026-10-26/lower/bb_back_squat",
    "code": "stall_streak",
    "severity": "warning",
    "scope": {
        "kind": "line",
        "week": "2026-10-26",
        "session": "lower",
        "exercise": "bb_back_squat",
    },
    "params": {"streak": 3},
    "params_hash": "sha256:s",
    "rn": None,
    "message": "the squat has stalled for 3 exposures",
    "left": None,
}
WORKING = {"type": "working", "count": 4, "load": 120.0, "load_kg": 54.43, "range": [6, 8]}


def a_plan_in_force() -> Connection:
    conn = a_squat_program()
    plan_id = an_approved_plan(conn, "2026-10-26")
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        "2026-10-26",
        "bb_back_squat",
        set_groups=[WORKING],
        change="held",
        flags=[STALL],
    )
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        "2026-10-26",
        "bb_bench_press",
        set_groups=[{**WORKING, "load": 100.0}],
        change="4×6–8: 95 → 100",
    )
    return conn


def flags_of(
    conn: Connection,
    *,
    severity: str | None = None,
    scope: str | None = None,
    summary: bool = False,
) -> QueryResult:
    return flags(
        conn,
        draft=None,
        today=TODAY,
        code=None,
        severity=severity,
        scope=scope,
        summary=summary,
        last=10,
    )


def lines_of(
    conn: Connection, *, exercises: tuple[str, ...] = (), changed: bool = False
) -> QueryResult:
    return lines(
        conn,
        draft=None,
        today=TODAY,
        units="lb",
        exercises=exercises,
        session=None,
        date=None,
        changed=changed,
        last=10,
    )


def test_query_flags_reads_the_flags_frozen_on_the_plan_in_force() -> None:
    conn = a_plan_in_force()

    assert [row["key"] for row in flags_of(conn).rows] == [STALL["key"]]
    assert flags_of(conn, summary=True).rows == [
        {"code": "stall_streak", "severity": "warning", "count": 1}
    ]
    assert flags_of(conn, severity="violation").rows == []
    assert flags_of(conn, scope="week").rows == []


def test_query_lines_reads_the_plan_in_force_and_filters_the_changed_lines() -> None:
    conn = a_plan_in_force()

    every = lines_of(conn).rows
    changed = lines_of(conn, changed=True).rows

    assert [(r["exercise"], r["prescription"], r["flags"]) for r in every] == [
        ("bb_back_squat", "4×6–8 at 120 lb", [STALL["key"]]),
        ("bb_bench_press", "4×6–8 at 100 lb", []),
    ]
    assert [r["exercise"] for r in changed] == ["bb_bench_press"]
    assert lines_of(conn, exercises=("bb_back_squat",)).count == 1


def test_a_plan_for_another_week_is_not_in_force() -> None:
    conn = a_squat_program()
    an_approved_plan(conn, "2026-11-02")

    assert flags_of(conn).rows == []
    assert lines_of(conn).rows == []
