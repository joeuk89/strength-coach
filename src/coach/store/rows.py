from collections.abc import Iterator, Mapping, Sequence

from coach.store.connection import Connection

type Row = dict[str, object]


def select(conn: Connection, sql: str, params: Sequence[object] = ()) -> list[Row]:
    cursor = conn.execute(sql, tuple(params))
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, found, strict=True)) for found in cursor.fetchall()]


def tables(conn: Connection) -> tuple[str, ...]:
    """Every table by name; views and SQLite's own tables are not rows of the store."""
    found = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    )
    return tuple(name for (name,) in found)


def columns(conn: Connection, table: str) -> tuple[str, ...]:
    return tuple(row[1] for row in conn.execute(f"PRAGMA table_info({_quoted(table)})"))


def primary_key(conn: Connection, table: str) -> tuple[str, ...]:
    info = conn.execute(f"PRAGMA table_info({_quoted(table)})").fetchall()
    return tuple(row[1] for row in sorted((r for r in info if r[5]), key=lambda r: r[5]))


def load_order(conn: Connection) -> tuple[str, ...]:
    """Every table after the tables its foreign keys name; a table naming itself is not a wait."""
    waiting = {
        table: {row[2] for row in conn.execute(f"PRAGMA foreign_key_list({_quoted(table)})")}
        - {table}
        for table in tables(conn)
    }
    ordered: list[str] = []
    while waiting:
        ready = sorted(t for t, needs in waiting.items() if needs <= set(ordered))
        if not ready:
            raise ValueError(f"foreign keys form a cycle among {sorted(waiting)}")
        ordered.extend(ready)
        for table in ready:
            del waiting[table]
    return tuple(ordered)


def count(conn: Connection, table: str) -> int:
    (n,) = conn.execute(f"SELECT count(*) FROM {_quoted(table)}").fetchone()
    return n


def in_key_order(conn: Connection, table: str) -> Iterator[dict[str, object]]:
    """Rows as column-ordered dicts, sorted by primary key; text compares by code point."""
    names = columns(conn, table)
    order = ", ".join(_quoted(name) for name in primary_key(conn, table))
    cursor = conn.execute(f"SELECT * FROM {_quoted(table)} ORDER BY {order}")
    for values in cursor:
        yield dict(zip(names, values, strict=True))


def insert(conn: Connection, table: str, row: Mapping[str, object]) -> None:
    names = ", ".join(_quoted(name) for name in row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {_quoted(table)} ({names}) VALUES ({marks})", tuple(row.values()))


def supersede(conn: Connection, table: str, old_id: str, new_id: str) -> None:
    """The supersede write (schema.md, "Updated in place"): point the old row at the new one."""
    flip = ", status = 'superseded'" if "status" in columns(conn, table) else ""
    conn.execute(
        f"UPDATE {_quoted(table)} SET superseded_by = ?{flip} WHERE id = ?", (new_id, old_id)
    )


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
