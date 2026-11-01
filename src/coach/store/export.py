import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from coach.store import rows
from coach.store.connection import Connection, schema_version

MANIFEST = "manifest.json"


@dataclass(frozen=True)
class Export:
    """The export as text: file name inside `export/` to its contents, and rows per table."""

    files: Mapping[str, str]
    rows: Mapping[str, int]


def export(conn: Connection, engine_version: str) -> Export:
    files: dict[str, str] = {}
    counts: dict[str, int] = {}
    for table in rows.tables(conn):
        lines = [_line(row) for row in rows.in_key_order(conn, table)]
        files[f"{table}.jsonl"] = "".join(lines)
        counts[table] = len(lines)
    manifest = {
        "schema_version": schema_version(conn),
        "engine_version": engine_version,
        "tables": counts,
    }
    files[MANIFEST] = json.dumps(manifest, indent=2) + "\n"
    return Export(files=files, rows=counts)


def on_disk(export_dir: Path) -> dict[str, str]:
    """The export files as they stand in `export_dir`, to compare with a fresh export."""
    if not export_dir.is_dir():
        return {}
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(export_dir.iterdir())
        if path.name == MANIFEST or path.suffix == ".jsonl"
    }


def _line(row: Mapping[str, object]) -> str:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    engine_version: str
    tables: Mapping[str, int]


def read_manifest(export_dir: Path) -> Manifest | None:
    path = export_dir / MANIFEST
    return parse_manifest(path.read_text(encoding="utf-8")) if path.is_file() else None


def parse_manifest(text: str) -> Manifest:
    document = json.loads(text)
    return Manifest(
        schema_version=document["schema_version"],
        engine_version=document["engine_version"],
        tables=document["tables"],
    )


def tables_behind(conn: Connection, manifest: Manifest) -> tuple[str, ...]:
    """Tables whose manifest row count exceeds the store's (`store_behind_export`)."""
    present = set(rows.tables(conn))
    return tuple(
        table
        for table, exported in sorted(manifest.tables.items())
        if exported > (rows.count(conn, table) if table in present else 0)
    )
