"""Stalls (docs/spec/prescription.md, "Stalls"): three or more consecutive ordinary exposures of
a line with no gain on the scheme's metric."""

from collections.abc import Callable, Sequence

from coach.core.e1rm import point
from coach.core.exposure import Exposure
from coach.core.linear import missed
from coach.core.program.form import Line

STREAK = 3
STREAK_RN = None

type Metric = Callable[[Line, Exposure], float]
type Run = Callable[[Line, Sequence[Exposure]], int]


def stall_streak(line: Line, history: Sequence[Exposure]) -> tuple[Exposure, ...]:
    """The newest run of `history` (ordinary, newest first) with no gain, oldest first; empty
    under three or for a scheme with no metric."""
    run = _RUNS.get(line.scheme.name)
    if run is None:
        return ()
    length = run(line, history)
    return tuple(reversed(history[:length])) if length >= STREAK else ()


def _no_gain(metric: Metric) -> Run:
    """The longest newest run whose values never exceed its oldest."""

    def run(line: Line, history: Sequence[Exposure]) -> int:
        values = [metric(line, exposure) for exposure in history]
        return max(
            (k for k in range(1, len(values) + 1) if all(v <= values[k - 1] for v in values[:k])),
            default=0,
        )

    return run


def _at_one_load(metric: Metric) -> Run:
    """A deliberate move to another load starts a new run rather than reading as no gain."""
    no_gain = _no_gain(metric)

    def run(line: Line, history: Sequence[Exposure]) -> int:
        length = next(
            (i for i, e in enumerate(history) if e.top_load != history[0].top_load), len(history)
        )
        return no_gain(line, history[:length])

    return run


def _misses(line: Line, history: Sequence[Exposure]) -> int:
    return next((i for i, e in enumerate(history) if not _missed(line, e)), len(history))


def _missed(line: Line, exposure: Exposure) -> bool:
    top = exposure.top_load
    return top is not None and missed(line, exposure, top)


def _reps_at_target(line: Line, exposure: Exposure) -> float:
    """Total reps at or under the authored RPE at the exposure's top load."""
    top = exposure.top_load
    authored = [g.rpe for g in line.working_groups() for _ in range(g.count)]
    return sum(
        logged.reps or 0
        for logged, rpe in zip(exposure.working, authored, strict=False)
        if logged.load == top and (rpe is None or logged.rpe is None or logged.rpe <= rpe)
    )


def _same(_line: Line, _exposure: Exposure) -> float:
    return 0


def _best_e1rm(_line: Line, exposure: Exposure) -> float:
    return max((_e1rm(exposure, i) for i in range(len(exposure.working))), default=0)


def _rep_out_e1rm(_line: Line, exposure: Exposure) -> float:
    """Raw rep-out counts fall wave to wave by design, so the rep-out reads as an e1RM."""
    return _e1rm(exposure, len(exposure.working) - 1) if exposure.working else 0


def _e1rm(exposure: Exposure, index: int) -> float:
    found = point(exposure, exposure.working[index])
    return 0 if found is None else found.load.amount


_RUNS: dict[str, Run] = {
    "double_progression": _at_one_load(_reps_at_target),
    "linear": _misses,
    "assistance_ladder": _at_one_load(_same),
    "top_backoff": _no_gain(_best_e1rm),
    "wave_531": _no_gain(_rep_out_e1rm),
}
