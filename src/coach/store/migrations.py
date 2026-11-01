from collections.abc import Callable

from coach.store.connection import Connection

type Migration = Callable[[Connection], None]

# MIGRATIONS[n - 1] moves a store from schema version n to n + 1 (schema.md, "Schema version and
# migrations"). The chain starts on cutover day.
MIGRATIONS: tuple[Migration, ...] = ()


def forward(conn: Connection, from_version: int) -> int:
    """Run every migration after `from_version` and return the version reached."""
    for migration in MIGRATIONS[from_version - 1 :]:
        migration(conn)
    return from_version + len(MIGRATIONS[from_version - 1 :])
