"""Stalls (docs/spec/prescription.md, "Stalls"): three or more consecutive ordinary exposures of
a line with no gain on the scheme's metric over the first of them."""

from collections.abc import Callable, Sequence

from coach.core.e1rm import point
from coach.core.exposure import Exposure
from coach.core.program.form import Line
from coach.core.progression import judge

STREAK = 3
STREAK_RN = None

type Metric = tuple[float, ...]


def stall_streak(line: Line, history: Sequence[Exposure]) -> tuple[Exposure, ...]:
    """The longest newest run of `history` (ordinary, newest first) with no gain over its
    oldest, oldest first; empty under three or for a scheme with no metric. `wave_531` reads
    the rep-out's e1RM, since raw rep-out counts fall wave to wave by design."""
    metric = _METRICS.get(line.scheme.name)
    if metric is None:
        return ()
    values = [metric(line, exposure) for exposure in history]
    streak = max(
        (k for k in range(2, len(values) + 1) if all(v <= values[k - 1] for v in values[:k])),
        default=1,
    )
    return tuple(reversed(history[:streak])) if streak >= STREAK else ()


def _top(exposure: Exposure) -> float:
    top = exposure.top_load
    if top is None:
        return 0
    return -top.amount if top.mode == "assisted" else top.amount


def _reps_at_target(line: Line, exposure: Exposure) -> Metric:
    """Total reps at or under the authored RPE at the exposure's top load."""
    top = exposure.top_load
    authored = [g.rpe for g in line.working_groups() for _ in range(g.count)]
    reps = sum(
        logged.reps or 0
        for logged, rpe in zip(exposure.working, authored, strict=False)
        if logged.load == top and (rpe is None or logged.rpe is None or logged.rpe <= rpe)
    )
    return (_top(exposure), reps)


def _hit(line: Line, exposure: Exposure) -> Metric:
    top = exposure.top_load
    return (_top(exposure), float(judge(line, exposure, top).hit))


def _rung(_line: Line, exposure: Exposure) -> Metric:
    return (_top(exposure),)


def _best_e1rm(_line: Line, exposure: Exposure) -> Metric:
    return (max((_e1rm(exposure, i) for i in range(len(exposure.working))), default=0),)


def _rep_out_e1rm(_line: Line, exposure: Exposure) -> Metric:
    return (_e1rm(exposure, len(exposure.working) - 1) if exposure.working else 0,)


def _e1rm(exposure: Exposure, index: int) -> float:
    found = point(exposure, exposure.working[index])
    return 0 if found is None else found.load.amount


_METRICS: dict[str, Callable[[Line, Exposure], Metric]] = {
    "double_progression": _reps_at_target,
    "linear": _hit,
    "assistance_ladder": _rung,
    "top_backoff": _best_e1rm,
    "wave_531": _rep_out_e1rm,
}
