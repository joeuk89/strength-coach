from coach.core.registries.agent import RECORD_KINDS, RecordKind
from coach.store.connection import Connection

WITHDRAWABLE = ("weigh_in", "sleep_night", "status_span", "annotation")


def written_by(conn: Connection, draft_hash: str) -> dict[str, list[str]]:
    """The ids each record kind holds under one Draft hash, in id order."""
    queries = {
        kind.name: _ids_written(kind) for kind in RECORD_KINDS.entries if kind.carries_draft_hash
    }
    found = {
        kind: [id_ for (id_,) in conn.execute(sql, (draft_hash,))] for kind, sql in queries.items()
    }
    return {kind: ids for kind, ids in found.items() if ids}


def withdrawn_by_draft(conn: Connection, draft_hash: str) -> list[str]:
    return [
        id_
        for table in WITHDRAWABLE
        for (id_,) in conn.execute(
            f"SELECT withdraws FROM {table} WHERE draft_hash = ? AND withdraws IS NOT NULL "
            "ORDER BY id",
            (draft_hash,),
        )
    ]


def _ids_written(kind: RecordKind) -> str:
    if kind.event_table is not None:
        return (
            f"SELECT {kind.store_table}_id FROM {kind.event_table} WHERE draft_hash = ? ORDER BY id"
        )
    return f"SELECT DISTINCT id FROM {kind.store_table} WHERE draft_hash = ? ORDER BY id"
