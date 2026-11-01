from coach.store.connection import Connection


def next_ids(conn: Connection, table: str, prefix: str, count: int) -> list[str]:
    """`count` ids after the highest `<prefix><n>` stored: max plus one, four digits (schema.md)."""
    (highest,) = conn.execute(
        f"SELECT max(CAST(substr(id, ?) AS INTEGER)) FROM {table} WHERE id LIKE ? || '%'",
        (len(prefix) + 1, prefix),
    ).fetchone()
    start = (highest or 0) + 1
    return [f"{prefix}{n:04d}" for n in range(start, start + count)]


def next_id(conn: Connection, table: str, prefix: str) -> str:
    return next_ids(conn, table, prefix, 1)[0]
