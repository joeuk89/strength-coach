import json
from collections.abc import Mapping

from coach.store.connection import Connection
from coach.store.rows import Row, select

COLUMNS = (
    "id",
    "name",
    "load_mode",
    "equipment_kind",
    "pattern",
    "muscles",
    "hevy_title",
    "hevy_exercise_type",
    "hevy_equipment",
    "hevy_muscle_group",
    "hevy_template_id",
    "source",
)


def insert(conn: Connection, row: Mapping[str, object]) -> None:
    values = [_column(name, row.get(name)) for name in COLUMNS]
    conn.execute(f"INSERT INTO exercise VALUES ({', '.join('?' * len(COLUMNS))})", values)


def get(conn: Connection, id_: str) -> Row | None:
    found = conn.execute(
        f"SELECT {', '.join(COLUMNS)} FROM exercise WHERE id = ?", (id_,)
    ).fetchone()
    if found is None:
        return None
    row: Row = dict(zip(COLUMNS, found, strict=True))
    row["muscles"] = json.loads(str(row["muscles"]))
    return row


def update(conn: Connection, id_: str, fields: Mapping[str, object]) -> None:
    """An in-place edit: the library is a state table (schema.md, "Updated in place")."""
    assert fields and set(fields) <= set(COLUMNS) - {"id"}
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = [_column(name, value) for name, value in fields.items()]
    conn.execute(f"UPDATE exercise SET {assignments} WHERE id = ?", (*values, id_))


def carrying_template(conn: Connection, hevy_template_id: str) -> str | None:
    found = conn.execute(
        "SELECT id FROM exercise WHERE hevy_template_id = ?", (hevy_template_id,)
    ).fetchone()
    return found[0] if found else None


def _column(name: str, value: object) -> object:
    return json.dumps(value) if name == "muscles" else value


def every(conn: Connection) -> list[Row]:
    rows = select(conn, f"SELECT {', '.join(COLUMNS)} FROM exercise ORDER BY id")
    return [{**row, "muscles": json.loads(str(row["muscles"]))} for row in rows]
