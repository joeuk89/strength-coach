from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import astuple, dataclass

from coach.core.log import StoredSet, Tombstone, WorkoutVersion
from coach.core.workout_import import Presence
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


_SET_COLUMNS = (
    "position, hevy_template_id, hevy_title, set_type, weight_kg, reps, duration_s, distance_m,"
    " rpe, note"
)
_WORKOUT_COLUMNS = "id, updated_at, source, date, title, routine_id, minutes, notes, raw"


def hevy_presence(conn: Connection) -> dict[str, Presence]:
    versions: defaultdict[str, set[str]] = defaultdict(set)
    for workout_id, updated_at in conn.execute(
        "SELECT id, updated_at FROM workout WHERE source = 'hevy'"
    ):
        versions[workout_id].add(updated_at)
    gone = {workout_id for (workout_id,) in conn.execute(_LATEST_GONE)}
    return {i: Presence(frozenset(v), gone=i in gone) for i, v in versions.items()}


_LATEST_GONE = """
SELECT t.workout_id FROM tombstone t
WHERE t.kind = 'gone'
  AND t.noticed_at = (SELECT max(noticed_at) FROM tombstone WHERE workout_id = t.workout_id)
"""


def append_version(conn: Connection, version: WorkoutVersion, recorded_at: str) -> None:
    conn.execute(
        f"INSERT INTO workout ({_WORKOUT_COLUMNS}, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            version.id,
            version.updated_at,
            version.source,
            version.date,
            version.title,
            version.routine_id,
            version.minutes,
            version.notes,
            version.raw,
            recorded_at,
        ),
    )
    conn.executemany(
        f"INSERT INTO logged_set (workout_id, workout_updated_at, {_SET_COLUMNS})"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                version.id,
                version.updated_at,
                s.position,
                s.hevy_template_id,
                s.hevy_title,
                s.set_type,
                s.weight_kg,
                s.reps,
                s.duration_s,
                s.distance_m,
                s.rpe,
                s.note,
            )
            for s in version.sets
        ],
    )


def append_tombstones(conn: Connection, tombstones: Iterable[Tombstone]) -> None:
    conn.executemany(
        "INSERT INTO tombstone (workout_id, noticed_at, kind, source) VALUES (?,?,?,?)",
        [(t.workout_id, t.noticed_at, t.kind, t.source) for t in tombstones],
    )


def tombstones(conn: Connection, workout_id: str) -> tuple[Tombstone, ...]:
    return tuple(
        Tombstone(*row)
        for row in conn.execute(
            "SELECT workout_id, noticed_at, kind, source FROM tombstone"
            " WHERE workout_id = ? ORDER BY noticed_at",
            (workout_id,),
        )
    )


def current_workouts(conn: Connection) -> tuple[WorkoutVersion, ...]:
    """`workout_current`: the latest version of every workout not gone."""
    return _read(conn, f"SELECT {_WORKOUT_COLUMNS} FROM workout_current ORDER BY date, id", ())


def workout_versions(conn: Connection, workout_id: str) -> tuple[WorkoutVersion, ...]:
    return _read(
        conn,
        f"SELECT {_WORKOUT_COLUMNS} FROM workout WHERE id = ? ORDER BY updated_at",
        (workout_id,),
    )


def counts_by_source(conn: Connection) -> dict[str, int]:
    counts = {"hevy": 0, "manual": 0}
    for source, count in conn.execute(
        "SELECT source, count(*) FROM workout_current GROUP BY source"
    ):
        counts[source] = count
    return counts


def _read(conn: Connection, query: str, params: tuple[str, ...]) -> tuple[WorkoutVersion, ...]:
    rows = conn.execute(query, params).fetchall()
    sets: defaultdict[tuple[str, str], list[StoredSet]] = defaultdict(list)
    for workout_id, updated_at, *columns in conn.execute(
        f"SELECT workout_id, workout_updated_at, {_SET_COLUMNS} FROM logged_set"
        f" WHERE (workout_id, workout_updated_at) IN (SELECT id, updated_at FROM ({query}))"
        " ORDER BY position",
        params,
    ):
        sets[(workout_id, updated_at)].append(StoredSet(*columns))
    return tuple(WorkoutVersion(*row, sets=tuple(sets[(row[0], row[1])])) for row in rows)


def reappeared(conn: Connection) -> tuple[tuple[str, str, str], ...]:
    """(workout id, `back` noticed at, latest version) for each workout whose latest presence
    event is `back` and that no `match` or `void` annotation has cleared (ADR 0011)."""
    return tuple(conn.execute(_REAPPEARED).fetchall())


_REAPPEARED = """
SELECT t.workout_id, t.noticed_at, (SELECT max(updated_at) FROM workout WHERE id = t.workout_id)
FROM tombstone t
WHERE t.kind = 'back'
  AND t.noticed_at = (SELECT max(noticed_at) FROM tombstone WHERE workout_id = t.workout_id)
  AND NOT EXISTS (
    SELECT 1 FROM annotation_current a
    WHERE a.kind IN ('match', 'void') AND a.target = 'workout:' || t.workout_id
  )
ORDER BY t.workout_id
"""


def mapped_template_ids(conn: Connection) -> frozenset[str]:
    rows = conn.execute("SELECT hevy_template_id FROM exercise WHERE hevy_template_id IS NOT NULL")
    return frozenset(template_id for (template_id,) in rows)
