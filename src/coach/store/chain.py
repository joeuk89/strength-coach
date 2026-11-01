import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files

from coach.store.migrations import MIGRATIONS, Migration


@dataclass(frozen=True)
class Chain:
    """The store's schema at every version: the current DDL, the frozen DDL of each past
    version, and the migration from each version to the next."""

    current: str
    frozen: Mapping[int, str]
    steps: tuple[Migration, ...]

    @property
    def version(self) -> int:
        return len(self.steps) + 1

    def ddl(self, version: int) -> str:
        return self.current if version == self.version else self.frozen[version]

    def pending(self, version: int) -> tuple[str, ...]:
        return tuple(step_name(n) for n in range(version, self.version))


@dataclass(frozen=True)
class Migrated:
    from_version: int
    to_version: int
    steps: tuple[str, ...]


def step_name(from_version: int) -> str:
    return f"m{from_version:04d}"


def packaged() -> Chain:
    store = files("coach.store")
    history = store / "schema_history"
    entries = history.iterdir() if history.is_dir() else ()
    frozen = {
        int(entry.name.removeprefix("v").removesuffix(".sql")): entry.read_text(encoding="utf-8")
        for entry in entries
        if entry.name.startswith("v") and entry.name.endswith(".sql")
    }
    current = (store / "schema.sql").read_text(encoding="utf-8")
    return Chain(current=current, frozen=frozen, steps=MIGRATIONS)


ENGINE = packaged()


def engine() -> Chain:
    return ENGINE


def migrate(conn: sqlite3.Connection, chain: Chain | None = None) -> Migrated:
    """Run every pending migration in one transaction and move `user_version` to the end."""
    chain = chain or engine()
    (start,) = conn.execute("PRAGMA user_version").fetchone()
    names = chain.pending(start)
    if not names:
        return Migrated(from_version=start, to_version=start, steps=())
    conn.commit()
    # Foreign keys cannot be switched inside a transaction, and a table rebuild needs them off.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for step in chain.steps[start - 1 :]:
                step(conn)
            orphans = conn.execute("PRAGMA foreign_key_check").fetchall()
            if orphans:
                raise sqlite3.IntegrityError(f"the migrations left orphaned rows: {orphans[:5]}")
            conn.execute(f"PRAGMA user_version = {chain.version}")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    return Migrated(from_version=start, to_version=chain.version, steps=names)
