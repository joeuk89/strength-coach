from collections.abc import Sequence
from dataclasses import astuple, dataclass

from coach.store.connection import Connection


@dataclass(frozen=True)
class WorkoutRow:
    id: str
    updated_at: str
    source: str
    date: str
    title: str | None
    routine_id: str | None
    session_id: str | None
    minutes: int | None
    session_rpe: float | None
    notes: str | None
    raw: str | None
    check_in: str | None
    draft_hash: str | None
    recorded_at: str


@dataclass(frozen=True)
class SetRow:
    position: int
    hevy_template_id: str | None
    hevy_title: str | None
    set_type: str
    weight_kg: float | None = None
    reps: int | None = None
    duration_s: int | None = None
    distance_m: float | None = None
    rpe: float | None = None
    note: str | None = None


@dataclass(frozen=True)
class UnmappedSet:
    workout_id: str
    hevy_template_id: str
    hevy_title: str | None


def insert(conn: Connection, workout: WorkoutRow, sets: Sequence[SetRow]) -> None:
    """One workout version and its logged sets."""
    conn.execute(f"INSERT INTO workout VALUES ({', '.join('?' * 14)})", astuple(workout))
    conn.executemany(
        f"INSERT INTO logged_set VALUES ({', '.join('?' * 12)})",
        [(workout.id, workout.updated_at, *astuple(s)) for s in sets],
    )


def session_exists(conn: Connection, session_id: str) -> bool:
    return conn.execute("SELECT 1 FROM session WHERE id = ?", (session_id,)).fetchone() is not None


def unmapped_sets(conn: Connection) -> list[UnmappedSet]:
    """Logged sets of current workouts whose template id no Exercise carries, in workout order."""
    rows = conn.execute(
        "SELECT w.id, s.hevy_template_id, s.hevy_title FROM workout_current w "
        "JOIN logged_set s ON s.workout_id = w.id AND s.workout_updated_at = w.updated_at "
        "WHERE s.hevy_template_id IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM exercise e WHERE e.hevy_template_id = s.hevy_template_id) "
        "ORDER BY w.date, w.id, s.position"
    ).fetchall()
    return [UnmappedSet(*row) for row in rows]
