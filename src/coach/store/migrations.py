import sqlite3
from collections.abc import Callable, Sequence

type Migration = Callable[[sqlite3.Connection], None]

# MIGRATIONS[n - 1] moves a store from schema version n to n + 1, and is added with
# schema_history/v<n>.sql, the schema.sql it leaves behind (schema.md, "Schema version and
# migrations"). The chain starts on cutover day.

REASONS_V1 = "'athlete_request','coach_judgement')"
REASONS_V2 = "'athlete_request','coach_judgement','progress')"
DECISION_KINDS_V1 = "'against_research','retire')"
DECISION_KINDS_V2 = "'against_research','ladder_rung','retire')"


def m0001(conn: sqlite3.Connection) -> None:
    """The reason `progress` and the Decision kind `ladder_rung` (ADR 0023)."""
    for table in ("acknowledgement", "override", "annotation"):
        widen_checks(conn, table, ((REASONS_V1, REASONS_V2),))
    widen_checks(
        conn, "decision", ((REASONS_V1, REASONS_V2), (DECISION_KINDS_V1, DECISION_KINDS_V2))
    )


MIGRATIONS: tuple[Migration, ...] = (m0001,)


def widen_checks(
    conn: sqlite3.Connection, table: str, replacements: Sequence[tuple[str, str]]
) -> None:
    """Rebuild `table` from its own stored DDL with each CHECK list text replaced, keeping its
    indexes as they were."""
    (create,) = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    for before, after in replacements:
        if before not in create:
            raise sqlite3.OperationalError(f"{table} has no CHECK list {before!r} to widen")
        create = create.replace(before, after)
    indexes = [
        sql
        for (sql,) in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? "
            "AND sql IS NOT NULL ORDER BY name",
            (table,),
        )
    ]
    rebuild_table(conn, table, create, indexes=indexes)


def rebuild_table(
    conn: sqlite3.Connection, table: str, create: str, *, indexes: Sequence[str] = ()
) -> None:
    """Give `table` the shape `create` declares, keeping the columns both shapes share.

    SQLite alters no UNIQUE or CHECK in place (ADR 0001). Runs inside `migrate`, which holds
    foreign keys off; legacy renaming leaves the views and child tables naming `table` as they are.
    """
    aside = f"{table}__before_migration"
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        conn.execute(f"ALTER TABLE {_quoted(table)} RENAME TO {_quoted(aside)}")
        conn.execute(create)
        kept = [name for name in _columns(conn, table) if name in _columns(conn, aside)]
        names = ", ".join(_quoted(name) for name in kept)
        conn.execute(f"INSERT INTO {_quoted(table)} ({names}) SELECT {names} FROM {_quoted(aside)}")
        conn.execute(f"DROP TABLE {_quoted(aside)}")
        for index in indexes:
            conn.execute(index)
    finally:
        conn.execute("PRAGMA legacy_alter_table = OFF")


def _columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(row[1] for row in conn.execute(f"PRAGMA table_info({_quoted(table)})"))


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
