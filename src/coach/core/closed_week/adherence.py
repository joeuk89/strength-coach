"""Adherence over the last four ordinary closed weeks (docs/spec/week.md, "Adherence")."""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from coach.core.closed_week.week import ClosedWeek
from coach.core.planned_week import week_monday

type AdherenceState = Literal["ok", "watch", "low", "insufficient"]

ORDINARY_WEEKS = 4
# The engine's opinion: adherence from before a month-long break says nothing about now.
LOOKBACK_WEEKS = 8
# rn:deloads.7 and rn:deloads.6.
WATCH_BELOW = 0.8
LOW_BELOW = 0.7


@dataclass(frozen=True)
class Adherence:
    state: AdherenceState
    figure: float | None = None
    weeks: int = 0


def adherence(weeks: Iterable[ClosedWeek], today: datetime.date) -> Adherence:
    since = week_monday(today) - datetime.timedelta(weeks=LOOKBACK_WEEKS - 1)
    ordinary = sorted(
        (w for w in weeks if w.ordinary and w.monday >= since), key=lambda w: w.monday
    )[-ORDINARY_WEEKS:]
    if len(ordinary) < ORDINARY_WEEKS:
        return Adherence("insufficient", None, len(ordinary))
    planned = sum(w.adherence_planned for w in ordinary)
    figure = sum(w.adherence_trained for w in ordinary) / planned if planned else 1.0
    if figure < LOW_BELOW:
        return Adherence("low", figure, len(ordinary))
    if figure < WATCH_BELOW:
        return Adherence("watch", figure, len(ordinary))
    return Adherence("ok", figure, len(ordinary))
