from collections.abc import Mapping
from dataclasses import dataclass

from coach.store.connection import Connection
from coach.store.rows import Row, select

# The withdrawable tables and the column naming the day a reading is about.
DAY_COLUMN = {"weigh_in": "date", "sleep_night": "night", "status_span": "from_date"}
TABLES = ("weigh_in", "sleep_night", "activity", "status_span")


@dataclass(frozen=True)
class Duplicate:
    table: str
    day: str
    source: str
    ids: tuple[str, ...]


def insert(conn: Connection, table: str, row: Mapping[str, object]) -> None:
    assert table in TABLES
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(row.values()))


def get(conn: Connection, table: str, id_: str) -> Row | None:
    assert table in TABLES
    found = select(conn, f"SELECT * FROM {table} WHERE id = ?", (id_,))
    return found[0] if found else None


def live(conn: Connection, table: str) -> list[Row]:
    """Rows neither withdrawn nor withdrawing; every activity row, since none is withdrawn."""
    assert table in TABLES
    source = f"{table}_current" if table in DAY_COLUMN else table
    return select(conn, f"SELECT * FROM {source} ORDER BY id")


def with_withdrawals(conn: Connection, table: str) -> list[Row]:
    """Every row, each with the id of the row withdrawing it, if any."""
    assert table in DAY_COLUMN
    return select(
        conn,
        f"SELECT r.*, (SELECT b.id FROM {table} b WHERE b.withdraws = r.id) AS withdrawn_by "
        f"FROM {table} r ORDER BY r.id",
    )


def withdrawn_by(conn: Connection, table: str, id_: str) -> str | None:
    assert table in DAY_COLUMN
    found = conn.execute(f"SELECT id FROM {table} WHERE withdraws = ?", (id_,)).fetchone()
    return found[0] if found else None


def duplicates(conn: Connection, table: str) -> list[Duplicate]:
    """Days with more than one live reading from one source: `reading_duplicate`."""
    assert table in ("weigh_in", "sleep_night")
    day = DAY_COLUMN[table]
    rows = conn.execute(
        f"SELECT {day}, source, group_concat(id, ',') FROM {table}_current "
        f"GROUP BY {day}, source HAVING count(*) > 1 ORDER BY {day}, source"
    ).fetchall()
    return [Duplicate(table, d, s, tuple(sorted(ids.split(",")))) for d, s, ids in rows]
