from collections.abc import Mapping

from coach.store.connection import Connection


def insert(conn: Connection, row: Mapping[str, object]) -> None:
    conn.execute(
        "INSERT INTO athlete_note (id, date, text, about, check_in, draft_hash, recorded_at) "
        "VALUES (:id, :date, :text, :about, :check_in, :draft_hash, :recorded_at)",
        dict(row),
    )
