"""`program adopt` and `program show` (docs/spec/program.md, "Adopt")."""

import datetime
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import cast

from coach.core.clock import Clock
from coach.core.config import Config, PlatePoolLocation
from coach.core.errors import Invalid
from coach.core.goal import Goal
from coach.core.kit import KitFiles, location_racks, parse_kit_tables, require_current_tables
from coach.core.load import Load, LoadMode
from coach.core.program.checks import AdoptContext, violations
from coach.core.program.defaults import fill
from coach.core.program.diff import ProgramDiff, diff
from coach.core.program.form import AcknowledgeEntry, Line, ProgramForm
from coach.core.program.parse import parse_program_draft
from coach.core.rack import Rack
from coach.render.program_draft import program_draft
from coach.services.history import read_history
from coach.store import exercises, goals, phases, programs
from coach.store.connection import Connection
from coach.store.transaction import transaction

NEW_EXERCISE_COLUMNS = ("name", "load_mode", "equipment_kind", "pattern", "muscles")


@dataclass(frozen=True)
class AdoptResult:
    version_id: str
    kind: str
    position: str
    block: str
    block_reset: bool
    diff: ProgramDiff
    start_loads: tuple[Mapping[str, object], ...]
    acknowledgements: tuple[AcknowledgeEntry, ...] = ()
    dry_run: bool = False
    no_op: bool = False


@dataclass(frozen=True)
class ShowResult:
    version_id: str
    kind: str
    emphasis: str
    adopted: str
    because: str
    sessions: tuple[tuple[str, int], ...]


def adopt(
    conn: Connection,
    data: bytes,
    *,
    file: str,
    config: Config,
    kits: Sequence[KitFiles],
    clock: Clock,
    dry_run: bool = False,
    position: str | None = None,
) -> AdoptResult:
    """Validate, fill, upsert declared exercises and record the version in one transaction.
    A Draft whose hash matches the version in force writes nothing and returns that version."""
    draft = parse_program_draft(data, file=file)
    racks = _racks(config, kits, draft.form)
    writing: AbstractContextManager[None] = nullcontext() if dry_run else transaction(conn)
    with writing:
        previous = programs.latest(conn)
        if previous is not None and previous.draft_hash == draft.hash:
            return _no_op(conn, previous, config, dry_run)
        version_id = f"pv-{previous.sequence + 1 if previous else 1}"
        start = _position(draft.form, previous, position)
        goal = _current_goal(conn)
        library = _library(conn)
        _check_declared(draft.form, library)
        context = AdoptContext(
            version_id=version_id,
            library=library,
            racks=racks,
            exposed=_exposed(conn, config),
            goal=goal,
            hevy_on=config.hevy is not None,
        )
        found = violations(draft.form, context, draft.unknown_keys)
        if found:
            raise Invalid(
                found[0].code,
                f"the Draft has {len(found)} violation(s); fix each and adopt again",
                {"violations": [flag.to_json() for flag in found]},
            )
        filled = fill(
            draft.form,
            priority_lifts=goal.priority_lifts if goal else (),
            phase=_open_phase_kind(conn),
            session_minutes=config.athlete.session_minutes,
        )
        today = clock.today().isoformat()
        reset = draft.form.kind == "redesign"
        result = AdoptResult(
            version_id=version_id,
            kind=draft.form.kind,
            position=start,
            block=f"b-{today if reset else programs.block_opened(conn)}",
            block_reset=reset,
            diff=diff(previous.form if previous else None, filled.form, filled.filled),
            start_loads=_start_loads(filled.form, library, config),
            acknowledgements=filled.form.acknowledgements,
            dry_run=dry_run,
        )
        if dry_run:
            return result
        for id_, fields in draft.form.exercises.items():
            exercises.upsert_declared(conn, id_, fields)
        programs.insert_version(
            conn,
            programs.VersionRow(
                id=version_id,
                sequence=int(version_id.removeprefix("pv-")),
                position=start,
                adopted=today,
                form=filled.form,
                draft_hash=draft.hash,
                recorded_at=clock.now().astimezone(datetime.UTC).isoformat(timespec="seconds"),
            ),
        )
    return result


def show(conn: Connection) -> ShowResult:
    version = _in_force(conn)
    return ShowResult(
        version_id=version.id,
        kind=version.form.kind,
        emphasis=version.form.emphasis,
        adopted=version.adopted,
        because=version.form.because,
        sessions=tuple(programs.line_counts(conn, version.id)),
    )


