"""The Routine map: which Hevy routine carries each session (schema.md, "Hevy")."""

from coach.store.connection import Connection


def mapped(conn: Connection) -> dict[str, str]:
    """Each session with a routine that is not retired, to that routine's id."""
    return dict(
        conn.execute("SELECT session_id, routine_id FROM routine_map WHERE status != 'retired'")
    )
