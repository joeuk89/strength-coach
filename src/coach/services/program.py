"""`program adopt` and `program show` (docs/spec/program.md, "Adopt")."""

import datetime
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, replace
from typing import cast

from coach.core.clock import Clock
from coach.core.closed_week.adherence import adherence
from coach.core.config import Config
from coach.core.errors import Invalid
from coach.core.exercise_ladder import LineRef
from coach.core.exposure import Exposure
from coach.core.flag import REFS, Flag, FlagKey
from coach.core.goal import Goal
from coach.core.kit import KitFiles
from coach.core.load import Load, LoadMode
from coach.core.program.checks import AdoptContext, OpenBlock, violations
from coach.core.program.defaults import fill
from coach.core.program.diff import ProgramDiff, diff
from coach.core.program.estimate import session_estimate
from coach.core.program.fold import Folded, fold_overrides
from coach.core.program.form import AcknowledgeEntry, Line, ProgramForm
from coach.core.program.parse import parse_program_draft
from coach.core.program.warnings import adopt_warnings, leave_warnings
from coach.render.program_draft import program_draft
from coach.services.cadence import cadence_signals
from coach.services.closed_weeks import ClosedWeeks, closed_weeks
from coach.services.history import read_history
from coach.services.ladders import rung_decisions, standing_rungs
from coach.services.plan_behind import plan_behind
from coach.services.racks import racks_by_location
from coach.store import exercises, goals, phases, programs, routine_map, week_plans
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
    sessions: tuple[Mapping[str, object], ...] = ()
    acknowledgements: tuple[AcknowledgeEntry, ...] = ()
    warnings: tuple[Flag, ...] = ()
    dry_run: bool = False
    no_op: bool = False


@dataclass(frozen=True)
class ShowResult:
    """`ladders` holds each `exercise_ladder` line with its session and standing rung."""

    version_id: str
    kind: str
    emphasis: str
    adopted: str
    because: str
    sessions: tuple[tuple[str, int], ...]
    ladders: tuple[tuple[str, Line, int], ...] = ()


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
    racks = racks_by_location(config, kits, draft.form.locations())
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
        phase = _open_phase_kind(conn)
        closed = closed_weeks(conn, config.athlete.units)
        filled = fill(
            draft.form,
            priority_lifts=goal.priority_lifts if goal else (),
            phase=phase,
            session_minutes=config.athlete.session_minutes,
        )
        context = AdoptContext(
            version_id=version_id,
            library=library,
            racks=racks,
            last_exposures=_last_exposures(conn, config),
            goal=goal,
            phase=phase,
            available_days=config.athlete.available_days,
            hevy_on=config.hevy is not None,
            previous=previous.form if previous else None,
            routines=routine_map.mapped(conn),
            open_block=_open_block(closed, previous),
            adherence=adherence(closed.weeks, clock.today()),
            signals={
                str(flag.scope.exercise_id): flag
                for flag in cadence_signals(
                    conn, closed, units=config.athlete.units, on=clock.today(), zone=clock.zone
                )
            },
        )
        raised = adopt_warnings(filled.form, context)
        found = violations(
            draft.form,
            replace(context, raised_warnings=frozenset(flag.key for flag in raised)),
            draft.unknown_keys,
        )
        if found:
            raise Invalid(
                found[0].code,
                f"the Draft has {len(found)} violation(s); fix each and adopt again",
                {"violations": [flag.to_json() for flag in found]},
            )
        warnings = leave_warnings(raised, draft.form.acknowledgements)
        frozen = tuple(_frozen(flag) for flag in warnings if flag.left is not None)
        today = clock.today().isoformat()
        reset = draft.form.kind == "redesign"
        result = AdoptResult(
            version_id=version_id,
            kind=draft.form.kind,
            position=start,
            block=f"b-{today}" if reset else _block_id(closed),
            block_reset=reset,
            diff=diff(previous.form if previous else None, filled.form, filled.filled),
            start_loads=_start_loads(filled.form, library, config),
            sessions=_session_estimates(filled.form),
            acknowledgements=frozen,
            warnings=warnings,
            dry_run=dry_run,
        )
        if dry_run:
            return _with_plan_behind(conn, result, clock)
        for id_, fields in draft.form.exercises.items():
            exercises.upsert_declared(conn, id_, fields)
        programs.insert_version(
            conn,
            programs.VersionRow(
                id=version_id,
                sequence=int(version_id.removeprefix("pv-")),
                position=start,
                adopted=today,
                form=replace(filled.form, acknowledgements=frozen),
                draft_hash=draft.hash,
                recorded_at=clock.now().astimezone(datetime.UTC).isoformat(timespec="seconds"),
            ),
        )
        programs.freeze_acknowledgements(conn, version_id, frozen)
    return _with_plan_behind(conn, result, clock)


