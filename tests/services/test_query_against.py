import datetime
from typing import Any, cast

from support.check_in_cards import field_of, opened
from support.closed_weeks import a_planned_squat_week, monday
from support.ledger import RECORDED_AT
from support.plans import SQUAT_LINE, SQUAT_TEMPLATE, a_frozen_prescription, a_squat_program
from support.program_drafts import a_line, a_session

from coach.core.units import KG_PER_LB
from coach.services.query import QueryResult, against
from coach.store import workouts
from coach.store.connection import Connection

PLANK_TEMPLATE = "C6C9B8A0"
BENCH = {"type": "working", "count": 3, "range": [6, 8], "rpe": 8}
PLANK = {"type": "working", "count": 2, "duration_s": 30}


def a_lower_program() -> Connection:
    """`lower` on Monday: the back squat and a `hold` plank."""
    plank = a_line(
        "plank", sets=[{"count": 2, "duration_s": 30}], scheme={"name": "hold"}, start_load=None
    )
    return a_squat_program(a_session("lower", SQUAT_LINE, plank))


def a_planned_lower_week(conn: Connection, week: str) -> str:
    """The squat at 4×6–8 @8, then the plank at 2×30 s."""
    plan_id = a_planned_squat_week(conn, week)
    a_frozen_prescription(conn, plan_id, "lower", week, "plank", set_groups=[PLANK], change="held")
    return plan_id


def lower_logged(
    conn: Connection,
    id_: str,
    on: str,
    squat: list[tuple[float, int, float | None]],
    *,
    plank: tuple[int, ...] = (),
    curl: list[tuple[float, int, float | None]] | None = None,
) -> None:
    """Squat and curl sets of (lb, reps, rpe) and plank sets of seconds, logged in Hevy."""
    logged = [(SQUAT_TEMPLATE, lb, reps, None, rpe) for lb, reps, rpe in squat]
    logged += [(PLANK_TEMPLATE, None, None, seconds, None) for seconds in plank]
    logged += [("curl", lb, reps, None, rpe) for lb, reps, rpe in curl or []]
    curl_template = _template(conn, "bb_curl")
    sets = [
        workouts.SetRow(
            position=position,
            hevy_template_id=curl_template if template == "curl" else template,
            hevy_title=None,
            set_type="working",
            weight_kg=None if lb is None else lb * KG_PER_LB,
            reps=reps,
            duration_s=seconds,
            rpe=rpe,
        )
        for position, (template, lb, reps, seconds, rpe) in enumerate(logged)
    ]
    with conn:
        workouts.insert(
            conn,
            workouts.WorkoutRow(
                id=id_,
                updated_at=f"{on}T18:00:00+00:00",
                source="hevy",
                date=on,
                title=None,
                routine_id=None,
                session_id=None,
                minutes=None,
                session_rpe=None,
                notes=None,
                raw="{}",
                check_in=None,
                draft_hash=None,
                recorded_at=RECORDED_AT,
            ),
            sets,
        )


def _template(conn: Connection, exercise: str) -> str:
    (template,) = conn.execute(
        "SELECT hevy_template_id FROM exercise WHERE id = ?", (exercise,)
    ).fetchone()
    return str(template)


def read(
    conn: Connection,
    week: str = monday(0),
    *,
    today: str = "2026-11-08",
    session: str | None = None,
    off: bool = False,
) -> QueryResult:
    return against(
        conn,
        week=datetime.date.fromisoformat(week),
        today=datetime.date.fromisoformat(today),
        session=session,
        off=off,
        units="lb",
        last=None,
    )


def by_exercise(result: QueryResult) -> dict[str, dict[str, Any]]:
    return {str(row["exercise"]): row for row in result.rows}


def test_a_line_logged_at_rpe_6_against_an_authored_8_shows_its_sets_two_under() -> None:
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))
    lower_logged(conn, "h-1", monday(0), [(120, 8, 6)] * 4, plank=(30, 30))

    squat = by_exercise(read(conn))["bb_back_squat"]

    assert squat == {
        "date": "2026-11-02",
        "session": "lower",
        "exercise": "bb_back_squat",
        "workouts": ["h-1"],
        "state": "logged",
        "hold": False,
        "prescription": [{"sets": 4, "reps": [6, 8], "seconds": None, "load": None, "rpe": 8.0}],
        "load": [120.0] * 4,
        "reps": [8] * 4,
        "seconds": [None] * 4,
        "rpe": [6.0] * 4,
        "reps_short": [0] * 4,
        "rpe_off": [-2.0] * 4,
        "sets_missing": 0,
        "rpe_missing": 0,
        "off": True,
    }


def test_a_prescribed_line_with_no_logged_set_reads_not_logged() -> None:
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))
    lower_logged(conn, "h-1", monday(0), [(120, 8, 8)] * 4)

    plank = by_exercise(read(conn))["plank"]

    assert (plank["state"], plank["workouts"], plank["seconds"], plank["off"]) == (
        "not_logged",
        ["h-1"],
        [],
        True,
    )


