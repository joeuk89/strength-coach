from coach.store.connection import Connection

# Each ledger table a Draft verb writes, by record kind.
TABLES = {
    "decision": "decision",
    "note": "athlete_note",
    "weigh_in": "weigh_in",
    "sleep_night": "sleep_night",
    "activity": "activity",
    "status_span": "status_span",
    "workout": "workout",
}
# A record kind written as events: the event table and the column naming the record's id.
EVENTS = {
    "niggle": ("niggle_event", "niggle_id"),
    "followup": ("follow_up_event", "follow_up_id"),
}
WITHDRAWABLE = ("weigh_in", "sleep_night", "status_span")


def written_by(conn: Connection, draft_hash: str) -> dict[str, list[str]]:
    """The ids each record kind holds under one Draft hash, in id order."""
    found: dict[str, list[str]] = {}
    for kind, table in TABLES.items():
        ids = [
            id_
            for (id_,) in conn.execute(
                f"SELECT DISTINCT id FROM {table} WHERE draft_hash = ? ORDER BY id", (draft_hash,)
            )
        ]
        if ids:
            found[kind] = ids
    for kind, (table, column) in EVENTS.items():
        ids = [
            id_
            for (id_,) in conn.execute(
                f"SELECT {column} FROM {table} WHERE draft_hash = ? ORDER BY id", (draft_hash,)
            )
        ]
        if ids:
            found[kind] = ids
    return found


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
