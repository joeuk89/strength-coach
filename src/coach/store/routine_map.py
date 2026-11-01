"""The Routine map: which Hevy routine carries each session (schema.md, "Hevy"). A state table:
`plan apply` writes a row after each write, import flips one to `missing`."""

from dataclasses import dataclass

from coach.core.hevy_actions import MappedRoutine, MapStatus
from coach.store.connection import Connection
from coach.store.rows import Row, select


def mapped(conn: Connection) -> dict[str, str]:
    """Each session with a routine that is not retired, to that routine's id."""
    return dict(
        conn.execute("SELECT session_id, routine_id FROM routine_map WHERE status != 'retired'")
    )


def every(conn: Connection) -> list[tuple[str, str, MapStatus]]:
    """Every map row as (session id, routine id, status)."""
    return conn.execute(
        "SELECT session_id, routine_id, status FROM routine_map ORDER BY session_id"
    ).fetchall()


def rows(conn: Connection) -> tuple[MappedRoutine, ...]:
    return tuple(
        MappedRoutine(*row)
        for row in conn.execute(
            "SELECT session_id, routine_id, status, written_at FROM routine_map ORDER BY session_id"
        )
    )


def record(
    conn: Connection,
    session_id: str,
    routine_id: str,
    status: MapStatus,
    *,
    plan_id: str,
    at: str,
    verified: bool,
) -> None:
    conn.execute(
        "INSERT INTO routine_map (session_id, routine_id, status, last_verified, plan_id,"
        " written_at) VALUES (?,?,?,?,?,?) ON CONFLICT (session_id) DO UPDATE SET"
        " routine_id = excluded.routine_id, status = excluded.status,"
        " last_verified = COALESCE(excluded.last_verified, routine_map.last_verified),"
        " plan_id = excluded.plan_id, written_at = excluded.written_at",
        (session_id, routine_id, status, at if verified else None, plan_id, at),
    )


def flip_missing(conn: Connection, returned: set[str]) -> int:
    """Flip every live row whose routine Hevy no longer returns; the mirror row stays."""
    held = conn.execute(
        "SELECT session_id, routine_id FROM routine_map WHERE status IN ('active','unverified')"
    ).fetchall()
    gone = [session for session, routine in held if routine not in returned]
    conn.executemany(
        "UPDATE routine_map SET status = 'missing' WHERE session_id = ?",
        [(session,) for session in gone],
    )
    return len(gone)


def joined(conn: Connection) -> list[Row]:
    """The map joined to the folder mirror: session, routine, folder, status, last verified."""
    return select(
        conn,
        "SELECT m.session_id AS session, m.routine_id AS routine, f.title AS folder,"
        " m.status, m.last_verified FROM routine_map m"
        " LEFT JOIN routine r ON r.hevy_id = m.routine_id"
        " LEFT JOIN folder f ON f.hevy_id = r.folder_id ORDER BY m.session_id",
    )


@dataclass(frozen=True)
class WrittenRow:
    session_id: str
    routine_id: str
    plan_id: str


def written(conn: Connection) -> tuple[WrittenRow, ...]:
    """The live rows a WeekPlan wrote: what drift is judged against."""
    return tuple(
        WrittenRow(*row)
        for row in conn.execute(
            "SELECT session_id, routine_id, plan_id FROM routine_map"
            " WHERE status IN ('active','unverified') AND plan_id IS NOT NULL ORDER BY session_id"
        )
    )


@dataclass(frozen=True)
class LiveRow:
    session_id: str
    status: MapStatus
    plan_id: str | None


def live(conn: Connection) -> tuple[LiveRow, ...]:
    """Every `active` or `unverified` row with the plan that last wrote it."""
    return tuple(
        LiveRow(*row)
        for row in conn.execute(
            "SELECT session_id, status, plan_id FROM routine_map"
            " WHERE status IN ('active','unverified') ORDER BY session_id"
        )
    )
