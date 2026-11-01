from collections.abc import Mapping

from coach.store.connection import Connection
from coach.store.rows import Row, insert, select


def insert_follow_up(conn: Connection, row: Mapping[str, object]) -> None:
    insert(conn, "follow_up", row)


def insert_event(conn: Connection, row: Mapping[str, object]) -> None:
    insert(conn, "follow_up_event", row)


def exists(conn: Connection, follow_up_id: str) -> bool:
    found = conn.execute("SELECT 1 FROM follow_up WHERE id = ?", (follow_up_id,)).fetchone()
    return found is not None


def last_due(conn: Connection, follow_up_id: str) -> str | None:
    """The due date the latest event carrying one set."""
    found = conn.execute(
        "SELECT due FROM follow_up_event WHERE follow_up_id = ? AND due IS NOT NULL "
        "ORDER BY date DESC, id DESC LIMIT 1",
        (follow_up_id,),
    ).fetchone()
    return found[0] if found else None


def every(conn: Connection) -> list[Row]:
    """Every follow-up with its latest event's kind and due date and its events oldest first."""
    rows = select(
        conn,
        "SELECT f.id, f.raised, f.text, f.about, c.kind, c.due, f.check_in, f.draft_hash, "
        "f.recorded_at FROM follow_up f JOIN follow_up_current c ON c.follow_up_id = f.id "
        "ORDER BY f.id",
    )
    for row in rows:
        row["events"] = select(
            conn,
            "SELECT id, date, kind, due, text, check_in, draft_hash, recorded_at "
            "FROM follow_up_event WHERE follow_up_id = ? ORDER BY date, id",
            (row["id"],),
        )
    return rows
