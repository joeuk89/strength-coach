import datetime
import json
from collections.abc import Mapping
from typing import cast

from coach.core.instant import parse_instant
from coach.core.prescription import DecisionInForce
from coach.store import rows
from coach.store.connection import Connection
from coach.store.rows import Row, insert, select


def insert_decision(conn: Connection, row: Mapping[str, object]) -> None:
    insert(
        conn,
        "decision",
        {
            **row,
            "params": json.dumps(row["params"]),
            "evidence": json.dumps(row["evidence"]) if row["evidence"] else None,
        },
    )


def get(conn: Connection, decision_id: str) -> Row | None:
    found = _decoded(select(conn, "SELECT * FROM decision WHERE id = ?", (decision_id,)))
    return found[0] if found else None


def in_force(conn: Connection, on: str | None = None) -> list[Row]:
    """Decisions in force: the view's rule, and with `on` the until filter for that date."""
    if on is None:
        return _decoded(select(conn, "SELECT * FROM decision_in_force ORDER BY id"))
    return _decoded(
        select(
            conn,
            "SELECT * FROM decision_in_force WHERE until IS NULL OR until >= ? ORDER BY id",
            (on,),
        )
    )


def in_force_dated(
    conn: Connection,
    on: datetime.date | None,
    kinds: tuple[str, ...],
    zone: datetime.tzinfo | None,
) -> tuple[DecisionInForce, ...]:
    """The Decisions of `kinds` in force, each dated by the day it was recorded on in `zone`."""
    return tuple(
        DecisionInForce(
            id=str(row["id"]),
            kind=str(row["kind"]),
            session_id=cast(str | None, row["session_id"]),
            exercise_id=cast(str | None, row["exercise_id"]),
            params=cast(Mapping[str, object], row["params"]),
            on=parse_instant(str(row["recorded_at"])).astimezone(zone).date(),
        )
        for row in in_force(conn, None if on is None else on.isoformat())
        if row["kind"] in kinds
    )


def every(conn: Connection) -> list[Row]:
    return _decoded(select(conn, "SELECT * FROM decision ORDER BY id"))


def supersede(conn: Connection, decision_ids: list[str], by: str) -> None:
    for decision_id in decision_ids:
        rows.supersede(conn, "decision", decision_id, by)


def retire(conn: Connection, decision_id: str, by: str) -> None:
    conn.execute("UPDATE decision SET retired_by = ? WHERE id = ?", (by, decision_id))


def _decoded(found: list[Row]) -> list[Row]:
    for row in found:
        row["params"] = json.loads(str(row["params"]))
        row["evidence"] = json.loads(str(row["evidence"])) if row["evidence"] else []
    return found
