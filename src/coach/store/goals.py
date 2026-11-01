import json
from collections.abc import Sequence
from dataclasses import dataclass

from coach.core.goal import Goal, Milestone, Target
from coach.store.connection import Connection


@dataclass(frozen=True)
class StoredGoal:
    id: str
    goal: Goal
    milestone_ids: tuple[str, ...]
    status: str
    adopted: str


def current_id(conn: Connection) -> str | None:
    found = conn.execute("SELECT id FROM goal WHERE status = 'current'").fetchone()
    return found[0] if found else None


def id_by_draft(conn: Connection, draft_hash: str) -> str | None:
    found = conn.execute("SELECT id FROM goal WHERE draft_hash = ?", (draft_hash,)).fetchone()
    return found[0] if found else None


def previous_of(conn: Connection, goal_id: str) -> str | None:
    """The Goal this one superseded, if any."""
    found = conn.execute("SELECT id FROM goal WHERE superseded_by = ?", (goal_id,)).fetchone()
    return found[0] if found else None


def insert(
    conn: Connection,
    *,
    id_: str,
    goal: Goal,
    milestone_ids: Sequence[str],
    adopted: str,
    draft_hash: str,
    recorded_at: str,
) -> None:
    """A new current Goal, superseding the current one in the caller's transaction
    (schema.md, "Updated in place")."""
    previous = current_id(conn)
    if previous:
        conn.execute("UPDATE goal SET status = 'superseded' WHERE id = ?", (previous,))
    conn.execute(
        "INSERT INTO goal (id, kind, why, because, adopted, status, superseded_by, draft_hash, "
        "recorded_at) VALUES (?, ?, ?, ?, ?, 'current', NULL, ?, ?)",
        (id_, goal.kind, goal.why, goal.because, adopted, draft_hash, recorded_at),
    )
    if previous:
        conn.execute("UPDATE goal SET superseded_by = ? WHERE id = ?", (id_, previous))
    conn.executemany(
        "INSERT INTO goal_priority_lift (goal_id, rank, exercise_id) VALUES (?, ?, ?)",
        [(id_, rank, lift) for rank, lift in enumerate(goal.priority_lifts, start=1)],
    )
    conn.executemany(
        "INSERT INTO milestone (id, goal_id, exercise_id, target_kind, target) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (m_id, id_, m.exercise, m.target.kind, json.dumps(_target_json(m.target)))
            for m_id, m in zip(milestone_ids, goal.milestones, strict=True)
        ],
    )


def get(conn: Connection, goal_id: str) -> StoredGoal | None:
    found = conn.execute(
        "SELECT kind, because, why, status, adopted FROM goal WHERE id = ?", (goal_id,)
    ).fetchone()
    if found is None:
        return None
    kind, because, why, status, adopted = found
    lifts = tuple(
        lift
        for (lift,) in conn.execute(
            "SELECT exercise_id FROM goal_priority_lift WHERE goal_id = ? ORDER BY rank",
            (goal_id,),
        )
    )
    milestones = conn.execute(
        "SELECT id, exercise_id, target_kind, target FROM milestone WHERE goal_id = ? ORDER BY id",
        (goal_id,),
    ).fetchall()
    return StoredGoal(
        id=goal_id,
        goal=Goal(
            kind=kind,
            because=because,
            priority_lifts=lifts,
            why=why,
            milestones=tuple(Milestone(e, _target(k, t)) for _, e, k, t in milestones),
        ),
        milestone_ids=tuple(m[0] for m in milestones),
        status=status,
        adopted=adopted,
    )


def _target_json(target: Target) -> dict[str, object]:
    return {k: v for k, v in target.describe().items() if k != "kind"}


def _target(kind: str, text: str) -> Target:
    values = json.loads(text)
    if kind == "load_x_reps":
        return Target(kind, load=float(values["load"]), reps=int(values["reps"]))
    return Target(kind, value=float(values["value"]))
