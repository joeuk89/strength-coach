from collections.abc import Sequence
from dataclasses import astuple, dataclass

from coach.store.connection import Connection
from coach.store.rows import Row, select


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


def latest(conn: Connection, *, current_only: bool) -> list[Row]:
    """The latest version of each workout with its sets and the times of its versions;
    with `current_only`, tombstoned workouts are left out."""
    source = (
        "workout_current"
        if current_only
        else (
            "(SELECT w.* FROM workout w WHERE w.updated_at = "
            "(SELECT max(updated_at) FROM workout WHERE id = w.id))"
        )
    )
    rows = select(
        conn,
        "SELECT id, updated_at, source, date, title, routine_id, session_id, minutes, "
        f"session_rpe, notes, check_in, draft_hash, recorded_at FROM {source} ORDER BY id",
    )
    for row in rows:
        row["sets"] = select(
            conn,
            "SELECT position, hevy_template_id, hevy_title, set_type, weight_kg, reps, "
            "duration_s, distance_m, rpe, note FROM logged_set "
            "WHERE workout_id = ? AND workout_updated_at = ? ORDER BY position",
            (row["id"], row["updated_at"]),
        )
        row["versions"] = [
            at
            for (at,) in conn.execute(
                "SELECT updated_at FROM workout WHERE id = ? ORDER BY updated_at", (row["id"],)
            )
        ]
    return rows


def exercises_with_exposure(conn: Connection) -> frozenset[str]:
    """Exercises a current workout logs a working set of, through the set's template id."""
    rows = conn.execute(
        "SELECT DISTINCT e.id FROM workout_current w "
        "JOIN logged_set s ON s.workout_id = w.id AND s.workout_updated_at = w.updated_at "
        "JOIN exercise e ON e.hevy_template_id = s.hevy_template_id "
        "WHERE s.set_type = 'working'"
    )
    return frozenset(id_ for (id_,) in rows)
