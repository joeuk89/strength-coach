"""`exercise_ladder` (docs/spec/program.md, "Schemes"; docs/spec/prescription.md, "The move,
per scheme"): a ladder of exercise rungs, each with the criterion for climbing off it. The
standing rung is a `ladder_rung` Decision; the engine offers the climb and never takes it
(ADR 0023)."""

import datetime
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from coach.core.exposure import Exposure, ExposureSet
from coach.core.flag import Acknowledgement, Flag, Scope, leave, raise_flag
from coach.core.line_history import newest_first, ordinary
from coach.core.prescription import DecisionInForce
from coach.core.program.form import Advance, ExerciseLadder, Line, ProgramForm, SetGroup
from coach.core.registries.schemes import DEFAULT_EXPOSURES

# The scheme's opening position; the line stands here until a rung is a recorded choice.
OPENING_RUNG = 1


@dataclass(frozen=True)
class StandingRung:
    """The rung a line stands on (from 1) and its start: the Decision's date, or the version's
    adoption for the opening rung. Only exposures on or after the start count."""

    index: int
    since: datetime.date | None


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


def ladder_of(form: ProgramForm, session_id: str, exercise_id: str) -> ExerciseLadder | None:
    """The ladder of the session's line keyed on `exercise_id`, its first rung's exercise."""
    session = form.session(session_id)
    lines = () if session is None else session.lines
    line = next((line for line in lines if line.exercise == exercise_id), None)
    return None if line is None else line.scheme.ladder


def standing_rung(
    decisions: Iterable[DecisionInForce],
    ladder: ExerciseLadder,
    *,
    session_id: str,
    line_key: str,
    adopted: datetime.date | None,
) -> StandingRung:
    """The `ladder_rung` Decision in force on the line, or the opening rung. A rung past a
    ladder an amend has since shortened stands on the top."""
    found = [
        d
        for d in decisions
        if (d.kind, d.session_id, d.exercise_id) == ("ladder_rung", session_id, line_key)
    ]
    if not found:
        return StandingRung(OPENING_RUNG, adopted)
    decision = found[-1]
    rung = decision.params["rung"]
    index = rung if isinstance(rung, int) else OPENING_RUNG
    return StandingRung(min(max(index, OPENING_RUNG), len(ladder.rungs)), decision.on)


def rung_line(line: Line, ladder: ExerciseLadder, index: int) -> Line:
    """The line as rung `index` prescribes it: the rung's exercise, sets and cues under the
    line's scheme. The line's own key stays with the caller's scope."""
    rung = ladder.rungs[index - 1]
    start_load = line.start_load if index == OPENING_RUNG else None
    return replace(
        line, exercise=rung.exercise, sets=rung.sets, cues=rung.cues, start_load=start_load
    )


def climb_offer(
    ladder: ExerciseLadder,
    standing: StandingRung,
    exposures: Iterable[Exposure],
    *,
    scope: Scope,
    on: datetime.date,
) -> Flag | None:
    """`rung_met` naming the next rung, or `ladder_top` on the last, when the newest run of
    ordinary exposures of the standing rung's exercise since its start each meet the rung's
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
    following = ladder.rungs[standing.index].exercise
    return raise_flag(
        "rung_met",
        scope,
        {
            "rung": standing.index,
            "next": following,
            "exposures": [e.ref for e in reversed(run)],
        },
        f"rung {standing.index} met its criterion on {len(run)} exposures; rung "
        f"{standing.index + 1}, {following}, is offered",
    )


@dataclass(frozen=True)
class LadderRead:
    """Where a line stands on its ladder: the standing rung, the newest run of exposures toward
    its criterion out of the `needed` (none on a `manual` rung), `met` where the climb is offered
    as `rung_met` or `ladder_top`, and `held` where an acknowledgement leaves that offer."""

    session_id: str
    line_key: str
    rung: int
    exercise: str
    rungs: int
    next: str | None
    exposures: int
    needed: int | None
    met: bool
    held: bool


def ladder_read(
    ladder: ExerciseLadder,
    standing: StandingRung,
    exposures: Iterable[Exposure],
    *,
    scope: Scope,
    before: datetime.date,
    acknowledgements: Iterable[Acknowledgement],
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
    offer = climb_offer(ladder, standing, exposures, scope=scope, on=before)
    top = standing.index == len(ladder.rungs)
    return LadderRead(
        session_id=session_id,
        line_key=str(scope.exercise_id),
        rung=standing.index,
        exercise=ladder.rungs[standing.index - 1].exercise,
        rungs=len(ladder.rungs),
        next=None if top else ladder.rungs[standing.index].exercise,
        exposures=count,
        needed=needed,
        met=offer is not None,
        held=offer is not None and leave(offer, acknowledgements).left is not None,
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
    since = standing.since
    history = ordinary(
        newest_first(
            e
            for e in exposures
            if e.exercise_id == rung.exercise
            and e.session_id in (None, session_id)
            and (since is None or since <= e.date)
            and e.date < before
        )
    )
    run: list[Exposure] = []
    for exposure in history:
        if not _meets(rung.sets, criterion, exposure):
            break
        run.append(exposure)
    return run


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
