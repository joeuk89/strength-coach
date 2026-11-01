from coach.store.connection import Connection
from coach.store.export import Export, export


def publish(conn: Connection, *, engine_version: str) -> Export:
    """What `publish` writes from the store: the export (schema.md, "Export")."""
    return export(conn, engine_version)
