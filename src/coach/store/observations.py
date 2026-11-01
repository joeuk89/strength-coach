import json
from collections.abc import Mapping

from coach.store import rows
from coach.store.connection import Connection
from coach.store.rows import Row, select


def insert(conn: Connection, row: Mapping[str, object]) -> None:
    evidence = row["evidence"]
    rows.insert(
        conn, "observation", {**row, "evidence": json.dumps(evidence) if evidence else None}
    )


def get(conn: Connection, observation_id: str) -> Row | None:
    found = select(conn, "SELECT * FROM observation WHERE id = ?", (observation_id,))
    return found[0] if found else None


def retire(
    conn: Connection, observation_id: str, *, retired_at: str, because: str, check_in: str
) -> None:
    """Retired in place: the retiring check-in is the audit (schema.md, "Updated in place")."""
    conn.execute(
        "UPDATE observation SET retired_at = ?, retired_because = ?, retired_check_in = ? "
        "WHERE id = ?",
        (retired_at, because, check_in, observation_id),
    )


def current(conn: Connection) -> list[str]:
    return [
        id_
        for (id_,) in conn.execute(
            "SELECT id FROM observation WHERE retired_at IS NULL ORDER BY id"
        )
    ]


def retired_by(conn: Connection, check_in: str) -> list[str]:
    return [
        id_
        for (id_,) in conn.execute(
            "SELECT id FROM observation WHERE retired_check_in = ? ORDER BY id", (check_in,)
        )
    ]
