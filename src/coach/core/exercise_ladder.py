"""`exercise_ladder` (docs/spec/program.md, "Schemes"): a ladder of exercise rungs, each with
the criterion for climbing off it (ADR 0023)."""

from dataclasses import replace

from coach.core.program.form import Advance, ExerciseLadder
from coach.core.registries.schemes import DEFAULT_EXPOSURES

# The scheme's opening position; the line stands here until a rung is a recorded choice.
OPENING_RUNG = 1


def full_criterion(ladder: ExerciseLadder, index: int) -> Advance:
    """Rung `index` (from 1)'s criterion with every unsaid key filled: the working group's reps
    or duration and its RPE, over the registry's run of exposures."""
    criterion = ladder.criterion(index)
    if criterion.manual:
        return criterion
    [group] = [g for g in ladder.rungs[index - 1].sets if g.working]
    top = group.reps[1] if isinstance(group.reps, tuple) else group.reps
    filled = Advance(
        reps=top if isinstance(top, int) and group.duration_s is None else None,
        duration_s=group.duration_s,
        rpe_at_most=group.rpe,
        exposures=DEFAULT_EXPOSURES,
    )
    return replace(filled, **criterion.stated())
