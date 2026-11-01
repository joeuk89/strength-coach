from collections.abc import Generator
from contextlib import contextmanager

from coach.store.connection import Connection


@contextmanager
def transaction(conn: Connection) -> Generator[None]:
    """One write transaction, taken before the first read so ids assigned inside it hold."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
