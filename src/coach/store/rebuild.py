import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from coach.core.errors import Setup
from coach.store import migrations, rows
from coach.store.connection import SCHEMA_VERSION, Connection, connect
from coach.store.export import read_manifest


@dataclass(frozen=True)
class Rebuilt:
    """The store was rebuilt from an export written at `schema_version`."""

    schema_version: int


def rebuild_missing(database: Path, export_dir: Path) -> Rebuilt | None:
    """Build a missing database from `export_dir`; a database that exists is never touched."""
    if database.exists():
        return None
    manifest = read_manifest(export_dir)
    if manifest is None:
        return None
    if manifest.schema_version > SCHEMA_VERSION:
        raise Setup(
            "export_newer_than_engine",
            f"export/ was written at schema version {manifest.schema_version} and this engine "
            f"reads up to {SCHEMA_VERSION}; install the engine the instance pins",
        )
    building = database.with_name(database.name + ".rebuilding")
    building.unlink(missing_ok=True)
    try:
        conn = connect(building)
        try:
            _build(conn, export_dir, manifest.schema_version)
        finally:
            conn.close()
        building.replace(database)
    finally:
        building.unlink(missing_ok=True)
    return Rebuilt(schema_version=manifest.schema_version)


def _build(conn: Connection, export_dir: Path, version: int) -> None:
    conn.executescript(_ddl(version))
    with conn:
        conn.execute("BEGIN")
        # Supersede pointers name later rows, so foreign keys are checked at commit, not per row.
        conn.execute("PRAGMA defer_foreign_keys = ON")
        for table in rows.load_order(conn):
            names = rows.columns(conn, table)
            text = (export_dir / f"{table}.jsonl").read_text(encoding="utf-8")
            for line in text.splitlines():
                row = json.loads(line)
                if list(row) != list(names):
                    raise ValueError(f"export/{table}.jsonl has a row not in {table}'s columns")
                rows.insert(conn, table, row)
        reached = migrations.forward(conn, version)
        conn.execute(f"PRAGMA user_version = {reached}")


def _ddl(version: int) -> str:
    store = files("coach.store")
    if version == SCHEMA_VERSION:
        return (store / "schema.sql").read_text(encoding="utf-8")
    return (store / "schema_history" / f"v{version}.sql").read_text(encoding="utf-8")
