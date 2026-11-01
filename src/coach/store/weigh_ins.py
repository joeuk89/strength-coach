import sqlite3

from coach.core.log import WeighIn
from coach.store.ids import next_id


def live_weigh_ins(conn: sqlite3.Connection, source: str | None = None) -> tuple[WeighIn, ...]:
    rows = conn.execute(
        "SELECT id, date, kg, source FROM weigh_in_current"
        " WHERE ? IS NULL OR source = ? ORDER BY date, id",
        (source, source),
    ).fetchall()
    return tuple(WeighIn(*row) for row in rows)


def enter_weigh_in(
    conn: sqlite3.Connection, date: str, kg: float, source: str, recorded_at: str
) -> str:
    weigh_in_id = next_id(conn, "weigh_in", "wi-")
    conn.execute(
        "INSERT INTO weigh_in (id, date, kg, source, recorded_at) VALUES (?,?,?,?,?)",
        (weigh_in_id, date, kg, source, recorded_at),
    )
    return weigh_in_id


def withdraw_weigh_in(conn: sqlite3.Connection, live: WeighIn, recorded_at: str) -> str:
    """A withdrawing row restates the withdrawn row's required columns (schema.md, "Views")."""
    weigh_in_id = next_id(conn, "weigh_in", "wi-")
    conn.execute(
        "INSERT INTO weigh_in (id, date, kg, source, withdraws, recorded_at) VALUES (?,?,?,?,?,?)",
        (weigh_in_id, live.date, live.kg, live.source, live.id, recorded_at),
    )
    return weigh_in_id
