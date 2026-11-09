"""The values every rendered page is drawn from, read from the store as it stands (ADR 0012)."""

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

from coach.core.closed_week.match import PlannedRef
from coach.core.config import Config, PlatePoolLocation, Units
from coach.core.exercise_ladder import OPENING_RUNG, LineRef, RungShape, rung_shapes
from coach.core.kit import SHORT_HASH_LENGTH, KitFiles, parse_kit_tables
from coach.core.pages import (
    AthletePage,
    CheckInRecord,
    DecisionRead,
    FollowUpRead,
    NiggleRead,
    PageLine,
    PageNames,
    Pages,
    PlannedSessionPage,
    PlatePoolKit,
    RoutinePage,
    WeekPage,
)
from coach.core.program.form import Session
from coach.core.rack import ListedRack
from coach.services.checkin_open import record_card
from coach.services.closed_weeks import planned_week
from coach.services.ladders import rung_decisions, standing_rungs
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
from coach.store.programs import VersionRow
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
    zone: datetime.tzinfo,
) -> Pages:
    units = config.athlete.units
    bodyweight_units = config.athlete.bodyweight_units
    names = _exercise_names(conn)
    every_decision = decisions.every(conn)
    records = tuple(
        _record(conn, row, every_decision, units, bodyweight_units, zone)
        for row in check_ins.current(conn)
    )
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
            zone=zone,
        ),
        names=PageNames(
            sessions={s.id: s.title for s in _authored(conn, programs.latest(conn)).values()},
            exercises={id_: name for id_, (name, _) in names.items()},
        ),
        week=_week(conn, names),
        routines=_routines(conn, config, kits, names, zone),
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


def _version_of(conn: Connection, plan: Row | None) -> VersionRow | None:
    return programs.in_force_at(conn, str(plan["approved_at"])) if plan else programs.latest(conn)


def _authored(conn: Connection, version: VersionRow | None) -> dict[str, Session]:
    """Every session as the version names it, rehab sessions included."""
    found = {s.id: s for s in niggles.every_rehab_session(conn)}
    if version is not None:
        found |= {s.id: s for s in version.form.sessions}
    return found


def _week(conn: Connection, names: Mapping[str, tuple[str, str | None]]) -> WeekPage | None:
    plan = week_plans.latest_week(conn)
    if plan is None:
        return None
    plan_id = str(plan["id"])
    week = planned_week(conn, plan, niggles.rehab_histories(conn))
    authored = _authored(conn, week.version)
    frozen: dict[PlannedRef, list[Row]] = {}
    for row in week_plans.prescriptions(conn, plan_id):
        frozen.setdefault((_day(row), str(row["session_id"])), []).append(row)
    derived = tuple(
        _session_page(
            s.session_id, s.date, s.kind, frozen.get((s.date, s.session_id), ()), authored, names
        )
        for s in week.kept
    )
    planned = week.refs()
    orphans = tuple(
        _session_page(
            session_id, day, _kind(authored, session_id), rows, authored, names, derived=False
        )
        for (day, session_id), rows in frozen.items()
        if (day, session_id) not in planned
    )
    return WeekPage(
        plan_id=plan_id,
        week=str(plan["week"]),
        position=str(plan["position"]),
        approved_at=str(plan["approved_at"]),
        sessions=derived + orphans,
        overrides=tuple(
            {k: row[k] for k in ("kind", "session_id", "exercise_id", "because", "text")}
            for row in week_plans.overrides(conn, plan_id)
        ),
    )


def _session_page(
    session_id: str,
    day: datetime.date,
    kind: str,
    rows: Sequence[Row],
    authored: Mapping[str, Session],
    names: Mapping[str, tuple[str, str | None]],
    *,
    derived: bool = True,
) -> PlannedSessionPage:
    session = authored.get(session_id)
    return PlannedSessionPage(
        session_id=session_id,
        title=_title(authored, session_id),
        date=day,
        kind=kind,
        lines=tuple(_line(row, names) for row in rows),
        estimated_sets=session.estimated_sets if session and not rows else None,
        derived=derived,
    )


