from coach.store.connection import Connection


def insert(conn: Connection, session_id: str, introduced_in: str) -> None:
    conn.execute(
        "INSERT INTO session (id, introduced_in) VALUES (?, ?)", (session_id, introduced_in)
    )


def exists(conn: Connection, session_id: str) -> bool:
    return conn.execute("SELECT 1 FROM session WHERE id = ?", (session_id,)).fetchone() is not None
