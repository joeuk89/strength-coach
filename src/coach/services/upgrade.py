from dataclasses import dataclass

from coach.store.catalogue import merge_catalogue
from coach.store.chain import Chain, migrate
from coach.store.connection import Connection
from coach.store.export import Export, export
from coach.store.transaction import transaction


@dataclass(frozen=True)
class Upgraded:
    from_version: int
    to_version: int
    migrations: tuple[str, ...]
    catalogue_added: tuple[str, ...]
    export: Export


def upgrade(conn: Connection, *, engine_version: str, chain: Chain | None = None) -> Upgraded:
    """The store's half of `coach upgrade` (ADR 0007): migrate, merge the catalogue, export."""
    migrated = migrate(conn, chain)
    with transaction(conn):
        added = merge_catalogue(conn)
    return Upgraded(
        from_version=migrated.from_version,
        to_version=migrated.to_version,
        migrations=migrated.steps,
        catalogue_added=added,
        export=export(conn, engine_version),
    )
