import json
import sqlite3
from typing import Any, cast

from coach.core.errors import Setup


def load_rows(conn: sqlite3.Connection, table: str, text: str) -> int:
    """Insert each line of a `<table>.jsonl` document, keys in column order (`schema.md`)."""
    columns = [name for (_, name, *_) in conn.execute(f"PRAGMA table_info({table})")]
    insert = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    )
    count = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        row = _row(line, columns, table, number)
        conn.execute(insert, [row[column] for column in columns])
        count += 1
    return count


def _row(line: str, columns: list[str], table: str, number: int) -> dict[str, Any]:
    try:
        row: Any = json.loads(line)
    except json.JSONDecodeError as error:
        raise _malformed(table, number, f"is not JSON ({error.msg})") from error
    if not isinstance(row, dict):
        raise _malformed(table, number, "is not a JSON object")
    values = cast(dict[str, Any], row)
    if list(values) != columns:
        raise _malformed(table, number, f"has keys {list(values)}, not the columns {columns}")
    return values


def _malformed(table: str, number: int, problem: str) -> Setup:
    return Setup("jsonl_row_malformed", f"{table}.jsonl line {number} {problem}")
