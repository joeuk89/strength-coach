"""The closed week's kind by one precedence order (docs/spec/week.md, "Week kind")."""

import datetime
from collections.abc import Collection, Iterable, Sequence
from typing import Literal

from coach.core.closed_week.sessions import GATE_KINDS, SessionOutcome

type WeekKind = Literal[
    "light", "return", "break", "minimum", "one_off", "hard", "missed", "partial"
]

ORDINARY: tuple[WeekKind, ...] = ("hard", "partial", "missed")
# rn:deloads.2: a hard week passes 75 % of the gate denominator; under 50 % trained is missed.
HARD_SHARE = 0.75
MISSED_SHARE = 0.5
# The first return band's edge (docs/spec/prescription.md, "The return band").
RETURN_GAP_DAYS = 10
CARRIED_KINDS: tuple[tuple[str, WeekKind], ...] = (
    ("minimum_week", "minimum"),
    ("one_off_week", "one_off"),
)


def week_kind(
    sessions: Sequence[SessionOutcome], *, carried: Collection[str], returned: bool
) -> WeekKind:
    """`carried` names the week overrides the plan in force carried; `returned` is the whole-week
    layoff `is_return_week` reads."""
    if "light_week" in carried:
        return "light"
    if returned:
        return "return"
    if _break(sessions):
        return "break"
    for override, kind in CARRIED_KINDS:
        if override in carried:
            return kind
    gate = [s for s in sessions if s.in_gate]
    if not gate:
        return "partial"
    if sum(1 for s in gate if s.passed) >= HARD_SHARE * len(gate):
        return "hard"
    if sum(1 for s in gate if s.trained) < MISSED_SHARE * len(gate):
        return "missed"
    return "partial"


def is_return_week(monday: datetime.date, lifting_dates: Iterable[datetime.date]) -> bool:
    """The gap between the last lifting workout before the week's first and that first is over
    ten days; a first workout ever is no return."""
    sunday = monday + datetime.timedelta(days=6)
    dates = sorted(set(lifting_dates))
    first = next((d for d in dates if monday <= d <= sunday), None)
    if first is None:
        return False
    before = [d for d in dates if d < first]
    return bool(before) and (first - before[-1]).days > RETURN_GAP_DAYS


def _break(sessions: Sequence[SessionOutcome]) -> bool:
    core = [
        s
        for s in sessions
        if s.session.tier == "core" and s.session.kind in GATE_KINDS and not s.cancelled
    ]
    return bool(core) and all(s.rested for s in core)