def _with_plan_behind(conn: Connection, result: AdoptResult, clock: Clock) -> AdoptResult:
    behind = plan_behind(conn, clock.today(), version_id=result.version_id)
    return replace(result, warnings=(*result.warnings, *behind))


def show(conn: Connection, *, zone: datetime.tzinfo) -> ShowResult:
    version = _in_force(conn)
    standing = standing_rungs(version.form, rung_decisions(conn, zone))
    return ShowResult(
        version_id=version.id,
        kind=version.form.kind,
        emphasis=version.form.emphasis,
        adopted=version.adopted,
        because=version.form.because,
        sessions=tuple(programs.line_counts(conn, version.id)),
        ladders=tuple(
            (session.id, line, standing[LineRef(session.id, line.exercise)])
            for session in version.form.sessions
            for line in session.lines
            if line.ladder is not None
        ),
    )


@dataclass(frozen=True)
class ShownDraft:
    text: str
    folded: tuple[Folded, ...] = ()


def show_draft(conn: Connection, *, apply_plan: datetime.date | None = None) -> ShownDraft:
    """The version in force as a Draft for the next version; an acknowledgement whose scope names
    a version names the next one and keeps its params hash, so it leaves only an unchanged warning.
    With `apply_plan`, that week's approved WeekPlan's line overrides are folded in
    (overrides.md, "What `--apply-plan` folds")."""
    version = _in_force(conn)
    next_id = f"pv-{version.sequence + 1}"
    carried = tuple(_carried(entry, next_id) for entry in version.form.acknowledgements)
    form = replace(version.form, acknowledgements=carried)
    if apply_plan is None:
        return ShownDraft(program_draft(form))
    plan = week_plans.in_force(conn, apply_plan.isoformat())
    if plan is None:
        raise Invalid("state_conflict", f"the week of {apply_plan} has no approved WeekPlan")
    folded = fold_overrides(form, week_plans.stored_overrides(conn, str(plan["id"])))
    return ShownDraft(program_draft(folded.form, folded_pins=folded.pins), folded.folded)


def _carried(entry: AcknowledgeEntry, next_id: str) -> AcknowledgeEntry:
    key = FlagKey.parse(entry.flag)
    if "version_id" not in REFS[key.scope.kind]:
        return entry
    return replace(entry, flag=str(FlagKey(key.code, replace(key.scope, version_id=next_id))))


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
        raise Invalid("state_conflict", "no Program version is adopted yet; run program adopt")
    return version


def _last_exposures(conn: Connection, config: Config) -> dict[str, Exposure]:
    """Each exercise with an Exposure anywhere, resolved as `prescribe` resolves them, to its
    latest."""
    latest: dict[str, Exposure] = {}
    for exposure in read_history(conn, config.athlete.units).lifting:
        held = latest.get(exposure.exercise_id)
        if held is None or exposure.date >= held.date:
            latest[exposure.exercise_id] = exposure
    return latest


def _open_block(closed: ClosedWeeks, previous: programs.VersionRow | None) -> OpenBlock | None:
    block = closed.open_block
    if previous is None or block is None:
        return None
    return OpenBlock(block.id, block.hard_weeks)


def _block_id(closed: ClosedWeeks) -> str:
    """Every version after the first follows a redesign, so a Block is open."""
    block = closed.open_block
    assert block is not None
    return block.id


def _frozen(flag: Flag) -> AcknowledgeEntry:
    assert flag.left is not None
    return AcknowledgeEntry(flag.key, flag.left.because, flag.left.text, flag.params_hash)


def _library(conn: Connection) -> dict[str, Mapping[str, object]]:
    return {str(row["id"]): row for row in exercises.every(conn)}


def _position(form: ProgramForm, previous: programs.VersionRow | None, asked: str | None) -> str:
    rotation = form.schedule.rotation
    if form.kind == "amend":
        if asked is not None:
            raise Invalid("state_conflict", "an amend keeps the rotation position; drop --position")
        if previous is None:
            raise Invalid(
                "state_conflict", "an amend continues a Block; the first version is a redesign"
            )
        if previous.position not in rotation:
            raise Invalid(
                "state_conflict",
                f"the rotation position {previous.position!r} is not in the new rotation; "
                "keep the week or adopt a redesign",
            )
        return previous.position
    start = asked or rotation[0]
    if start not in rotation:
        raise Invalid("state_conflict", f"--position {start!r} is not a rotation week")
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


def _session_estimates(form: ProgramForm) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {
            "id": session.id,
            "minutes": session.minutes,
            "estimate": session_estimate(session),
        }
        for session in form.sessions
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
        block=_block_id(closed_weeks(conn, config.athlete.units)),
        block_reset=False,
        diff=diff(stored.form, stored.form),
        start_loads=_start_loads(stored.form, _library(conn), config),
        sessions=_session_estimates(stored.form),
        acknowledgements=programs.acknowledgements(conn, stored.id),
        dry_run=dry_run,
        no_op=True,
    )
