import json
from collections.abc import Iterable
from dataclasses import dataclass

from coach.core.clock import Clock
from coach.core.config import Units
from coach.core.flag import Flag
from coach.core.import_flags import (
    exercise_unmapped,
    routine_drift,
    workout_reappeared,
)
from coach.core.instant import utc_instant
from coach.core.mirror import BodyMeasurement, engine_folders, mirrored_routine
from coach.core.routine_projection import routine_diff
from coach.core.workout_import import Changes, event_pull_changes, event_since, full_pull_changes
from coach.hevy.parse import parse_routine
from coach.hevy.protocol import HevyClient
from coach.services.projections import folder_role, projection, session_facts
from coach.store import mirrors, routine_map, week_plans
from coach.store.connection import Connection
from coach.store.import_runs import last_import_at, record_import_run
from coach.store.mirrors import upsert_folder, upsert_routine
from coach.store.weigh_ins import enter_weigh_in, live_weigh_ins, withdraw_weigh_in
from coach.store.workouts import (
    append_tombstones,
    append_version,
    current_workouts,
    hevy_presence,
    mapped_template_ids,
    reappeared,
)


@dataclass(frozen=True)
class WorkoutCounts:
    new: int
    versioned: int
    gone: int
    back: int


@dataclass(frozen=True)
class ImportResult:
    kind: str
    since: str | None
    at: str
    workouts: WorkoutCounts
    weigh_ins: int
    routines: int
    folders: int
    warnings: tuple[Flag, ...]


def import_hevy(
    conn: Connection, client: HevyClient, clock: Clock, *, full: bool, units: Units
) -> ImportResult:
    """Pull Hevy append-only into the store (ADR 0011, "Import"). Every GET runs before the one
    write transaction, so an unreachable Hevy leaves the store as it was."""
    now = clock.now()
    zone = clock.zone
    last = last_import_at(conn)
    stored = hevy_presence(conn)
    kind, since = ("full", None) if full or last is None else ("event", event_since(last))
    if since is None:
        changes = full_pull_changes(stored, client.workouts(), now, zone)
    else:
        changes = event_pull_changes(stored, client.workout_events(since), now, zone)
    pulled_routines = client.routines()
    pulled_folders = engine_folders(client.folders())
    measurements = client.body_measurements()
    at = utc_instant(now)
    since_text = utc_instant(since) if since else None
    with conn:
        for version in changes.versions:
            append_version(conn, version, at)
        append_tombstones(conn, changes.tombstones)
        entered, withdrawn = _weigh_ins(conn, measurements, at)
        routine_rows = sum(upsert_routine(conn, mirrored_routine(r), at) for r in pulled_routines)
        folder_rows = sum(upsert_folder(conn, f) for f in pulled_folders)
        routine_map.flip_missing(conn, {r.id for r in pulled_routines})
        summary = {
            **_log_summary(changes),
            "weigh_in": entered + withdrawn,
            "routine": routine_rows,
            "folder": folder_rows,
        }
        record_import_run(conn, at=at, since=since_text, kind=kind, summary=summary)
    return ImportResult(
        kind=kind,
        since=since_text,
        at=at,
        workouts=WorkoutCounts(
            changes.new, changes.versioned, changes.count("gone"), changes.count("back")
        ),
        weigh_ins=entered,
        routines=routine_rows,
        folders=folder_rows,
        warnings=standing_warnings(conn, units),
    )


def standing_warnings(conn: Connection, units: Units) -> tuple[Flag, ...]:
    """The import warnings that stand on the store as it is now (validation.md)."""
    returned = tuple(workout_reappeared(*row) for row in reappeared(conn))
    unmapped = exercise_unmapped(current_workouts(conn), mapped_template_ids(conn))
    return returned + unmapped + _drift(conn, units)


def _drift(conn: Connection, units: Units) -> tuple[Flag, ...]:
    """Each live mapped routine against the projection of the WeekPlan that wrote it: the
    mirror is what Hevy returned at the last import or read-back (ADR 0011, "Import")."""
    live = {r.hevy_id: r for r in mirrors.routines(conn)}
    # With no engine folder mirrored for the role, `plan apply` refuses or creates it first.
    roles = {f.role for f in mirrors.folders(conn)}
    flags: list[Flag] = []
    for row in routine_map.written(conn):
        mirrored = live.get(row.routine_id)
        if mirrored is None:
            continue
        plan = week_plans.by_id(conn, row.plan_id)
        session = session_facts(conn, plan).get(row.session_id)
        if (
            session is None
            or folder_role(session) not in roles
            or not _froze(conn, row.plan_id, row.session_id)
        ):
            continue
        body = projection(conn, plan, row.session_id, session, units)
        diff = routine_diff(body, parse_routine({"routine": json.loads(mirrored.raw)}))
        if diff:
            flags.append(routine_drift(row.routine_id, row.plan_id, diff))
    return tuple(flags)


def _froze(conn: Connection, plan_id: str, session_id: str) -> bool:
    """A routine its plan retired froze no line to project; its map row can stay live when
    the retire read back differently."""
    return any(r["session_id"] == session_id for r in week_plans.prescriptions(conn, plan_id))


def _weigh_ins(
    conn: Connection, measurements: Iterable[BodyMeasurement], at: str
) -> tuple[int, int]:
    """Enter each measured weight Hevy holds once; a changed one withdraws the old reading.
    Returns the readings entered and withdrawn."""
    live = {w.date: w for w in live_weigh_ins(conn, "hevy")}
    measured = {m.date: m.weight_kg for m in measurements if m.weight_kg is not None}
    entered = withdrawn = 0
    for date, kg in sorted(measured.items()):
        known = live.get(date)
        if known is not None and known.kg == kg:
            continue
        if known is not None:
            withdraw_weigh_in(conn, known, at)
            withdrawn += 1
        enter_weigh_in(conn, date, kg, "hevy", at)
        entered += 1
    return entered, withdrawn


def _log_summary(changes: Changes) -> dict[str, int]:
    return {
        "workout": len(changes.versions),
        "logged_set": sum(len(v.sets) for v in changes.versions),
        "tombstone": len(changes.tombstones),
    }
