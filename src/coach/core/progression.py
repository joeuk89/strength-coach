"""The hit test each scheme runs on its anchor (docs/spec/prescription.md, "The move, per
scheme"). It reads the version's authored groups, never a past plan."""

from dataclasses import dataclass

from coach.core.exposure import Exposure, ExposureSet
from coach.core.load import Load
from coach.core.program.form import Line, Number, Reps

RPE_OVER = 2


@dataclass(frozen=True)
class Missed:
    """The first working set over the line: RPE two or more above the authored, or below the
    bottom of the range."""

    set_index: int
    reps: int
    range: tuple[int, int]
    logged_rpe: float | None
    authored_rpe: Number | None


@dataclass(frozen=True)
class Verdict:
    hit: bool
    missed: Missed | None = None
    incomplete: bool = False


HOLD = Verdict(hit=False)
INCOMPLETE = Verdict(hit=False, incomplete=True)


def judge(line: Line, anchor: Exposure, load: Load | None = None) -> Verdict:
    """`load` is the anchor load the line moves from; a working set logged lighter than it is
    not at the anchor load, so it reaches no target."""
    authored = [
        (group.reps, group.rpe) for group in line.working_groups() for _ in range(group.count)
    ]
    logged = anchor.working[: len(authored)]
    # Fewer working sets logged than authored is not a hit and raises nothing.
    if len(logged) < len(authored) or any(s.reps is None for s in logged):
        return INCOMPLETE
    pairs = list(zip(authored, logged, strict=True))
    at_load = all(_at_load(s, load) for s in logged)
    match line.scheme.name:
        case "double_progression":
            return _double_progression(pairs, at_load)
        case "linear":
            return Verdict(at_load and _all_reached(pairs))
        case "assistance_ladder":
            return _assistance_ladder(pairs, at_load)
        case _:
            return HOLD


type Pair = tuple[tuple[Reps | None, Number | None], ExposureSet]


def _double_progression(pairs: list[Pair], at_load: bool) -> Verdict:
    for index, ((reps, rpe), logged) in enumerate(pairs, start=1):
        assert logged.reps is not None
        low, high = _range(reps)
        over = rpe is not None and logged.rpe is not None and logged.rpe >= rpe + RPE_OVER
        if over or logged.reps < low:
            return Verdict(False, Missed(index, logged.reps, (low, high), logged.rpe, rpe))
    return Verdict(at_load and _all_reached(pairs))


def _assistance_ladder(pairs: list[Pair], at_load: bool) -> Verdict:
    for index, ((reps, rpe), logged) in enumerate(pairs, start=1):
        assert logged.reps is not None
        if rpe is not None and logged.rpe is not None and logged.rpe >= rpe + RPE_OVER:
            return Verdict(False, Missed(index, logged.reps, _range(reps), logged.rpe, rpe))
    return Verdict(at_load and _all_reached(pairs))


def _all_reached(pairs: list[Pair]) -> bool:
    return all(_reached(logged, reps, rpe) for (reps, rpe), logged in pairs)


def _at_load(logged: ExposureSet, load: Load | None) -> bool:
    if load is None:
        return True
    if logged.load is None:
        return False
    amount = logged.load.as_mode(load.mode).amount
    if load.mode == "assisted":
        return amount <= load.amount
    return amount >= load.amount


def _reached(logged: ExposureSet, reps: Reps | None, rpe: Number | None) -> bool:
    """At the top of the authored reps at or under the authored RPE; a set with no RPE counts
    as on target."""
    on_target = rpe is None or logged.rpe is None or logged.rpe <= rpe
    return (logged.reps or 0) >= _top(reps) and on_target


def _range(reps: Reps | None) -> tuple[int, int]:
    if isinstance(reps, tuple):
        return reps
    top = _top(reps)
    return top, top


def _top(reps: Reps | None) -> int:
    if isinstance(reps, tuple):
        return reps[1]
    if isinstance(reps, str):
        return int(reps.rstrip("+"))
    return reps or 0
