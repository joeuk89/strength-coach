"""The Routine map: which Hevy routine carries each session (schema.md, "Hevy")."""

from coach.core.hevy_actions import MapStatus
from coach.store.connection import Connection


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