def test_a_missed_session_reads_every_line_not_logged() -> None:
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))

    rows = read(conn).rows

    assert [(r["exercise"], r["state"], r["workouts"]) for r in rows] == [
        ("bb_back_squat", "not_logged", []),
        ("plank", "not_logged", []),
    ]


def test_an_exercise_logged_in_the_matched_workout_and_not_prescribed_reads_not_prescribed() -> (
    None
):
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))
    lower_logged(conn, "h-1", monday(0), [(120, 8, 8)] * 4, plank=(30, 30), curl=[(50, 12, 9)])

    rows = read(conn).rows

    assert [r["exercise"] for r in rows] == ["bb_back_squat", "plank", "bb_curl"]
    curl = rows[-1]
    assert (curl["state"], curl["prescription"], curl["reps"], curl["rpe_off"]) == (
        "not_prescribed",
        [],
        [12],
        [None],
    )


def test_a_hold_line_with_timed_sets_shows_its_logged_seconds() -> None:
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))
    lower_logged(conn, "h-1", monday(0), [(120, 8, 8)] * 4, plank=(30, 25))

    plank = by_exercise(read(conn))["plank"]

    assert plank["hold"] is True
    assert plank["prescription"] == [
        {"sets": 2, "reps": None, "seconds": 30, "load": None, "rpe": None}
    ]
    assert (plank["seconds"], plank["reps"]) == ([30, 25], [None, None])


def test_a_hold_line_logged_as_prescribed_without_an_rpe_is_not_off() -> None:
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))
    lower_logged(conn, "h-1", monday(0), [(120, 8, 8)] * 4, plank=(30, 30))

    plank = by_exercise(read(conn))["plank"]

    assert (plank["rpe_missing"], plank["off"]) == (2, False)
    assert "plank" not in by_exercise(read(conn, off=True))


def test_the_off_filter_keeps_only_rows_off_the_prescription() -> None:
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))
    lower_logged(conn, "h-1", monday(0), [(120, 8, 8)] * 4, curl=[(50, 12, 9)])

    rows = read(conn, off=True).rows

    assert [(r["exercise"], r["state"]) for r in rows] == [
        ("plank", "not_logged"),
        ("bb_curl", "not_prescribed"),
    ]


def test_the_session_filter_keeps_one_session() -> None:
    conn = a_squat_program(a_session("lower", SQUAT_LINE), a_session("push", a_line()))
    plan_id = a_planned_squat_week(conn, monday(0))
    a_frozen_prescription(
        conn, plan_id, "push", "2026-11-04", "bb_bench_press", set_groups=[BENCH], change="held"
    )

    every = read(conn).rows
    push = read(conn, session="push").rows

    assert [r["session"] for r in every] == ["lower", "push"]
    assert [(r["session"], r["exercise"], r["date"]) for r in push] == [
        ("push", "bb_bench_press", "2026-11-04")
    ]


def test_a_past_week_reads_its_own_plan_after_the_next_plan_is_in_force() -> None:
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))
    lower_logged(conn, "h-1", monday(0), [(120, 8, 6)] * 4, plank=(30, 30))
    a_planned_squat_week(conn, monday(1))

    past = read(conn, "2026-11-06", today="2026-11-10").rows
    current = read(conn, monday(1), today="2026-11-10").rows

    assert [(r["date"], r["exercise"], r["rpe_off"]) for r in past] == [
        ("2026-11-02", "bb_back_squat", [-2.0] * 4),
        ("2026-11-02", "plank", [None, None]),
    ]
    assert [(r["date"], r["exercise"], r["state"]) for r in current] == [
        ("2026-11-09", "bb_back_squat", "not_logged")
    ]


def test_the_week_defaults_to_the_week_holding_today() -> None:
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))
    a_planned_squat_week(conn, monday(1))

    rows = against(
        conn,
        week=None,
        today=datetime.date(2026, 11, 11),
        session=None,
        off=False,
        units="lb",
        last=None,
    ).rows

    assert [r["date"] for r in rows] == ["2026-11-09"]


def test_the_cards_against_counts_equal_the_counts_derived_from_the_read() -> None:
    conn = a_lower_program()
    a_planned_lower_week(conn, monday(0))
    lower_logged(
        conn,
        "h-1",
        monday(0),
        [(120, 8, 8), (120, 5, 8), (120, 8, 6), (120, 8, None)],
        plank=(30, 25),
    )

    rows = [r for r in by_exercise(read(conn)).values() if r["state"] == "logged" and not r["hold"]]
    [lower] = cast(list[dict[str, Any]], field_of(opened(conn), "sessions").facts["core"])

    assert lower["against"] == {
        "reps_missed": sum(1 for r in rows for short in r["reps_short"] if short),
        "effort_off": sum(1 for r in rows for o in r["rpe_off"] if o is not None and abs(o) >= 1.5),
        "rpe_missing": sum(r["rpe_missing"] for r in rows),
    }
    assert lower["against"] == {"reps_missed": 1, "effort_off": 1, "rpe_missing": 1}
