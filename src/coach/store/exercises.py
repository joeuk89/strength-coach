import json
from collections.abc import Mapping
from typing import cast

from coach.core.exposure import LibraryEntry
from coach.core.load import LoadMode
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
    return None if found is None else _decoded(dict(zip(COLUMNS, found, strict=True)))


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
    return [_decoded(row) for row in rows]


def _decoded(row: Row) -> Row:
    return {**row, "muscles": json.loads(str(row["muscles"]))}


def library(conn: Connection) -> dict[str, LibraryEntry]:
    """Each Exercise by the Hevy template id it carries."""
    found = conn.execute(
        "SELECT hevy_template_id, id, load_mode FROM exercise WHERE hevy_template_id IS NOT NULL"
    )
    return {
        template_id: LibraryEntry(id_, cast(LoadMode, load_mode))
        for template_id, id_, load_mode in found
    }
