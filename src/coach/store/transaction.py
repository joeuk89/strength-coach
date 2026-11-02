from collections.abc import Generator
from contextlib import contextmanager

from coach.store.connection import Connection


@contextmanager
def transaction(conn: Connection, *, commit: bool = True) -> Generator[None]:
    """One write transaction, taken before the first read so ids assigned inside it hold.
    With `commit` false it rolls back even on success: a dry run of the real write."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT" if commit else "ROLLBACK")
