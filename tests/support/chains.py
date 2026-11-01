"""Schema chains for tests: a temporary DDL whose second version needs a table rebuild, and the
engine's own schema with one probe table added, so `upgrade` migrates with no real schema change."""

import sqlite3

from coach.store.chain import ENGINE, Chain
from coach.store.migrations import rebuild_table

KIND_V1 = """CREATE TABLE kind (
  id    TEXT PRIMARY KEY,
  label TEXT NOT NULL CHECK (label IN ('a','b'))
);
"""
KIND_V2 = """CREATE TABLE kind (
  id    TEXT PRIMARY KEY,
  label TEXT NOT NULL CHECK (label IN ('a','b','c'))
);
"""
KIND_INDEX = "CREATE INDEX kind_label ON kind(label);\n"
REST = """CREATE TABLE item (
  id   TEXT PRIMARY KEY,
  kind TEXT NOT NULL REFERENCES kind(id)
);
CREATE VIEW item_label AS SELECT item.id, kind.label FROM item JOIN kind ON kind.id = item.kind;
"""

TEMPORARY_V1 = KIND_V1 + KIND_INDEX + REST
TEMPORARY_V2 = KIND_V2 + KIND_INDEX + REST


def widen_kind_label(conn: sqlite3.Connection) -> None:
    rebuild_table(conn, "kind", KIND_V2, indexes=(KIND_INDEX,))


TEMPORARY = Chain(current=TEMPORARY_V2, frozen={1: TEMPORARY_V1}, steps=(widen_kind_label,))

PROBE = "CREATE TABLE upgrade_probe (id TEXT PRIMARY KEY);\n"


def add_probe(conn: sqlite3.Connection) -> None:
    conn.execute(PROBE)


ENGINE_PLUS_PROBE = Chain(
    current=ENGINE.current + PROBE, frozen={1: ENGINE.current}, steps=(add_probe,)
)
