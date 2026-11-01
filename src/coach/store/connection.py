import sqlite3
from pathlib import Path

from coach.core.errors import Setup
from coach.store.chain import Chain, engine

# Services name the connection through store, so only store imports sqlite3 (ADR 0019).
type Connection = sqlite3.Connection


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    (version,) = conn.execute("PRAGMA user_version").fetchone()
    return version


def open_store(path: str | Path, chain: Chain | None = None) -> sqlite3.Connection:
    """Open the store, building a fresh database at the current version; no verb but
    `upgrade` reads a store behind the engine (`open_store_behind`)."""
    chain = chain or engine()
    conn = open_store_behind(path, chain)
    version = schema_version(conn)
    if version < chain.version:
        conn.close()
        raise Setup(
            "schema_behind",
            f"the store is at schema version {version} and the engine at {chain.version}; "
            "run `coach upgrade`",
        )
    return conn


def open_store_behind(path: str | Path, chain: Chain | None = None) -> sqlite3.Connection:
    """Open the store at whatever version it is, building a fresh database at the current one."""
    chain = chain or engine()
    conn = connect(path)
    if schema_version(conn) == 0 and _is_empty(conn):
        conn.executescript(chain.current)
        conn.execute(f"PRAGMA user_version = {chain.version}")
    return conn


def copy_to_memory(conn: sqlite3.Connection) -> sqlite3.Connection:
    """An in-memory copy of the store, for a dry run to work on and throw away."""
    copy = connect(":memory:")
    conn.backup(copy)
    copy.execute("PRAGMA foreign_keys = ON")
    return copy


def _is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT count(*) FROM sqlite_master").fetchone() == (0,)
