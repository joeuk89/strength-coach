import datetime
from typing import Any

from support.plans import a_frozen_prescription, a_squat_program, an_approved_plan

from coach.services.query import QueryResult, flags, lines
from coach.store.connection import Connection

TODAY = datetime.date(2026, 10, 30)
LOWER_SQUAT = {
    "kind": "line",
    "week": "2026-10-26",
    "session": "lower",
    "exercise": "bb_back_squat",
}
STALL = {
    "key": "stall_streak@line:2026-10-26/lower/bb_back_squat",
    "code": "stall_streak",
    "severity": "warning",
    "scope": LOWER_SQUAT,
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
    code: str | None = None,
    summary: bool = False,
    full: bool = False,
) -> QueryResult:
    return flags(
        conn,
        draft=None,
        today=TODAY,
        code=code,
        severity=severity,
        scope=scope,
        summary=summary,
        full=full,
        last=None if full else 10,
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

    assert [row["key"] for row in flags_of(conn, severity="warning").rows] == [STALL["key"]]
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


def test_query_lines_lists_same_day_sessions_in_the_order_the_plan_froze_them() -> None:
    conn = a_squat_program()
    plan_id = an_approved_plan(conn, "2026-10-26")
    for session, exercise in (
        ("lower", "bb_bench_press"),
        ("lower", "bb_back_squat"),
        ("arms", "db_curl"),
    ):
        a_frozen_prescription(
            conn, plan_id, session, "2026-10-26", exercise, set_groups=[WORKING], change="held"
        )

    assert [(r["session"], r["exercise"]) for r in lines_of(conn).rows] == [
        ("lower", "bb_bench_press"),
        ("lower", "bb_back_squat"),
        ("arms", "db_curl"),
    ]


def test_a_plan_for_another_week_is_not_in_force() -> None:
    conn = a_squat_program()
    an_approved_plan(conn, "2026-11-02")

    assert flags_of(conn).rows == []
    assert lines_of(conn).rows == []


CODES = ("stall_streak", "rep_range_missed", "dose_under_target")
EXERCISES = (
    "bb_back_squat",
    "bb_bench_press",
    "bb_deadlift",
    "bb_overhead_press",
    "bb_bent_over_row",
    "bb_romanian_deadlift",
    "bb_front_squat",
    "bb_hip_thrust",
    "ez_bar_curl",
)


def a_flag(code: str, exercise: str) -> dict[str, object]:
    return {
        **STALL,
        "key": f"{code}@line:2026-10-26/lower/{exercise}",
        "code": code,
        "scope": {**LOWER_SQUAT, "exercise": exercise},
        "params_hash": f"sha256:{code}/{exercise}",
        "message": f"{code} on {exercise}",
    }


def a_plan_with_27_flags() -> Connection:
    """Nine lines of the plan in force, each carrying a flag of each of three codes."""
    conn = a_squat_program()
    plan_id = an_approved_plan(conn, "2026-10-26")
    for exercise in EXERCISES:
        a_frozen_prescription(
            conn,
            plan_id,
            "lower",
            "2026-10-26",
            exercise,
            set_groups=[WORKING],
            change="held",
            flags=[a_flag(code, exercise) for code in CODES],
        )
    return conn


def test_query_flags_with_no_filter_returns_one_row_per_code_with_every_key() -> None:
    result = flags_of(a_plan_with_27_flags())
    rows: Any = result.rows

    assert (result.count, result.truncated) == (3, False)
    assert [(row["code"], row["severity"], row["count"]) for row in result.rows] == [
        ("stall_streak", "warning", 9),
        ("rep_range_missed", "warning", 9),
        ("dose_under_target", "warning", 9),
    ]
    assert rows[1]["keys"][:2] == [
        {
            "key": "rep_range_missed@line:2026-10-26/lower/bb_back_squat",
            "params_hash": "sha256:rep_range_missed/bb_back_squat",
        },
        {
            "key": "rep_range_missed@line:2026-10-26/lower/bb_bench_press",
            "params_hash": "sha256:rep_range_missed/bb_bench_press",
        },
    ]
    assert sum(len(row["keys"]) for row in rows) == 27


def test_query_flags_by_code_returns_the_flat_rows_with_their_messages() -> None:
    result = flags_of(a_plan_with_27_flags(), code="dose_under_target")

    assert (result.count, result.truncated) == (9, False)
    assert result.rows[0] == {
        "key": "dose_under_target@line:2026-10-26/lower/bb_back_squat",
        "code": "dose_under_target",
        "severity": "warning",
        "message": "dose_under_target on bb_back_squat",
        "left": None,
    }


def test_query_flags_full_with_no_filter_returns_every_flat_row() -> None:
    result = flags_of(a_plan_with_27_flags(), full=True)

    assert (result.count, result.truncated, len(result.rows)) == (27, False, 27)
    assert {"key", "message"} <= set(result.rows[0])


def test_query_flags_summary_still_counts_by_code_and_severity() -> None:
    assert flags_of(a_plan_with_27_flags(), summary=True).rows == [
        {"code": "dose_under_target", "severity": "warning", "count": 9},
        {"code": "rep_range_missed", "severity": "warning", "count": 9},
        {"code": "stall_streak", "severity": "warning", "count": 9},
    ]
