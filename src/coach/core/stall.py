"""Stalls (docs/spec/prescription.md, "Stalls"): three consecutive ordinary exposures of a line
with no gain on the scheme's metric."""

from collections.abc import Callable, Sequence

from coach.core.e1rm import point
from coach.core.exposure import Exposure
from coach.core.linear import missed
from coach.core.program.form import Line

STREAK = 3

type Metric = Callable[[Line, Exposure], tuple[float, ...]]


def judged(session_kind: str) -> bool:
    """A practice is never judged: no line in one raises a stall or a slow cadence."""
    return session_kind != "practice"


def stall_streak(line: Line, history: Sequence[Exposure]) -> tuple[Exposure, ...]:
    """The newest three of `history` (ordinary, newest first), oldest first, when neither later
    one gains on the first; empty otherwise or for a scheme with no metric."""
    if len(history) < STREAK:
        return ()
    streak = tuple(reversed(history[:STREAK]))
    if line.scheme.name == "linear":
        return streak if all(_missed(line, e) for e in streak) else ()
    metric = _METRICS.get(line.scheme.name)
    if metric is None:
        return ()
    first, *later = (metric(line, exposure) for exposure in streak)
    return streak if max(later) <= first else ()


def _missed(line: Line, exposure: Exposure) -> bool:
    top = exposure.top_load
    return top is not None and missed(line, exposure, top)


def _reps_at_target(line: Line, exposure: Exposure) -> tuple[float, ...]:
    """The top load, then the total reps at or under the authored RPE at it: a heavier load is a
    gain whatever the reps."""
    top = exposure.top_load
    if top is None:
        return (0, 0)
    authored = [g.rpe for g in line.working_groups() for _ in range(g.count)]
    reps = sum(
        logged.reps or 0
        for logged, rpe in zip(exposure.working, authored, strict=False)
        if logged.load == top and (rpe is None or logged.rpe is None or logged.rpe <= rpe)
    )
    return (top.amount, reps)


def _dose_at_target(line: Line, exposure: Exposure) -> tuple[float, ...]:
    """Total reps, or seconds on a duration rung, at or under the authored RPE."""
    authored = [g for g in line.working_groups() for _ in range(g.count)]
    return (
        sum(
            (logged.duration_s if group.duration_s is not None else logged.reps) or 0
            for logged, group in zip(exposure.working, authored, strict=False)
            if group.rpe is None or logged.rpe is None or logged.rpe <= group.rpe
        ),
    )


def _rung(_line: Line, exposure: Exposure) -> tuple[float, ...]:
    top = exposure.top_load
    return (0,) if top is None else (-top.amount,)


def _best_e1rm(_line: Line, exposure: Exposure) -> tuple[float, ...]:
    return (max((_e1rm(exposure, i) for i in range(len(exposure.working))), default=0),)


def _rep_out_e1rm(_line: Line, exposure: Exposure) -> tuple[float, ...]:
    """Raw rep-out counts fall wave to wave by design, so the rep-out is read as its e1RM."""
    return (_e1rm(exposure, len(exposure.working) - 1) if exposure.working else 0,)


def _e1rm(exposure: Exposure, index: int) -> float:
    found = point(exposure, exposure.working[index])
    return 0 if found is None else found.load.amount


_METRICS: dict[str, Metric] = {
    "double_progression": _reps_at_target,
    "assistance_ladder": _rung,
    "exercise_ladder": _dose_at_target,
    "top_backoff": _best_e1rm,
    "wave_531": _rep_out_e1rm,
}
