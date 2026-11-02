"""The logged history as core values: exposures carrying their Match and the session dates
trained without sets."""

import datetime
from dataclasses import dataclass

from coach.core.config import Units
from coach.core.days_off import DaysOff, SessionTrained, line_days_off
from coach.core.exposure import Exposure, lifting_reads
from coach.services.closed_weeks import WeekLog
from coach.store.connection import Connection


@dataclass(frozen=True)
class History:
    exposures: tuple[Exposure, ...]
    trained: tuple[SessionTrained, ...]

    @property
    def lifting(self) -> tuple[Exposure, ...]:
        """What a lifting or rehab line reads (ADR 0010)."""
        return lifting_reads(self.exposures)


def read_history(conn: Connection, units: Units, log: WeekLog | None = None) -> History:
    """`log` is the closed-week log already built for the same store, if any: its Match is the
    one the history carries."""
    log = log or WeekLog(conn, units)
    return History(log.matched_exposures, log.trained)


def days_off_for_line(
    conn: Connection, *, exercise_id: str, session_id: str, on: datetime.date, units: Units
) -> DaysOff:
    history = read_history(conn, units)
    return line_days_off(
        history.lifting,
        history.trained,
        exercise_id=exercise_id,
        session_id=session_id,
        on=on,
    )
