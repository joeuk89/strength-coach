import json
from collections.abc import Mapping

from coach.store.connection import Connection
from coach.store.rows import Row, insert, select


def insert_decision(conn: Connection, row: Mapping[str, object]) -> None:
    insert(
        conn,
        "decision",
        {**row, "params": json.dumps(row["params"]), "evidence": _json_or_null(row["evidence"])},
    )


def get(conn: Connection, decision_id: str) -> Row | None:
    found = _decoded(select(conn, "SELECT * FROM decision WHERE id = ?", (decision_id,)))
    return found[0] if found else None


def in_force(conn: Connection, on: str | None = None) -> list[Row]:
    """Decisions in force: the view's rule, and with `on` the until filter for that date."""
    if on is None:
        return _decoded(select(conn, "SELECT * FROM decision_in_force ORDER BY id"))
    return _decoded(
        select(
            conn,
            "SELECT * FROM decision_in_force WHERE until IS NULL OR until >= ? ORDER BY id",
            (on,),
        )
    )


def every(conn: Connection) -> list[Row]:
    return _decoded(select(conn, "SELECT * FROM decision ORDER BY id"))


def supersede(conn: Connection, decision_ids: list[str], by: str) -> None:
    conn.executemany(
        "UPDATE decision SET superseded_by = ? WHERE id = ?", [(by, id_) for id_ in decision_ids]
    )


def retire(conn: Connection, decision_id: str, by: str) -> None:
    conn.execute("UPDATE decision SET retired_by = ? WHERE id = ?", (by, decision_id))


def _json_or_null(value: object) -> str | None:
    return json.dumps(value) if value else None


def _decoded(rows: list[Row]) -> list[Row]:
    for row in rows:
        row["params"] = json.loads(str(row["params"]))
        row["evidence"] = json.loads(str(row["evidence"])) if row["evidence"] else []
    return rows
