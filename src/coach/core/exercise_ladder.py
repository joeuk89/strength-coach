"""`exercise_ladder` (docs/spec/program.md, "Schemes"; docs/spec/prescription.md, "The move,
per scheme"): a ladder of exercise rungs, each with the criterion for climbing off it. The
standing rung is a `ladder_rung` Decision; the engine offers the climb and never takes it
(ADR 0023)."""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from coach.core.exposure import Exposure, ExposureSet
from coach.core.flag import Acknowledgement, Flag, Scope, leave, raise_flag
from coach.core.frozen_prescription import frozen_groups
from coach.core.line_history import newest_first, ordinary
from coach.core.note_dose import working_rpe, working_shape
from coach.core.prescription import DecisionInForce, PrescribedGroup, RungNaming
from coach.core.program.form import (
    Advance,
    ExerciseLadder,
    Line,
    ProgramForm,
    Rung,
    SetGroup,
    group_document,
)
from coach.core.registries.schemes import DEFAULT_EXPOSURES

# The scheme's opening position; the line stands here until a rung is a recorded choice.
OPENING_RUNG = 1


@dataclass(frozen=True)
class LineRef:
    """A session's line: `line_key` is the line's own exercise, its first rung's on a ladder."""

    session_id: str
    line_key: str


@dataclass(frozen=True)
class StandingRung:
    """The rung a line stands on (from 1) and the first date an exposure counts on it."""

    index: int
    counts_from: datetime.date | None

    def counted(self, exposures: Iterable[Exposure]) -> tuple[Exposure, ...]:
        """Those of `exposures` the rung's load, criterion and `stall_streak` may read."""
        since = self.counts_from
        return tuple(e for e in exposures if since is None or since <= e.date)


def full_criterion(ladder: ExerciseLadder, index: int) -> Advance:
    """Rung `index` (from 1)'s criterion with every unsaid key filled: the working group's reps
    or duration and its RPE, over the registry's run of exposures."""
    criterion = ladder.criterion(index)
    if criterion.manual:
        return criterion
    [group] = [g for g in ladder.rungs[index - 1].sets if g.working]
    top = group.reps[1] if isinstance(group.reps, tuple) else group.reps
    if isinstance(top, str):
        top = int(top.rstrip("+"))
    filled = Advance(
        reps=top if group.duration_s is None else None,
        duration_s=group.duration_s,
        rpe_at_most=group.rpe,
        exposures=DEFAULT_EXPOSURES,
    )
    return replace(filled, **criterion.stated())


@dataclass(frozen=True)
class RungShape:
    """One rung of a line's ladder as the version authors it; `criterion` is in full."""

    rung: int
    exercise: str
    label: str
    cues: str | None
    set_groups: tuple[Mapping[str, object], ...]
    criterion: Mapping[str, object]
    standing: bool


def rung_shapes(
    line: Line, ladder: ExerciseLadder, standing: int, *, naming: RungNaming
) -> tuple[RungShape, ...]:
    return tuple(
        RungShape(
            rung=index,
            exercise=rung.exercise,
            label=rung_label(line, ladder, index, standing=standing, naming=naming),
            cues=rung.cues,
            set_groups=tuple(group_document(group) for group in rung.sets),
            criterion=full_criterion(ladder, index).stated(),
            standing=index == standing,
        )
        for index, rung in enumerate(ladder.rungs, start=1)
    )


def ladder_of(form: ProgramForm, session_id: str, exercise_id: str) -> ExerciseLadder | None:
    """The ladder of the session's line keyed on `exercise_id`, its first rung's exercise."""
    session = form.session(session_id)
    lines = () if session is None else session.lines
    line = next((line for line in lines if line.exercise == exercise_id), None)
    return None if line is None else line.ladder


