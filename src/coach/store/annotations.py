import json
from collections.abc import Mapping
from typing import cast

from coach.core.exposure import Annotation
from coach.store.connection import Connection
from coach.store.rows import Row, insert, select


def insert_annotation(conn: Connection, row: Mapping[str, object]) -> None:
    params = row.get("params")
    insert(conn, "annotation", {**row, "params": json.dumps(params) if params else None})


def get(conn: Connection, annotation_id: str) -> Row | None:
    found = select(conn, "SELECT * FROM annotation WHERE id = ?", (annotation_id,))
    return found[0] if found else None


def withdrawn_by(conn: Connection, annotation_id: str) -> str | None:
    found = conn.execute(
        "SELECT id FROM annotation WHERE withdraws = ?", (annotation_id,)
    ).fetchone()
    return found[0] if found else None


def every(conn: Connection) -> list[Row]:
    """Every annotation with the id of the row withdrawing it, if any."""
    rows = select(
        conn,
        "SELECT a.*, (SELECT b.id FROM annotation b WHERE b.withdraws = a.id) AS withdrawn_by "
        "FROM annotation a ORDER BY a.id",
    )
    for row in rows:
        row["params"] = json.loads(str(row["params"])) if row["params"] else None
    return rows


def live(conn: Connection) -> tuple[Annotation, ...]:
    """`annotation_current` without the withdrawing rows, which are never read."""
    found = conn.execute(
        "SELECT id, kind, target, params FROM annotation_current WHERE withdraws IS NULL"
    ).fetchall()
    return tuple(
        Annotation(id_, kind, target, cast(dict[str, object], json.loads(params or "{}")))
        for id_, kind, target, params in found
    )
