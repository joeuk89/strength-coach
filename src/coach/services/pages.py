"""The values every rendered page is drawn from, read from the store as it stands (ADR 0012)."""

import datetime
from collections.abc import Mapping, Sequence
from typing import cast

from coach.core.config import Config, PlatePoolLocation, Units
from coach.core.kit import SHORT_HASH_LENGTH, KitFiles
from coach.core.pages import (
    AthletePage,
    CheckInRecord,
    DecisionRead,
    FollowUpRead,
    NiggleRead,
    PageLine,
    Pages,
    PlannedSessionPage,
    PlatePoolKit,
    RoutinePage,
    WeekPage,
)
from coach.core.program.form import Session
from coach.services.checkin_open import record_card
from coach.services.progress import newest_day, progress
from coach.store import (
    check_ins,
    decisions,
    exercises,
    follow_ups,
    niggles,
    observations,
    programs,
    routine_map,
    week_plans,
)
from coach.store.connection import Connection
from coach.store.rows import Row

ATHLETE_READS = 3
# The progress page reads as of the store's newest day, not the clock, so an unchanged store
# renders an unchanged page; a store recording no day reads the same on any day.
_ANY_DAY = datetime.date(2000, 1, 1)

type Json = Mapping[str, object]


def page_facts(
    conn: Connection,
    *,
    config: Config,
    kits: Sequence[KitFiles],
    profile: str | None,
) -> Pages:
    units = config.athlete.units
    bodyweight_units = config.athlete.bodyweight_units
    names = _exercise_names(conn)
    recorded = check_ins.current(conn)
    records = tuple(_record(conn, row, units, bodyweight_units) for row in recorded)
    return Pages(
        units=units,
        bodyweight_units=bodyweight_units,
        pin=config.engine.version,
        athlete=_athlete(conn, config, profile, records),
        progress=progress(
            conn,
            on=newest_day(conn, units) or _ANY_DAY,
            units=units,
            bodyweight_units=bodyweight_units,
        ),
        week=_week(conn, names),
        routines=_routines(conn, config, kits, names),
        check_ins=records,
    )


def _exercise_names(conn: Connection) -> dict[str, tuple[str, str | None]]:
    return {
        str(row["id"]): (str(row["name"]), cast(str | None, row["equipment_kind"]))
        for row in exercises.every(conn)
    }


def _line(row: Row, names: Mapping[str, tuple[str, str | None]]) -> PageLine:
    exercise_id = str(row["exercise_id"])
    name, kind = names.get(exercise_id, (exercise_id, None))
    return PageLine(
        exercise_id=exercise_id,
        name=name,
        equipment_kind=kind,
        set_groups=tuple(cast(list[Json], row["set_groups"])),
        steps=tuple(cast(list[Json], row["steps"])),
        flags=tuple(cast(list[Json], row["flags"])),
        change=str(row["change"]),
        derived_from=str(row["derived_from"]),
    )


def _sessions(conn: Connection, plan: Row | None) -> tuple[dict[str, Session], str | None]:
    """Every session as the version in force when the plan was approved names it, rehab
    sessions included, and that version's default location."""
    version = (
        programs.in_force_at(conn, str(plan["approved_at"])) if plan else programs.latest(conn)
    )
    found = {s.id: s for s in niggles.every_rehab_session(conn)}
    if version is None:
        return found, None
    found |= {s.id: s for s in version.form.sessions}
    return found, version.form.location


def _week(conn: Connection, names: Mapping[str, tuple[str, str | None]]) -> WeekPage | None:
    plan = week_plans.latest_week(conn)
    if plan is None:
        return None
    plan_id = str(plan["id"])
    sessions, _ = _sessions(conn, plan)
    by_day: dict[tuple[str, str], list[Row]] = {}
    for row in week_plans.prescriptions(conn, plan_id):
        by_day.setdefault((str(row["date"]), str(row["session_id"])), []).append(row)
    return WeekPage(
        plan_id=plan_id,
        week=str(plan["week"]),
        position=str(plan["position"]),
        approved_at=str(plan["approved_at"]),
        sessions=tuple(
            PlannedSessionPage(
                session_id=session_id,
                title=_title(sessions, session_id),
                date=datetime.date.fromisoformat(day),
                lines=tuple(_line(row, names) for row in found),
            )
            for (day, session_id), found in by_day.items()
        ),
        overrides=tuple(
            {k: row[k] for k in ("kind", "session_id", "exercise_id", "because", "text")}
            for row in week_plans.overrides(conn, plan_id)
        ),
    )


