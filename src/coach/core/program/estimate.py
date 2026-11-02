"""The session time estimate `program adopt` reads (docs/spec/program.md, "Adopt")."""

import math

from coach.core.program.form import Session

# The time one set takes before its rest, when it states no duration_s; an opinion.
SET_WORK_S = 40


def session_estimate(session: Session) -> int | None:
    """Whole minutes, rounded up; None for a session with no lines or no minutes."""
    if session.minutes is None or not session.lines:
        return None
    seconds = sum(
        group.count * ((group.duration_s or SET_WORK_S) + line.rest_s)
        for line in session.lines
        for group in line.sets
    )
    return math.ceil(seconds / 60)
