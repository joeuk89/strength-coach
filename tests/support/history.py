"""Scenario builders for logged history: workouts with sets, annotations and plans. Each writes
only through `store` functions."""

import datetime
from pathlib import Path
from typing import Any

from coach.store import annotations, readings, workouts
from coach.store.connection import Connection, open_store
from support.instances import an_instance
from support.ledger import RECORDED_AT, an_exercise

type Logged = tuple[float | None, int, float | None]


def a_logged_workout(
    conn: Connection,
    id_: str,
    on: str,
    *exercises: tuple[str, tuple[Logged, ...]],
    session_id: str | None = None,
) -> str:
    """A workout version: per (template id, sets), working sets of (kg, reps, rpe). An id
    starting `w-` is a manual workout."""
    manual = id_.startswith("w-")
    logged_sets = [(template, set_) for template, logged in exercises for set_ in logged]
    sets = [
        workouts.SetRow(
            position=position,
            hevy_template_id=template,
            hevy_title=None,
            set_type="working",
            weight_kg=kg,
            reps=reps,
            rpe=rpe,
        )
        for position, (template, (kg, reps, rpe)) in enumerate(logged_sets)
    ]
    with conn:
        workouts.insert(
            conn,
            workouts.WorkoutRow(
                id=id_,
                updated_at=f"{on}T18:00:00+00:00",
                source="manual" if manual else "hevy",
                date=on,
                title=None,
                routine_id=None,
                session_id=session_id,
                minutes=None,
                session_rpe=None,
                notes=None,
                raw=None if manual else "{}",
                check_in=None,
                draft_hash="h" if manual else None,
                recorded_at=RECORDED_AT,
            ),
            sets,
        )
    return id_


def an_annotation(
    conn: Connection,
    id_: str,
    kind: str,
    target: str,
    *,
    withdraws: str | None = None,
    **params: Any,
) -> str:
    with conn:
        annotations.insert_annotation(
            conn,
            {
                "id": id_,
                "kind": kind,
                "target": target,
                "params": params or None,
                "because": "coach_judgement",
                "text": None,
                "withdraws": withdraws,
                "check_in": None,
                "draft_hash": "h",
                "recorded_at": RECORDED_AT,
            },
        )
    return id_


def a_status_span(conn: Connection, id_: str, kind: str, from_date: str, to_date: str) -> str:
    with conn:
        readings.insert(
            conn,
            "status_span",
            {
                "id": id_,
                "kind": kind,
                "from_date": from_date,
                "to_date": to_date,
                "draft_hash": "h",
                "recorded_at": RECORDED_AT,
            },
        )
    return id_


def an_instance_with_eight_weeks(root: Path, *, pin: str) -> Path:
    """An instance whose store holds eight weekly workouts of bench and squat from 7 Sep 2026,
    bench rising 2.5 a week from 100."""
    an_instance(root, pin=pin)
    (root / ".coach").mkdir()
    conn = open_store(root / ".coach" / "coach.db")
    an_exercise(conn, "bb_bench_press", hevy_template_id="79D0BB3A")
    an_exercise(conn, "bb_back_squat", hevy_template_id="D04AC939", pattern="squat")
    for week in range(8):
        on = (datetime.date(2026, 9, 7) + datetime.timedelta(weeks=week)).isoformat()
        sets = ((100 + 2.5 * week, 5, 8), (100 + 2.5 * week, 5, 8.5), (95, 8, 8))
        a_logged_workout(conn, f"h-{week}", on, ("79D0BB3A", sets), ("D04AC939", ((140, 5, 8),)))
    conn.close()
    return root