def _kind(authored: Mapping[str, Session], session_id: str) -> str:
    """A frozen row's session is no longer authored when its version is gone: it was a
    prescribed line, so it reads as lifting."""
    session = authored.get(session_id)
    return session.kind if session else "lifting"


def _day(row: Row) -> datetime.date:
    return datetime.date.fromisoformat(str(row["date"]))


def _routines(
    conn: Connection,
    config: Config,
    kits: Sequence[KitFiles],
    names: Mapping[str, tuple[str, str | None]],
    zone: datetime.tzinfo,
) -> tuple[RoutinePage, ...]:
    return tuple(_routine(conn, live, config, kits, names, zone) for live in routine_map.live(conn))


def _routine(
    conn: Connection,
    live: routine_map.LiveRow,
    config: Config,
    kits: Sequence[KitFiles],
    names: Mapping[str, tuple[str, str | None]],
    zone: datetime.tzinfo,
) -> RoutinePage:
    plan = week_plans.by_id(conn, live.plan_id) if live.plan_id else None
    version = _version_of(conn, plan)
    sessions = _authored(conn, version)
    session = sessions.get(live.session_id)
    location = (session.location if session else None) or (
        version.form.location if version else None
    )
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
    standing = standing_rungs(version.form, rung_decisions(conn, zone)) if version else {}
    ladders = _ladders(session, names, standing) if session else {}
    return RoutinePage(
        session_id=live.session_id,
        title=_title(sessions, live.session_id),
        week=str(plan["week"]) if plan else None,
        location=location,
        lines=tuple(
            replace(line, ladder=ladders.get(line.exercise_id, ()))
            for line in (_line(r, names) for r in rows if r["date"] == first)
        ),
        kit=_kit(config, kits, location),
    )


def _ladders(
    session: Session,
    names: Mapping[str, tuple[str, str | None]],
    standing: Mapping[LineRef, int],
) -> dict[str, tuple[RungShape, ...]]:
    """Each `exercise_ladder` line's rungs, keyed on every rung's exercise, since the frozen
    row names the rung the week prescribed."""
    found: dict[str, tuple[RungShape, ...]] = {}
    for line in session.lines:
        ladder = line.ladder
        if ladder is None:
            continue
        rungs = rung_shapes(
            ladder,
            standing.get(LineRef(session.id, line.exercise), OPENING_RUNG),
            name_of=lambda exercise: names.get(exercise, (exercise, None))[0],
        )
        found |= dict.fromkeys(line.rung_exercises, rungs)
    return found


def _kit(config: Config, kits: Sequence[KitFiles], location: str | None) -> PlatePoolKit | None:
    found = next((loc for loc in config.locations if loc.name == location), None)
    if not isinstance(found, PlatePoolLocation):
        return None
    files = next((k for k in kits if k.location == found.name), None)
    if files is None:
        return None
    rounded_to = files.tables.get("inventory_sha256") if files.tables else None
    sha = rounded_to if isinstance(rounded_to, str) else files.inventory_sha256
    listed = {
        name: choice
        for name, choice in found.choices().items()
        if isinstance(choice.hardware, tuple)
    }
    racks: Mapping[str, ListedRack] = {}
    if listed and files.tables is not None:
        racks = parse_kit_tables(files.tables, choices=listed, units=config.athlete.units).racks
    return PlatePoolKit(
        location=found.name,
        implements=found.implements,
        implement=found.implement,
        short_hash=(sha or "")[:SHORT_HASH_LENGTH],
        inventory=files.inventory,
        racks=racks,
    )


def _record(
    conn: Connection,
    row: check_ins.StoredCheckIn,
    every_decision: Sequence[Row],
    units: Units,
    bodyweight_units: Units,
    zone: datetime.tzinfo,
) -> CheckInRecord:
    return CheckInRecord(
        id=row.id,
        date=row.date,
        tier=row.tier,
        window=row.window,
        readiness=row.readiness,
        read=check_ins.read_of(conn, row.id),
        card=record_card(conn, row, units=units, bodyweight_units=bodyweight_units, zone=zone),
        decisions=tuple(_decision(d) for d in every_decision if d["check_in"] == row.id),
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