def show_draft(conn: Connection) -> str:
    return program_draft(_in_force(conn).form)


def _current_goal(conn: Connection) -> Goal | None:
    goal_id = goals.current_id(conn)
    stored = goals.get(conn, goal_id) if goal_id else None
    return stored.goal if stored else None


def _open_phase_kind(conn: Connection) -> str | None:
    phase = phases.open_phase(conn)
    return phase.kind if phase else None


def _in_force(conn: Connection) -> programs.VersionRow:
    version = programs.latest(conn)
    if version is None:
        raise Invalid("invalid_argument", "no Program version is adopted yet; run program adopt")
    return version


def _racks(
    config: Config, kits: Sequence[KitFiles], form: ProgramForm
) -> dict[str, Mapping[str, Rack]]:
    """Each location's racks; a plate-pool location the Draft names must have current tables."""
    files = {kit.location: kit for kit in kits}
    named = set(form.locations())
    racks: dict[str, Mapping[str, Rack]] = {}
    for location in config.locations:
        kit = None
        if isinstance(location, PlatePoolLocation) and location.name in named:
            tables = files.get(location.name) or KitFiles(location.name, location.kit, None, None)
            require_current_tables(tables)
            assert tables.tables is not None
            kit = parse_kit_tables(
                tables.tables,
                collars=location.collars,
                dumbbells=location.dumbbells,
                units=config.athlete.units,
            )
        racks[location.name] = location_racks(location, kit)
    return racks


def _exposed(conn: Connection, config: Config) -> frozenset[str]:
    """Exercises with an Exposure anywhere, resolved as `prescribe` resolves them."""
    history = read_history(conn, config.athlete.units)
    return frozenset(exposure.exercise_id for exposure in history.exposures)


def _library(conn: Connection) -> dict[str, Mapping[str, object]]:
    return {str(row["id"]): row for row in exercises.every(conn)}


def _position(form: ProgramForm, previous: programs.VersionRow | None, asked: str | None) -> str:
    rotation = form.schedule.rotation
    if form.kind == "amend":
        if asked is not None:
            raise Invalid(
                "invalid_argument", "an amend keeps the rotation position; drop --position"
            )
        if previous is None:
            raise Invalid(
                "invalid_argument", "an amend continues a Block; the first version is a redesign"
            )
        if previous.position not in rotation:
            raise Invalid(
                "invalid_argument",
                f"the rotation position {previous.position!r} is not in the new rotation; "
                "keep the week or adopt a redesign",
            )
        return previous.position
    start = asked or rotation[0]
    if start not in rotation:
        raise Invalid("invalid_argument", f"--position {start!r} is not a rotation week")
    return start


def _check_declared(form: ProgramForm, library: Mapping[str, object]) -> None:
    for id_, fields in form.exercises.items():
        missing = [c for c in NEW_EXERCISE_COLUMNS if c not in fields]
        if id_ not in library and missing:
            raise Invalid(
                "invalid_argument",
                f"[exercise.{id_}] is new to the library and lacks {', '.join(missing)}",
            )


def _start_loads(
    form: ProgramForm, library: Mapping[str, Mapping[str, object]], config: Config
) -> tuple[Mapping[str, object], ...]:
    units = config.athlete.units
    return tuple(
        {
            "session": session.id,
            "exercise": line.exercise,
            "start_load": line.start_load,
            "units": units,
            "kg": Load(line.start_load, _load_mode(form, library, line)).hevy_kg(units),
        }
        for session in form.sessions
        for line in session.lines
        if line.start_load is not None
    )


def _load_mode(
    form: ProgramForm, library: Mapping[str, Mapping[str, object]], line: Line
) -> LoadMode:
    declared = form.exercises.get(line.exercise, {})
    mode = line.load_mode or declared.get("load_mode") or library[line.exercise]["load_mode"]
    return cast(LoadMode, mode)


def _no_op(
    conn: Connection, stored: programs.VersionRow, config: Config, dry_run: bool
) -> AdoptResult:
    return AdoptResult(
        version_id=stored.id,
        kind=stored.form.kind,
        position=stored.position,
        block=f"b-{programs.block_opened(conn)}",
        block_reset=False,
        diff=diff(stored.form, stored.form),
        start_loads=_start_loads(stored.form, _library(conn), config),
        acknowledgements=stored.form.acknowledgements,
        dry_run=dry_run,
        no_op=True,
    )
