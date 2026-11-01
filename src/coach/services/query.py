import datetime
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast, get_args

from coach.core.config import Units
from coach.core.e1rm import point
from coach.core.errors import Invalid
from coach.core.exposure import Exposure
from coach.core.frozen_prescription import dose, frozen_groups
from coach.core.plan_check import CheckedPlan
from coach.core.planned_week import week_monday
from coach.core.registries.agent import RECORD_KINDS
from coach.core.registries.flags import Severity
from coach.services.history import read_history
from coach.store import (
    annotations,
    decisions,
    follow_ups,
    niggles,
    notes,
    observations,
    routine_map,
    week_plans,
    workouts,
)
from coach.store import exercises as library
from coach.store import readings as stored
from coach.store.connection import Connection
from coach.store.rows import Row

READING_KINDS = ("weigh_in", "sleep_night", "activity")
SEVERITIES: tuple[str, ...] = get_args(Severity.__value__)
# What `prescribe` calls a line whose load and shape did not move.
UNCHANGED = "held"


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


def exposures(
    conn: Connection,
    *,
    exercises: tuple[str, ...],
    since: datetime.date | None,
    last: int | None,
    units: Units,
) -> QueryResult:
    """`query exposures`: each Exposure with its annotations applied, newest first."""
    unknown = [e for e in exercises if library.get(conn, e) is None]
    if unknown:
        raise Invalid("unknown_exercise", f"no exercise {', '.join(unknown)} in the library")
    found = [
        e
        for e in read_history(conn, units).exposures
        if (not exercises or e.exercise_id in exercises) and (since is None or e.date >= since)
    ]
    found.sort(key=lambda e: e.exercise_id)
    found.sort(key=lambda e: (e.date, e.workout_id), reverse=True)
    return _newest([_exposure(e) for e in found], last)


def _exposure(exposure: Exposure) -> Row:
    top = exposure.top_load
    best = max(
        (p for s in exposure.working if (p := point(exposure, s)) is not None),
        key=lambda p: p.load.amount,
        default=None,
    )
    return {
        "exposure": exposure.ref,
        "date": exposure.date.isoformat(),
        "session": exposure.session_id,
        "load": None if top is None else top.amount,
        "load_mode": None if top is None else top.mode,
        "reps": [s.reps for s in exposure.working],
        "rpe": [s.rpe for s in exposure.working],
        "e1rm": None if best is None else best.load.amount,
        "e1rm_lower_bound": None if best is None else best.lower_bound,
        "annotations": list(exposure.annotations),
    }


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
    rows = [
        {"record_kind": kind, **row}
        for row in LEDGER_READERS[kind](conn, open_, today)
        if id_ is None or row["id"] == id_
    ]
    return _newest(rows, last)


def _kind_of(conn: Connection, id_: str) -> str:
    for kind in RECORD_KINDS.entries:
        if kind.id_prefix is not None and id_.startswith(kind.id_prefix):
            return kind.name
    return "exercise" if library.get(conn, id_) else "workout"


def routines(conn: Connection, *, last: int | None) -> QueryResult:
    """`query routines`: the Routine map joined to folders, not the mirror (cutover.md)."""
    return _newest(routine_map.joined(conn), last)


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
    return library.every(conn)


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


def _observations(conn: Connection, open_: bool, today: datetime.date) -> list[Row]:
    rows = observations.every(conn)
    if open_:
        rows = [r for r in rows if r["retired_at"] is None]
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
    "observation": _observations,
}


def flags(
    conn: Connection,
    *,
    draft: CheckedPlan | None,
    today: datetime.date,
    code: str | None,
    severity: str | None,
    scope: str | None,
    summary: bool,
    last: int | None,
) -> QueryResult:
    """`query flags`: the flags frozen on the plan in force, or those of a Draft validated now;
    with `summary` the counts by (code, severity)."""
    if severity is not None and severity not in SEVERITIES:
        raise Invalid("invalid_argument", f"--severity takes one of {', '.join(SEVERITIES)}")
    found = [
        flag
        for flag in _plan_flags(conn, draft, today)
        if (code is None or flag["code"] == code)
        and (severity is None or flag["severity"] == severity)
        and (scope is None or cast(Row, flag["scope"])["kind"] == scope)
    ]
    if summary:
        counts = Counter((str(f["code"]), str(f["severity"])) for f in found)
        rows: list[Row] = [
            {"code": c, "severity": s, "count": n} for (c, s), n in sorted(counts.items())
        ]
        return _newest(rows, last)
    return _newest([_flag_row(flag) for flag in found], last)


def lines(
    conn: Connection,
    *,
    draft: CheckedPlan | None,
    today: datetime.date,
    units: Units,
    exercises: tuple[str, ...],
    session: str | None,
    date: datetime.date | None,
    changed: bool,
    last: int | None,
) -> QueryResult:
    """`query lines`: each line of the plan in force, or of a Draft validated now, with its
    prescription, its change from the last exposure and its flag keys."""
    rows = [
        row
        for row in _plan_lines(conn, draft, today, units)
        if (not exercises or row["exercise"] in exercises)
        and (session is None or row["session"] == session)
        and (date is None or row["date"] == date.isoformat())
        and (not changed or row["change"] != UNCHANGED)
    ]
    return _newest(rows, last)


def _plan_flags(conn: Connection, draft: CheckedPlan | None, today: datetime.date) -> list[Row]:
    if draft is not None:
        return [flag.to_json() for flag in draft.flags]
    unique: dict[str, Row] = {}
    for row in _in_force_prescriptions(conn, today):
        for flag in cast(list[Row], row["flags"]):
            unique.setdefault(str(flag["key"]), flag)
    return list(unique.values())


def _plan_lines(
    conn: Connection, draft: CheckedPlan | None, today: datetime.date, units: Units
) -> list[Row]:
    if draft is not None:
        return [
            _line_row(
                prescribed.session.date.isoformat(),
                prescribed.session.session_id,
                line.exercise_id,
                frozen_groups(line.groups, units),
                line.change,
                [flag.key for flag in line.flags],
                units,
            )
            for prescribed in draft.draft.sessions
            for line in prescribed.lines
        ]
    return [
        _line_row(
            str(row["date"]),
            str(row["session_id"]),
            str(row["exercise_id"]),
            cast(list[Row], row["set_groups"]),
            str(row["change"]),
            [str(flag["key"]) for flag in cast(list[Row], row["flags"])],
            units,
        )
        for row in _in_force_prescriptions(conn, today)
    ]


def _in_force_prescriptions(conn: Connection, today: datetime.date) -> list[Row]:
    plan = week_plans.in_force(conn, week_monday(today).isoformat())
    return [] if plan is None else week_plans.prescriptions(conn, str(plan["id"]))


def _line_row(
    date: str,
    session: str,
    exercise: str,
    set_groups: Sequence[Mapping[str, object]],
    change: str,
    flag_keys: list[str],
    units: Units,
) -> Row:
    return {
        "date": date,
        "session": session,
        "exercise": exercise,
        "prescription": dose(set_groups, units),
        "change": change,
        "flags": flag_keys,
    }


def _flag_row(flag: Row) -> Row:
    return {
        "key": flag["key"],
        "code": flag["code"],
        "severity": flag["severity"],
        "message": flag["message"],
        "left": flag["left"],
    }
