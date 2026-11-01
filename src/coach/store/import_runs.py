import datetime
import json
import sqlite3
from collections.abc import Mapping

from coach.core.instant import parse_instant
from coach.core.log import ImportRun
from coach.store.ids import next_id


def last_import_at(conn: sqlite3.Connection) -> datetime.datetime | None:
    (at,) = conn.execute("SELECT max(at) FROM import_run").fetchone()
    return parse_instant(at) if at else None


def record_import_run(
    conn: sqlite3.Connection,
    *,
    at: str,
    since: str | None,
    kind: str,
    summary: Mapping[str, int],
) -> str:
    run_id = next_id(conn, "import_run", "ir-")
    conn.execute(
        "INSERT INTO import_run (id, at, since, kind, only, summary) VALUES (?,?,?,?,NULL,?)",
        (run_id, at, since, kind, json.dumps(dict(summary), sort_keys=True)),
    )
    return run_id


def import_runs(conn: sqlite3.Connection) -> tuple[ImportRun, ...]:
    return tuple(
        ImportRun(run_id, at, since, kind, json.loads(summary))
        for run_id, at, since, kind, summary in conn.execute(
            "SELECT id, at, since, kind, summary FROM import_run ORDER BY at, id"
        )
    )
