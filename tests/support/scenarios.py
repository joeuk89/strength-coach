"""Scenario builders: each writes one piece of history through `store` functions only."""

import json
from importlib.resources import files
from typing import Any

from coach.store import exercises, rows
from coach.store.connection import Connection
from coach.store.jsonl import load_rows

RECORDED_AT = "2026-11-01T09:00:00Z"


def a_session(conn: Connection, session_id: str, *, introduced_in: str = "pv-1") -> None:
    rows.insert(conn, "session", {"id": session_id, "introduced_in": introduced_in})


def a_catalogue_without(conn: Connection, *missing: str) -> None:
    """The store an older engine seeded, whose catalogue lacked the `missing` ids."""
    catalogue = files("coach.store").joinpath("catalogue.jsonl").read_text(encoding="utf-8")
    lines = [line for line in catalogue.splitlines() if line.strip()]
    kept = [line for line in lines if json.loads(line)["id"] not in missing]
    assert len(lines) - len(kept) == len(set(missing)), "every missing id is a catalogue id"
    load_rows(conn, "exercise", "\n".join(kept))


def an_exercise(conn: Connection, exercise_id: str, **columns: Any) -> None:
    row: dict[str, Any] = {
        "id": exercise_id,
        "name": exercise_id.replace("_", " "),
        "load_mode": "total",
        "equipment_kind": "barbell",
        "pattern": "horizontal_push",
        "muscles": json.dumps({"primary": ["chest"], "secondary": []}, separators=(",", ":")),
        "source": "record",
    }
    rows.insert(conn, "exercise", row | columns)


def a_workout(
    conn: Connection,
    workout_id: str,
    updated_at: str,
    *,
    sets: int = 3,
    template_id: str = "79D0BB3A",
    weight_kg: float = 80.0,
    **columns: Any,
) -> None:
    row: dict[str, Any] = {
        "id": workout_id,
        "updated_at": updated_at,
        "source": "manual" if workout_id.startswith("w-") else "hevy",
        "date": updated_at[:10],
        "recorded_at": RECORDED_AT,
    }
    rows.insert(conn, "workout", row | columns)
    for position in range(1, sets + 1):
        rows.insert(
            conn,
            "logged_set",
            {
                "workout_id": workout_id,
                "workout_updated_at": updated_at,
                "position": position,
                "hevy_template_id": template_id,
                "set_type": "working",
                "weight_kg": weight_kg,
                "reps": 8,
                "rpe": 7.5,
            },
        )


def a_check_in(conn: Connection, check_in_id: str) -> None:
    date = check_in_id.removeprefix("ci-")[:10]
    rows.insert(
        conn,
        "check_in",
        {
            "id": check_in_id,
            "date": date,
            "tier": "light",
            "window_start": date,
            "window_end": date,
            "read": "Training went well.",
            "status": "current",
            "draft_hash": f"h-{check_in_id}",
            "recorded_at": RECORDED_AT,
        },
    )


def a_superseded_check_in(conn: Connection, date: str) -> None:
    """A check-in and the later one for the same date that supersedes it."""
    a_check_in(conn, f"ci-{date}")
    a_check_in(conn, f"ci-{date}-2")
    rows.supersede(conn, "check_in", f"ci-{date}", f"ci-{date}-2")


def a_weigh_in(
    conn: Connection, weigh_in_id: str, date: str, kg: float, *, check_in: str | None = None
) -> None:
    rows.insert(
        conn,
        "weigh_in",
        {
            "id": weigh_in_id,
            "date": date,
            "kg": kg,
            "source": "check_in" if check_in else "manual",
            "check_in": check_in,
            "recorded_at": RECORDED_AT,
        },
    )


def a_history(conn: Connection) -> None:
    """A small store touching foreign keys, a forward pointer, nulls, reals and unicode."""
    an_exercise(conn, "bb_bench_press", name="Bänkpress", hevy_template_id="79D0BB3A")
    an_exercise(conn, "bb_back_squat", pattern="squat", hevy_template_id="D04AC939")
    a_logged_history(conn)


def a_history_on_the_catalogue(conn: Connection) -> None:
    """`a_history` in a store `init` seeded: the athlete edits two catalogue rows."""
    exercises.update(conn, "bb_bench_press", {"name": "Bänkpress", "hevy_template_id": "79D0BB3A"})
    exercises.update(conn, "bb_back_squat", {"hevy_template_id": "D04AC939"})
    a_logged_history(conn)


def a_logged_history(conn: Connection) -> None:
    a_session(conn, "upper_a")
    a_session(conn, "lower_a")
    a_workout(conn, "b7e2c1a0-5d3f-4e8a-9c21-7f0a4d6b9e13", "2026-10-27T18:00:00Z", sets=11)
    a_workout(conn, "w-0001", "2026-10-29T07:30:00Z", template_id="D04AC939", weight_kg=102.5)
    a_superseded_check_in(conn, "2026-11-01")
    a_weigh_in(conn, "wi-0001", "2026-11-01", 81.35, check_in="ci-2026-11-01-2")
    a_weigh_in(conn, "wi-0002", "2026-10-25", 81.9)