def standing_rung(
    decisions: Iterable[DecisionInForce],
    ladder: ExerciseLadder,
    *,
    line: LineRef,
    adopted: datetime.date | None,
) -> StandingRung:
    """The `ladder_rung` Decision in force on the line, or the opening rung. A rung past a
    ladder an amend has since shortened stands on the top. Exposures count from the day after
    the Decision, since neither carries a time and the workout that earned the climb is often
    logged that day; the opening rung counts from adoption itself, since no rung earned it."""
    found = [
        d
        for d in decisions
        if (d.kind, d.session_id, d.exercise_id) == ("ladder_rung", line.session_id, line.line_key)
    ]
    if not found:
        return StandingRung(OPENING_RUNG, adopted)
    decision = found[-1]
    rung = decision.params["rung"]
    index = rung if isinstance(rung, int) else OPENING_RUNG
    return StandingRung(
        min(max(index, OPENING_RUNG), len(ladder.rungs)),
        None if decision.on is None else decision.on + datetime.timedelta(days=1),
    )


def rung_line(line: Line, ladder: ExerciseLadder, index: int) -> Line:
    """The line as rung `index` prescribes it: the rung's exercise, sets and cues under the
    line's scheme. The line's `start_load` and `load_mode` are the first rung's; a later rung
    has its own load in its own exercise's mode. The line's own key stays with the caller's
    scope."""
    rung = ladder.rungs[index - 1]
    shaped = replace(line, exercise=rung.exercise, sets=rung.sets, cues=rung.cues)
    if index == OPENING_RUNG:
        return shaped
    return replace(shaped, start_load=rung.start_load, load_mode=None)


def rung_label(
    line: Line, ladder: ExerciseLadder, index: int, *, standing: int, naming: RungNaming
) -> str:
    """`rung <n> · [<exercise name> · ]<dose>[ · <load>][ · <cues>]`: the name only when the
    rung's exercise differs from the standing rung's, and an empty segment left out."""
    rung = ladder.rungs[index - 1]
    named = rung.exercise != ladder.rungs[standing - 1].exercise
    load = rung_line(line, ladder, index).start_load
    segments = (
        f"rung {index}",
        naming.name(rung.exercise) if named else None,
        _rung_dose(rung, naming),
        None if load is None else f"{load:g} {naming.units}",
        rung.cues,
    )
    return " · ".join(s for s in segments if s)


def _rung_dose(rung: Rung, naming: RungNaming) -> str:
    working = frozen_groups(
        [
            PrescribedGroup(g.type, g.count, reps=g.reps, duration_s=g.duration_s, rpe=g.rpe)
            for g in rung.sets
            if g.working
        ],
        naming.units,
    )
    return working_shape(working) + working_rpe(working)


def rung_anchors(
    exposures: Iterable[Exposure], standing: StandingRung, week: int, session_id: str
) -> tuple[Exposure, ...]:
    """What may anchor a later rung carrying its own start load this `week`. A rung a return band
    stepped back to has none: the standing rung's start says nothing of that rung's history."""
    if week != standing.index:
        return ()
    return _counted_in_session(exposures, standing, session_id)


def climb_offer(
    line: Line,
    ladder: ExerciseLadder,
    standing: StandingRung,
    exposures: Iterable[Exposure],
    *,
    scope: Scope,
    on: datetime.date,
    naming: RungNaming,
) -> Flag | None:
    """`rung_met` offering the next rung by its label, or `ladder_top` on the last, when the newest
    run of ordinary exposures of the standing rung's exercise since its start each meet the rung's
    criterion. A `manual` rung waits for the athlete's word."""
    needed = _needed(ladder, standing.index)
    if needed is None:
        return None
    run = _qualifying_run(ladder, standing, exposures, str(scope.session_id), on)[:needed]
    if len(run) < needed:
        return None
    if standing.index == len(ladder.rungs):
        return raise_flag(
            "ladder_top",
            scope,
            {"rung": standing.index},
            f"rung {standing.index}, the ladder's top, met its criterion on {len(run)} exposures; "
            "the version may hold it or move the line on",
        )
    next_rung = standing.index + 1
    label = rung_label(line, ladder, next_rung, standing=standing.index, naming=naming)
    return raise_flag(
        "rung_met",
        scope,
        {
            "rung": standing.index,
            "next": ladder.rungs[standing.index].exercise,
            "next_rung": next_rung,
            "exposures": [e.ref for e in reversed(run)],
        },
        f"rung {standing.index} met its criterion on {len(run)} exposures; {label} is offered",
    )


