import datetime
from collections.abc import Callable
from dataclasses import dataclass

from coach.core.errors import Invalid
from coach.core.registries.agent import RECORD_KINDS
from coach.services.ledger import ID_PREFIX
from coach.store import annotations, decisions, exercises, follow_ups, niggles, notes, workouts
from coach.store import readings as stored
from coach.store.connection import Connection
from coach.store.rows import Row

READING_KINDS = ("weigh_in", "sleep_night", "activity")


@dataclass(frozen=True)
class QueryResult:
    rows: list[Row]
    count: int
    truncated: bool


def readings(conn: Connection, *, kind: str | None, last: int | None) -> QueryResult:
    """`query readings`: live Weigh-ins, Sleep nights and Activities, newest first."""
    if kind is not None and kind not in READING_KINDS:
        raise Invalid("invalid_argument", f"--kind takes one of {', '.join(READING_KINDS)}")
    rows = [
        _reading(table, row)
        for table in (READING_KINDS if kind is None else (kind,))
        for row in stored.live(conn, table)
    ]
    rows.sort(key=lambda r: (str(r.get("date", r.get("night"))), str(r["id"])), reverse=True)
    return _newest(rows, last)


def ledger(
    conn: Connection,
    *,
    kind: str | None,
    id_: str | None,
    open_: bool,
    today: datetime.date,
    last: int | None,
) -> QueryResult:
    """`query ledger`: one record kind's rows with their withdrawals, or one record by id."""
    if kind is None and id_ is None:
        raise Invalid("invalid_argument", "query ledger takes --kind, --id or both")
    kind = kind or _kind_of(conn, str(id_))
    if kind not in RECORD_KINDS:
        raise Invalid("invalid_argument", f"{kind!r} is not a record kind")
    reader = LEDGER_READERS.get(kind)
    if reader is None:
        raise Invalid("invalid_argument", f"query ledger does not read {kind} yet")
    rows = [
        {"record_kind": kind, **row}
        for row in reader(conn, open_, today)
        if id_ is None or row["id"] == id_
    ]
    return _newest(rows, last)


def _kind_of(conn: Connection, id_: str) -> str:
    for kind, (_, prefix) in ID_PREFIX.items():
        if id_.startswith(prefix):
            return kind
    return "exercise" if exercises.get(conn, id_) else "workout"


def _newest(rows: list[Row], last: int | None) -> QueryResult:
    kept = rows[:last]
    return QueryResult(kept, len(rows), len(kept) < len(rows))


def _reading(table: str, row: Row) -> Row:
    shown: Row = {"record_kind": table, "id": row["id"]}
    if table == "weigh_in":
        shown.update(date=row["date"], kg=row["kg"], source=row["source"])
    elif table == "sleep_night":
        shown.update(night=row["night"], hours=row["hours"], source=row["source"])
    else:
        fields = ("date", "kind", "minutes", "distance_km", "rpe", "text")
        shown.update({column: row[column] for column in fields})
        shown["quality"] = bool(row["quality"])
        shown["source"] = "check_in" if row["check_in"] else "manual"
    return shown


def _activity(row: Row) -> Row:
    return {**row, "quality": bool(row["quality"])}


def _newest_first(rows: list[Row], day: str) -> list[Row]:
    return sorted(rows, key=lambda r: (str(r[day]), str(r["id"])), reverse=True)


def _unwithdrawn(rows: list[Row]) -> list[Row]:
    return [r for r in rows if r["withdraws"] is None and r["withdrawn_by"] is None]


def _withdrawable(table: str, day: str) -> Callable[[Connection, bool, datetime.date], list[Row]]:
    def read(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
        rows = stored.with_withdrawals(conn, table)
        return _newest_first(_unwithdrawn(rows) if open_ else rows, day)

    return read


def _status_spans(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    rows = _withdrawable("status_span", "from_date")(conn, open_, today)
    if open_:
        rows = [r for r in rows if r["to_date"] is None or str(r["to_date"]) >= today.isoformat()]
    return rows


def _activities(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    return _newest_first([_activity(r) for r in stored.live(conn, "activity")], "date")


def _notes(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    return _newest_first(notes.every(conn), "date")


def _workouts(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    return _newest_first(workouts.latest(conn, current_only=open_), "date")


def _exercises(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    return exercises.every(conn)


def _niggles(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    rows = niggles.every(conn)
    if open_:
        rows = [r for r in rows if r["status"] != "resolved"]
    return _newest_first(rows, "opened")


def _follow_ups(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    rows = follow_ups.every(conn)
    if open_:
        rows = [r for r in rows if r["kind"] not in ("resolved", "dropped")]
    return _newest_first(rows, "raised")


def _decisions(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    rows = decisions.in_force(conn, today.isoformat()) if open_ else decisions.every(conn)
    return sorted(rows, key=lambda r: str(r["id"]), reverse=True)


def _annotations(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    rows = annotations.every(conn)
    return sorted(_unwithdrawn(rows) if open_ else rows, key=lambda r: str(r["id"]), reverse=True)


# Notes, Activities and Exercises have no lifecycle, so `--open` keeps every row of them.
LEDGER_READERS: dict[str, Callable[[Connection, bool, datetime.date], list[Row]]] = {
    "niggle": _niggles,
    "followup": _follow_ups,
    "decision": _decisions,
    "annotation": _annotations,
    "note": _notes,
    "weigh_in": _withdrawable("weigh_in", "date"),
    "sleep_night": _withdrawable("sleep_night", "night"),
    "activity": _activities,
    "status_span": _status_spans,
    "workout": _workouts,
    "exercise": _exercises,
}
