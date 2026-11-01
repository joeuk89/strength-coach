import sqlite3
from importlib.resources import files
from pathlib import Path

from coach.core.errors import Setup

SCHEMA_VERSION = 1

# Services name the connection through store, so only store imports sqlite3 (ADR 0019).
type Connection = sqlite3.Connection


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    (version,) = conn.execute("PRAGMA user_version").fetchone()
    return version


def open_store(path: str | Path) -> sqlite3.Connection:
    """Open the store, building a fresh database from `schema.sql` at the current version."""
    conn = connect(path)
    version = schema_version(conn)
    if version == 0 and _is_empty(conn):
        conn.executescript(files("coach.store").joinpath("schema.sql").read_text(encoding="utf-8"))
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    elif version < SCHEMA_VERSION:
        conn.close()
        raise Setup(
            "schema_behind",
            f"the store is at schema version {version} and the engine at {SCHEMA_VERSION}; "
            "run `coach upgrade`",
        )
    return conn


def _is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT count(*) FROM sqlite_master").fetchone() == (0,)
