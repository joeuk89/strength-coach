import json
from collections.abc import Mapping, Sequence

from coach.store.connection import Connection
from coach.store.rows import Row, insert, select

CONSTRAINT_COLUMNS = ("kind", "exercise_id", "pattern", "value")


def insert_niggle(conn: Connection, row: Mapping[str, object]) -> None:
    insert(conn, "niggle", row)


def insert_event(
    conn: Connection, row: Mapping[str, object], constraints: Sequence[Mapping[str, object]]
) -> None:
    """One niggle event and the whole constraint set in force from its date."""
    insert(conn, "niggle_event", row)
    for constraint in constraints:
        insert(conn, "niggle_constraint", {**constraint, "event_id": row["id"]})


def insert_rehab_session(conn: Connection, row: Mapping[str, object]) -> None:
    insert(conn, "rehab_session", {**row, "lines": json.dumps(row["lines"])})


def exists(conn: Connection, niggle_id: str) -> bool:
    found = conn.execute("SELECT 1 FROM niggle WHERE id = ?", (niggle_id,)).fetchone()
    return found is not None


def every(conn: Connection) -> list[Row]:
    """Every niggle with its status in force, its events oldest first, each with its
    constraints, and the latest event's constraints as the set in force."""
    niggles = select(
        conn,
        "SELECT n.id, n.opened, n.site, n.rehab_session_id, c.status, c.date, c.event_id, "
        "n.draft_hash, n.recorded_at FROM niggle n JOIN niggle_current c ON c.niggle_id = n.id "
        "ORDER BY n.id",
    )
    for niggle in niggles:
        events = select(
            conn,
            "SELECT id, date, status, text, check_in, draft_hash, recorded_at FROM niggle_event "
            "WHERE niggle_id = ? ORDER BY date, id",
            (niggle["id"],),
        )
        for event in events:
            event["constraints"] = _constraints(conn, str(event["id"]))
        event_id = niggle.pop("event_id")
        niggle["constraints"] = next(e["constraints"] for e in events if e["id"] == event_id)
        niggle["rehab_session"] = _rehab_session(conn, niggle["rehab_session_id"])
        niggle["events"] = events
    return niggles


def _constraints(conn: Connection, event_id: str) -> list[Row]:
    return select(
        conn,
        f"SELECT {', '.join(CONSTRAINT_COLUMNS)} FROM niggle_constraint WHERE event_id = ? "
        "ORDER BY id",
        (event_id,),
    )


def _rehab_session(conn: Connection, session_id: object) -> Row | None:
    found = select(
        conn,
        "SELECT session_id, title, tier, cadence, location, lines FROM rehab_session "
        "WHERE session_id = ?",
        (session_id,),
    )
    if not found:
        return None
    return {**found[0], "lines": json.loads(str(found[0]["lines"]))}