@dataclass(frozen=True)
class LadderRead:
    """Where a line stands on its ladder: the standing rung, the newest run of exposures toward
    its criterion out of the `needed` (none on a `manual` rung), `met` where the climb is offered
    as `rung_met` or `ladder_top`, `held` where an acknowledgement leaves that offer, and every
    rung's label in rung order."""

    line: LineRef
    rung: int
    exercise: str
    rungs: int
    next: str | None
    exposures: int
    needed: int | None
    met: bool
    held: bool
    labels: tuple[str, ...]

    @property
    def label(self) -> str:
        return self.labels[self.rung - 1]

    @property
    def next_label(self) -> str | None:
        return None if self.next is None else self.labels[self.rung]


def ladder_read(
    line: Line,
    ladder: ExerciseLadder,
    standing: StandingRung,
    exposures: Sequence[Exposure],
    *,
    scope: Scope,
    before: datetime.date,
    acknowledgements: Iterable[Acknowledgement],
    naming: RungNaming,
) -> LadderRead:
    """The line's ladder as the exposures logged before `before` leave it, on the line `scope`
    names. The climb offer goes through `leave`, as every flag on the approval prompt does."""
    session_id = str(scope.session_id)
    needed = _needed(ladder, standing.index)
    count = (
        0
        if needed is None
        else min(len(_qualifying_run(ladder, standing, exposures, session_id, before)), needed)
    )
    offer = climb_offer(line, ladder, standing, exposures, scope=scope, on=before, naming=naming)
    top = standing.index == len(ladder.rungs)
    return LadderRead(
        line=LineRef(session_id, str(scope.exercise_id)),
        rung=standing.index,
        exercise=ladder.rungs[standing.index - 1].exercise,
        rungs=len(ladder.rungs),
        next=None if top else ladder.rungs[standing.index].exercise,
        exposures=count,
        needed=needed,
        met=offer is not None,
        held=offer is not None and leave(offer, acknowledgements).left is not None,
        labels=tuple(
            rung_label(line, ladder, index, standing=standing.index, naming=naming)
            for index in range(OPENING_RUNG, len(ladder.rungs) + 1)
        ),
    )


def _needed(ladder: ExerciseLadder, index: int) -> int | None:
    """The exposures rung `index` needs toward its criterion; none on a `manual` rung."""
    criterion = full_criterion(ladder, index)
    return None if criterion.manual else criterion.exposures or DEFAULT_EXPOSURES


def _qualifying_run(
    ladder: ExerciseLadder,
    standing: StandingRung,
    exposures: Iterable[Exposure],
    session_id: str,
    before: datetime.date,
) -> Sequence[Exposure]:
    """The newest ordinary exposures of the standing rung's exercise since its start, newest
    first, up to the first that misses the rung's criterion."""
    criterion = full_criterion(ladder, standing.index)
    rung = ladder.rungs[standing.index - 1]
    history = ordinary(
        newest_first(
            e
            for e in _counted_in_session(exposures, standing, session_id)
            if e.exercise_id == rung.exercise and e.date < before
        )
    )
    run: list[Exposure] = []
    for exposure in history:
        if not _meets(rung.sets, criterion, exposure):
            break
        run.append(exposure)
    return run


def _counted_in_session(
    exposures: Iterable[Exposure], standing: StandingRung, session_id: str
) -> tuple[Exposure, ...]:
    return standing.counted(e for e in exposures if e.session_id in (None, session_id))


def _meets(sets: Sequence[SetGroup], criterion: Advance, exposure: Exposure) -> bool:
    """Every authored working set logged at the criterion's reps or duration at or under its
    RPE; a set with no RPE counts as on target."""
    count = sum(group.count for group in sets if group.working)
    logged = exposure.working[:count]
    return len(logged) == count and all(_on_target(s, criterion) for s in logged)


def _on_target(logged: ExposureSet, criterion: Advance) -> bool:
    if criterion.duration_s is not None:
        reached = (logged.duration_s or 0) >= criterion.duration_s
    else:
        reached = (logged.reps or 0) >= (criterion.reps or 0)
    ceiling = criterion.rpe_at_most
    return reached and (ceiling is None or logged.rpe is None or logged.rpe <= ceiling)
