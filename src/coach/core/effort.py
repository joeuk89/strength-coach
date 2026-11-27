"""A load-bearing line held at one load with no effort reading (docs/spec/prescription.md, "A
load held unread")."""

from collections.abc import Sequence

from coach.core.exposure import Exposure
from coach.core.planned_week import week_monday

# Opinion: three weeks is long enough to say a load sits unnoticed, short of a Block.
WEEKS_UNREAD = 3


def held_unread(history: Sequence[Exposure]) -> tuple[Exposure, ...]:
    """The newest run of `history` (newest first) at the newest one's top load with no RPE on
    any working set, oldest first, when it spans `WEEKS_UNREAD` weeks or more; empty otherwise."""
    if not history or history[0].top_load is None:
        return ()
    load = history[0].top_load
    run: list[Exposure] = []
    for exposure in history:
        if exposure.top_load != load or any(s.rpe is not None for s in exposure.working):
            break
        run.append(exposure)
    return tuple(reversed(run)) if weeks_spanned(run) >= WEEKS_UNREAD else ()


def weeks_spanned(run: Sequence[Exposure]) -> int:
    return len({week_monday(e.date) for e in run})
