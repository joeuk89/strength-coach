from collections.abc import Mapping
from dataclasses import dataclass

from coach.store.connection import Connection

type Row = dict[str, object]

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
    cursor = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,))
    found = cursor.fetchone()
    if found is None:
        return None
    return dict(zip([d[0] for d in cursor.description], found, strict=True))


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
