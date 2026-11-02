"""The session time estimate `program adopt` reads (docs/spec/program.md, "Adopt")."""

import math
from collections.abc import Sequence

from coach.core.program.form import Line

# The time one set takes before its rest, when it states no duration_s; an opinion.
SET_WORK_S = 40


def session_estimate(lines: Sequence[Line]) -> int | None:
    """Whole minutes, rounded up; None for a session with no lines."""
    if not lines:
        return None
    seconds = sum(
        group.count * ((group.duration_s or SET_WORK_S) + line.rest_s)
        for line in lines
        for group in line.sets
    )
    return math.ceil(seconds / 60)
