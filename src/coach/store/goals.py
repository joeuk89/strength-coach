from collections.abc import Sequence

from coach.core.program.checks import Goal
from coach.store.connection import Connection


def current(conn: Connection) -> Goal | None:
    found = conn.execute("SELECT id, kind FROM goal WHERE status = 'current'").fetchone()
    if found is None:
        return None
    goal_id, kind = found
    lifts = conn.execute(
        "SELECT exercise_id FROM goal_priority_lift WHERE goal_id = ? ORDER BY rank", (goal_id,)
    )
    return Goal(kind, tuple(exercise for (exercise,) in lifts))


def insert(
    conn: Connection,
    *,
    id_: str,
    kind: str,
    priority_lifts: Sequence[str],
    adopted: str,
    draft_hash: str,
    recorded_at: str,
    why: str = "",
    because: str = "first goal",
) -> None:
    conn.execute(
        "INSERT INTO goal VALUES (?, ?, ?, ?, ?, 'current', NULL, ?, ?)",
        (id_, kind, why, because, adopted, draft_hash, recorded_at),
    )
    conn.executemany(
        "INSERT INTO goal_priority_lift VALUES (?, ?, ?)",
        [(id_, rank, exercise) for rank, exercise in enumerate(priority_lifts, start=1)],
    )
