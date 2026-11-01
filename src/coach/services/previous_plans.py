"""What a new plan Draft reads of the approved WeekPlans before it: the second-week flags."""

import datetime
from collections.abc import Mapping, Sequence
from typing import cast

from coach.core.config import Units
from coach.core.flag import Flag
from coach.core.instant import parse_instant
from coach.core.load import LoadMode
from coach.core.prescription import PlanOverride, SessionPrescription
from coach.core.rack import Rack
from coach.core.second_week import (
    FrozenLineFacts,
    LineOverride,
    PastPlan,
    PreviousPlan,
    counted_overrides,
    frozen_load_off_rack,
    override_persisting,
    unexplained_drift,
)
from coach.store import decisions, exercises, niggles, programs, week_plans
from coach.store.connection import Connection
from coach.store.rows import Row


def second_week_flags(
    conn: Connection,
    sessions: Sequence[SessionPrescription],
    overrides: Sequence[PlanOverride],
    *,
    monday: datetime.date,
    racks: Mapping[str, Mapping[str, Rack]],
    units: Units,
) -> tuple[Flag, ...]:
    earlier = week_plans.approved_before(conn, monday.isoformat())
    persisting = override_persisting(
        overrides,
        [_past(conn, row) for row in earlier],
        covered=_covered(conn, monday),
        monday=monday,
    )
    if not earlier:
        return persisting
    previous = _previous(conn, earlier[0])
    drift = (
        ()
        if _version_since(conn, earlier[0])
        else unexplained_drift(sessions, overrides, previous, monday=monday, units=units)
    )
    return (*drift, *persisting, *frozen_load_off_rack(previous, racks, monday=monday))


def _past(conn: Connection, row: Row) -> PastPlan:
    week = datetime.date.fromisoformat(str(row["week"]))
    overrides = week_plans.stored_overrides(conn, str(row["id"]))
    return PastPlan(str(row["id"]), counted_overrides(overrides, _covered(conn, week)))


def _covered(conn: Connection, monday: datetime.date) -> frozenset[LineOverride]:
    """The line overrides an override Decision in force on that Monday carries."""
    return frozenset(
        (
            str(cast(Mapping[str, Mapping[str, object]], row["params"])["override"]["kind"]),
            str(row["session_id"]),
            str(row["exercise_id"]),
        )
        for row in decisions.in_force(conn, monday.isoformat())
        if row["kind"] == "override" and row["session_id"] and row["exercise_id"]
    )


def _previous(conn: Connection, row: Row) -> PreviousPlan:
    plan_id = str(row["id"])
    locations = _locations(conn)
    library = {str(e["id"]): e for e in exercises.every(conn)}
    lines = tuple(
        FrozenLineFacts(
            session_id=str(r["session_id"]),
            exercise_id=str(r["exercise_id"]),
            derived_from=str(r["derived_from"]),
            set_groups=cast(list[Mapping[str, object]], r["set_groups"]),
            location=locations.get(str(r["session_id"])),
            equipment_kind=_column(library, str(r["exercise_id"]), "equipment_kind"),
            load_mode=cast(
                LoadMode, _column(library, str(r["exercise_id"]), "load_mode") or "total"
            ),
        )
        for r in week_plans.prescriptions(conn, plan_id)
    )
    return PreviousPlan(
        plan_id,
        datetime.date.fromisoformat(str(row["week"])),
        lines,
        week_plans.stored_overrides(conn, plan_id),
    )


def _locations(conn: Connection) -> dict[str, str]:
    """Each session in force at its location; a session naming none trains at the version's."""
    version = programs.latest(conn)
    if version is None:
        return {}
    default = version.form.location
    sessions = (*version.form.sessions, *niggles.open_rehab_sessions(conn))
    return {s.id: s.location or default for s in sessions}


def _version_since(conn: Connection, row: Row) -> bool:
    """A version adopted after the plan was approved explains any change of its lines."""
    version = programs.latest(conn)
    return version is not None and parse_instant(version.recorded_at) > parse_instant(
        str(row["approved_at"])
    )


def _column(library: Mapping[str, Row], exercise_id: str, column: str) -> str | None:
    entry = library.get(exercise_id)
    return None if entry is None else cast(str | None, entry[column])
