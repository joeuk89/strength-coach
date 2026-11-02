"""The carried e1RM (docs/spec/prescription.md, "The carried e1RM"): after a return week, a
`top_backoff` line reads the pre-layoff e1RM scaled by the return band's load factor until the
live e1RM catches it or 42 days have passed since the return exposure."""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass, replace

from coach.core.cut import return_band
from coach.core.days_off import SessionTrained, line_days_off
from coach.core.e1rm import PRECISION, WINDOW_DAYS, E1rm, e1rm
from coach.core.exposure import Exposure
from coach.core.load import Load

_DAY = datetime.timedelta(days=1)


@dataclass(frozen=True)
class CarriedE1rm:
    """`pre_layoff_on` is the day after the last exposure before the return: the slid window
    ends there as the live window ends on the planned date."""

    pre_layoff: E1rm
    factor: float
    expires: datetime.date
    pre_layoff_on: datetime.date

    @property
    def load(self) -> Load:
        amount = round(self.pre_layoff.load.amount * self.factor, PRECISION)
        return replace(self.pre_layoff.load, amount=amount)

    @property
    def e1rm(self) -> E1rm:
        return E1rm(self.load, self.pre_layoff.lower_bound, self.pre_layoff.exposure)


def carried_e1rm(
    exposures: Iterable[Exposure],
    trained: Iterable[SessionTrained],
    *,
    exercise_id: str,
    session_id: str,
    on: datetime.date,
) -> CarriedE1rm | None:
    """None in a return week itself, with no return exposure in the last 42 days, or with no
    qualifying point in the 42 days ending on the last exposure before the return."""
    exposures, trained = tuple(exposures), tuple(trained)

    def days_off_on(day: datetime.date) -> int:
        return line_days_off(
            exposures, trained, exercise_id=exercise_id, session_id=session_id, on=day
        ).days

    if return_band(days_off_on(on)) is not None:
        return None
    dates = sorted({e.date for e in exposures if e.exercise_id == exercise_id and e.date < on})
    since = on - datetime.timedelta(days=WINDOW_DAYS)
    for i in range(len(dates) - 1, 0, -1):
        returned = dates[i]
        if returned < since:
            return None
        band = return_band(days_off_on(returned))
        if band is None:
            continue
        pre_layoff_on = dates[i - 1] + _DAY
        point = e1rm(exposures, exercise_id, pre_layoff_on)
        if point is None:
            return None
        expires = returned + datetime.timedelta(days=WINDOW_DAYS)
        return CarriedE1rm(point, band.load_factor, expires, pre_layoff_on)
    return None


@dataclass(frozen=True)
class E1rmRead:
    """The one e1RM a line reads. `carried` is set only while it binds: above the live e1RM."""

    live: E1rm | None
    carried: CarriedE1rm | None = None

    @property
    def best(self) -> E1rm | None:
        return self.live if self.carried is None else self.carried.e1rm


def e1rm_read(live: E1rm | None, carried: CarriedE1rm | None) -> E1rmRead:
    if carried is None or (live is not None and live.load.amount >= carried.load.amount):
        return E1rmRead(live)
    return E1rmRead(live, carried)
