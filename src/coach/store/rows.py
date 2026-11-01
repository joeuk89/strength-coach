from collections.abc import Sequence

from coach.store.connection import Connection

type Row = dict[str, object]


def select(conn: Connection, sql: str, params: Sequence[object] = ()) -> list[Row]:
    cursor = conn.execute(sql, tuple(params))
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, found, strict=True)) for found in cursor.fetchall()]
