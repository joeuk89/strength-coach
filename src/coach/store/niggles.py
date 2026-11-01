import json
from collections.abc import Mapping, Sequence
from typing import cast

from coach.core.prescription import NiggleConstraint
from coach.core.program.form import Session
from coach.core.program.parse import parse_line
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


def open_rehab_sessions(conn: Connection) -> tuple[Session, ...]:
    """The rehab session of every niggle short of `resolved` (ADR 0010)."""
    return tuple(
        _rehab_as_session(cast(Row, niggle["rehab_session"]))
        for niggle in every(conn)
        if niggle["status"] != "resolved" and niggle["rehab_session"] is not None
    )


def every_rehab_session(conn: Connection) -> tuple[Session, ...]:
    """Every niggle's rehab session, resolved or not: the rows are never updated."""
    return tuple(
        _rehab_as_session(cast(Row, niggle["rehab_session"]))
        for niggle in every(conn)
        if niggle["rehab_session"] is not None
    )


def open_constraints(conn: Connection) -> tuple[NiggleConstraint, ...]:
    """The constraint set in force on every niggle short of `resolved`."""
    return tuple(
        NiggleConstraint(
            niggle_id=str(niggle["id"]),
            kind=str(row["kind"]),
            exercise_id=cast(str | None, row["exercise_id"]),
            pattern=cast(str | None, row["pattern"]),
            value=cast(float | None, row["value"]),
        )
        for niggle in every(conn)
        if niggle["status"] != "resolved"
        for row in cast(list[Row], niggle["constraints"])
    )


def _rehab_as_session(row: Row) -> Session:
    session_id = str(row["session_id"])
    lines = tuple(
        parse_line(_line_document(line), file=f"rehab_session {session_id}")
        for line in cast(list[Mapping[str, object]], row["lines"])
    )
    return Session(
        id=session_id,
        title=str(row["title"]),
        kind="rehab",
        tier=str(row["tier"]),
        cadence=str(row["cadence"]),
        location=cast(str | None, row["location"]),
        lines=lines,
    )


def _line_document(line: Mapping[str, object]) -> dict[str, object]:
    document = {
        "exercise": line["exercise_id"],
        "sets": line["set_groups"],
        "rest_s": line["rest_s"],
        "scheme": line["scheme"],
        "load_mode": line.get("load_mode"),
        "cues": line.get("cues"),
        "start_load": line.get("start_load"),
        "superset": line.get("superset"),
    }
    return {key: value for key, value in document.items() if value is not None}