def _routines(
    conn: Connection,
    config: Config,
    kits: Sequence[KitFiles],
    names: Mapping[str, tuple[str, str | None]],
) -> tuple[RoutinePage, ...]:
    return tuple(_routine(conn, live, config, kits, names) for live in routine_map.live(conn))


def _routine(
    conn: Connection,
    live: routine_map.LiveRow,
    config: Config,
    kits: Sequence[KitFiles],
    names: Mapping[str, tuple[str, str | None]],
) -> RoutinePage:
    plan = week_plans.by_id(conn, live.plan_id) if live.plan_id else None
    sessions, default_location = _sessions(conn, plan)
    session = sessions.get(live.session_id)
    location = (session.location if session else None) or default_location
    rows = (
        [
            r
            for r in week_plans.prescriptions(conn, str(plan["id"]))
            if r["session_id"] == live.session_id
        ]
        if plan
        else []
    )
    first = min((str(r["date"]) for r in rows), default=None)
    return RoutinePage(
        session_id=live.session_id,
        title=_title(sessions, live.session_id),
        week=str(plan["week"]) if plan else None,
        location=location,
        lines=tuple(_line(r, names) for r in rows if r["date"] == first),
        kit=_kit(config, kits, location),
    )


def _kit(config: Config, kits: Sequence[KitFiles], location: str | None) -> PlatePoolKit | None:
    found = next((loc for loc in config.locations if loc.name == location), None)
    if not isinstance(found, PlatePoolLocation):
        return None
    files = next((k for k in kits if k.location == found.name), None)
    if files is None:
        return None
    rounded_to = files.tables.get("inventory_sha256") if files.tables else None
    sha = rounded_to if isinstance(rounded_to, str) else files.inventory_sha256
    return PlatePoolKit(
        location=found.name,
        collars=found.collars,
        dumbbells=found.dumbbells,
        implements=found.implements,
        short_hash=(sha or "")[:SHORT_HASH_LENGTH],
        inventory=files.inventory,
    )


def _record(
    conn: Connection, row: check_ins.StoredCheckIn, units: Units, bodyweight_units: Units
) -> CheckInRecord:
    return CheckInRecord(
        id=row.id,
        date=row.date,
        tier=row.tier,
        window=row.window,
        readiness=row.readiness,
        read=check_ins.read_of(conn, row.id),
        card=record_card(conn, row, units=units, bodyweight_units=bodyweight_units),
        decisions=tuple(_decision(d) for d in decisions.every(conn) if d["check_in"] == row.id),
    )


def _decision(row: Row) -> DecisionRead:
    return DecisionRead(
        id=str(row["id"]),
        kind=str(row["kind"]),
        because=str(row["because"]),
        text=str(row["text"]),
        until=cast(str | None, row["until"]),
        session_id=cast(str | None, row["session_id"]),
        exercise_id=cast(str | None, row["exercise_id"]),
    )


def _athlete(
    conn: Connection, config: Config, profile: str | None, records: Sequence[CheckInRecord]
) -> AthletePage:
    return AthletePage(
        profile=profile,
        athlete=config.athlete,
        locations=config.locations,
        niggles=tuple(
            NiggleRead(
                id=str(n["id"]),
                site=str(n["site"]),
                status=str(n["status"]),
                opened=str(n["opened"]),
                constraints=tuple(cast(list[Json], n["constraints"])),
            )
            for n in niggles.every(conn)
            if n["status"] != "resolved"
        ),
        follow_ups=tuple(
            FollowUpRead(str(f["id"]), str(f["text"]), cast(str | None, f["due"]))
            for f in follow_ups.every(conn)
            if f["kind"] in ("kept", "deferred")
        ),
        observations=tuple(
            str(o["text"]) for o in observations.every(conn) if o["retired_at"] is None
        ),
        decisions=tuple(_decision(d) for d in decisions.in_force(conn) if d["kind"] == "override"),
        reads=tuple((r.date, r.read) for r in records[-ATHLETE_READS:]),
    )


def _title(sessions: Mapping[str, Session], session_id: str) -> str:
    session = sessions.get(session_id)
    return session.title if session else session_id
