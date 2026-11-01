"""Scenario builders for the ledger and the log. Each writes only through `store` functions."""

import datetime
from typing import Any

from coach.store import exercises, readings, workouts
from coach.store.connection import Connection, open_store

RECORDED_AT = "2026-10-30T12:00:00+00:00"


def a_store() -> Connection:
    return open_store(":memory:")


def an_exercise(conn: Connection, id_: str, **columns: Any) -> str:
    row: dict[str, Any] = {
        "id": id_,
        "name": id_.replace("_", " "),
        "load_mode": "total",
        "equipment_kind": "barbell",
        "pattern": "push",
        "muscles": {"primary": ["chest"], "secondary": []},
        "hevy_title": None,
        "hevy_exercise_type": None,
        "hevy_equipment": None,
        "hevy_muscle_group": None,
        "hevy_template_id": None,
        "source": "catalogue",
    }
    row.update(columns)
    with conn:
        exercises.insert(conn, row)
    return id_


def a_weigh_in(conn: Connection, date: str, kg: float, *, id_: str, source: str = "manual") -> str:
    with conn:
        readings.insert(
            conn,
            "weigh_in",
            {
                "id": id_,
                "date": date,
                "kg": kg,
                "source": source,
                "withdraws": None,
                "check_in": None,
                "draft_hash": None,
                "recorded_at": RECORDED_AT,
            },
        )
    return id_


def a_hevy_workout(
    conn: Connection,
    id_: str,
    *,
    date: datetime.date = datetime.date(2026, 10, 20),
    templates: tuple[tuple[str, str], ...] = (),
    updated_at: str = "2026-10-20T10:00:00+00:00",
) -> str:
    """A Hevy workout version with one working set per (template id, title)."""
    with conn:
        workouts.insert(
            conn,
            workouts.WorkoutRow(
                id=id_,
                updated_at=updated_at,
                source="hevy",
                date=date.isoformat(),
                title="Push",
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
            [
                workouts.SetRow(
                    position=i,
                    hevy_template_id=template,
                    hevy_title=title,
                    set_type="working",
                    weight_kg=60.0,
                    reps=5,
                )
                for i, (template, title) in enumerate(templates)
            ],
        )
    return id_
