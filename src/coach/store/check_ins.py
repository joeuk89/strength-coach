import datetime
from collections.abc import Mapping
from dataclasses import dataclass

from coach.core.check_in import Window
from coach.store import rows
from coach.store.connection import Connection

COLUMNS = "id, date, tier, window_start, window_end, status, readiness"


@dataclass(frozen=True)
class StoredCheckIn:
    id: str
    date: datetime.date
    tier: str
    window: Window
    status: str
    readiness: str | None = None


def insert(conn: Connection, row: Mapping[str, object]) -> None:
    rows.insert(conn, "check_in", row)


def next_id(conn: Connection, date: datetime.date) -> str:
    """`ci-<date>`, and `-2`, `-3` for each row that supersedes it (schema.md, "Ids")."""
    day = date.isoformat()
    (count,) = conn.execute("SELECT count(*) FROM check_in WHERE date = ?", (day,)).fetchone()
    return f"ci-{day}" if count == 0 else f"ci-{day}-{count + 1}"


def by_draft(conn: Connection, draft_hash: str) -> StoredCheckIn | None:
    return _one(conn, f"SELECT {COLUMNS} FROM check_in WHERE draft_hash = ?", (draft_hash,))


def current_on(conn: Connection, date: datetime.date) -> StoredCheckIn | None:
    return _one(
        conn,
        f"SELECT {COLUMNS} FROM check_in WHERE status = 'current' AND date = ?",
        (date.isoformat(),),
    )


def newest_current(
    conn: Connection, *, before: datetime.date | None = None
) -> StoredCheckIn | None:
    """The newest `current` row, or the newest dated strictly before `before`."""
    return _one(
        conn,
        f"SELECT {COLUMNS} FROM check_in WHERE status = 'current' AND (? IS NULL OR date < ?) "
        "ORDER BY date DESC LIMIT 1",
        (before.isoformat(),) * 2 if before else (None, None),
    )


def last_deep(conn: Connection) -> datetime.date | None:
    (found,) = conn.execute(
        "SELECT max(date) FROM check_in WHERE status = 'current' AND tier = 'deep'"
    ).fetchone()
    return datetime.date.fromisoformat(found) if found else None


def supersede(conn: Connection, old_id: str, new_id: str) -> None:
    rows.supersede(conn, "check_in", old_id, new_id)


def superseded_by(conn: Connection, check_in: str) -> str | None:
    found = conn.execute("SELECT id FROM check_in WHERE superseded_by = ?", (check_in,)).fetchone()
    return found[0] if found else None


def _one(conn: Connection, sql: str, params: tuple[object, ...]) -> StoredCheckIn | None:
    found = conn.execute(sql, params).fetchone()
    if found is None:
        return None
    return _stored(found)


def _stored(found: tuple[str, ...]) -> StoredCheckIn:
    id_, date, tier, start, end, status, readiness = found
    window = Window(datetime.date.fromisoformat(start), datetime.date.fromisoformat(end))
    return StoredCheckIn(id_, datetime.date.fromisoformat(date), tier, window, status, readiness)


def current(conn: Connection) -> list[StoredCheckIn]:
    """Every `current` row, oldest first."""
    found = conn.execute(f"SELECT {COLUMNS} FROM check_in WHERE status = 'current' ORDER BY date")
    return [_stored(row) for row in found]


def current_windows(conn: Connection) -> list[tuple[datetime.date, datetime.date]]:
    """Each `current` Check-in's window, first and last day, oldest first."""
    found = conn.execute(
        "SELECT window_start, window_end FROM check_in WHERE status = 'current' "
        "ORDER BY window_start"
    )
    return [
        (datetime.date.fromisoformat(start), datetime.date.fromisoformat(end))
        for start, end in found
    ]


def read_of(conn: Connection, check_in: str) -> str:
    (read,) = conn.execute("SELECT read FROM check_in WHERE id = ?", (check_in,)).fetchone()
    return str(read)
