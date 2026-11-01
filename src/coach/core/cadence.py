"""Cadence signals at the block boundary, read per scheme on the scheme's own metric
(docs/spec/goals.md, "Cadence signals")."""

import datetime
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from coach.core.closed_week.adherence import WATCH_BELOW
from coach.core.e1rm import e1rm
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.line_history import newest_first, ordinary
from coach.core.linear import resets
from coach.core.load import LoadMode
from coach.core.program.form import Line
from coach.core.progression import judge
from coach.core.registries.schemes import CadenceSignal
from coach.core.stall import stall_streak
from coach.core.switching import switch_for

# The `ok` line of week.md's adherence states.
ADHERENCE_FLOOR = WATCH_BELOW
RESETS_SLOW = 2
_DAY = datetime.timedelta(days=1)

type Metric = dict[str, object]


@dataclass(frozen=True)
class BlockSpan:
    id: str
    start: datetime.date
    end: datetime.date

    def holds(self, day: datetime.date) -> bool:
        return self.start <= day <= self.end


@dataclass(frozen=True)
class CadenceRead:
    """`blocks` are the Block before and the closed one. `exposures` are the exercise's, every
    one. `adherence` is trained over planned core sessions across both Blocks' ordinary weeks.
    `capped` is, per Prescription frozen in the closed Block, whether the one-row cap bound.
    `session_id` is the line's session: per-line reads skip Exposures matched to another."""

    line: Line
    blocks: tuple[BlockSpan, BlockSpan]
    exposures: Sequence[Exposure]
    adherence: float | None
    capped: Sequence[bool] = ()
    session_id: str | None = None


def cadence_signal(read: CadenceRead) -> Flag | None:
    if read.adherence is None or read.adherence < ADHERENCE_FLOOR:
        return None
    scheme = read.line.scheme.name
    slow = _SLOW.get(scheme)
    found = slow(read) if slow else None
    if found is not None:
        return _signal("cadence_slow", read, found)
    fast = _FAST.get(scheme)
    found = fast(read) if fast else None
    if found is not None:
        return _signal("cadence_fast", read, found)
    return None


def _two_resets(read: CadenceRead) -> Metric | None:
    before, closed = read.blocks
    history = _inside(read, before.start, closed.end)
    loads = [e.top_load for e in history if e.top_load is not None]
    mode: LoadMode = loads[0].mode if loads else "total"
    found = resets(read.line, history, None, mode)
    return {"resets": len(found)} if len(found) >= RESETS_SLOW else None


def _stalled_at_both_ends(read: CadenceRead) -> Metric | None:
    before = read.blocks[0]
    first, last = (stall_streak(read.line, _inside(read, before.start, b.end)) for b in read.blocks)
    if not first or not last:
        return None
    # Oldest of the first stall against the newest two of the last: no gain across both.
    across = stall_streak(read.line, (last[-1], last[-2], first[0]))
    return {"stall_streak": len(last)} if across else None


def _flat_e1rm(read: CadenceRead) -> Metric | None:
    before, closed = read.blocks
    start = e1rm(read.exposures, read.line.exercise, before.end + _DAY)
    end = e1rm(read.exposures, read.line.exercise, closed.end + _DAY)
    if start is None or end is None or end.load.amount > start.load.amount:
        return None
    return {"e1rm_from": start.load.amount, "e1rm_to": end.load.amount}


def _every_exposure_at_top(read: CadenceRead) -> Metric | None:
    before, closed = read.blocks
    inside = _inside(read, closed.start, closed.end)
    if not inside or not all(judge(read.line, e).hit for e in inside):
        return None
    if stall_streak(read.line, _inside(read, before.start, closed.end)):
        return None
    return {"exposures_at_top": len(inside)}


def _capped_every_time(read: CadenceRead) -> Metric | None:
    if not read.capped or not all(read.capped):
        return None
    return {"capped": len(read.capped)}


_SLOW: dict[str, Callable[[CadenceRead], Metric | None]] = {
    "linear": _two_resets,
    "double_progression": _stalled_at_both_ends,
    "assistance_ladder": _stalled_at_both_ends,
    "top_backoff": _flat_e1rm,
    "wave_531": _flat_e1rm,
}
_FAST: dict[str, Callable[[CadenceRead], Metric | None]] = {
    "double_progression": _every_exposure_at_top,
    "top_backoff": _capped_every_time,
}


def _inside(read: CadenceRead, start: datetime.date, end: datetime.date) -> tuple[Exposure, ...]:
    exercise = read.line.exercise
    return ordinary(
        newest_first(
            e
            for e in read.exposures
            if e.exercise_id == exercise
            and start <= e.date <= end
            and (read.session_id is None or e.session_id in (None, read.session_id))
        )
    )


def _signal(code: CadenceSignal, read: CadenceRead, metric: Metric) -> Flag:
    scheme = read.line.scheme.name
    switch = switch_for(code, scheme)
    assert switch is not None
    exercise = read.line.exercise
    return raise_flag(
        code,
        Scope("exercise", exercise_id=exercise),
        {
            "scheme": scheme,
            "metric": metric,
            **({"blocks": [b.id for b in read.blocks]} if code == "cadence_slow" else {}),
            **switch.params(),
        },
        f"{exercise} on {scheme}: {code.replace('_', ' ')} over {_read_over(code)}; "
        f"the version may {switch.may}",
    )


def _read_over(code: CadenceSignal) -> str:
    return "the last two Blocks" if code == "cadence_slow" else "the closed Block"
