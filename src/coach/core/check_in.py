import datetime
from dataclasses import dataclass

from coach.core.errors import Invalid

# week.md, "When a check-in is due": a window longer than this is a catch-up.
CATCH_UP_DAYS = 10
# rn:deloads.12: the deep review falls due 42 days after the last one.
DEEP_DAYS = 42
DAY = datetime.timedelta(days=1)


@dataclass(frozen=True)
class Window:
    start: datetime.date
    end: datetime.date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def catch_up(self) -> bool:
        return self.days > CATCH_UP_DAYS


def check_in_window(
    date: datetime.date,
    *,
    previous_end: datetime.date | None = None,
    first_plan_monday: datetime.date | None = None,
    file_start: datetime.date | None = None,
) -> Window:
    """The span a check-in reviews, derived once at `checkin record` (check-in.md, "The row")."""
    if previous_end is not None:
        if file_start is not None:
            raise Invalid(
                "state_conflict",
                "window_start is set only on the instance's first check-in; this window starts "
                f"the day after the previous one's window_end, {previous_end}",
            )
        start = previous_end + DAY
    else:
        planned = first_plan_monday if first_plan_monday and first_plan_monday <= date else None
        start = file_start or planned or date
    if start > date:
        raise Invalid(
            "state_conflict",
            f"the check-in on {date} would review a window starting {start}, after its date",
        )
    return Window(start, date)


@dataclass(frozen=True)
class LastCheckIn:
    """The newest `current` Check-in row."""

    date: datetime.date
    tier: str
    window: Window


@dataclass(frozen=True)
class CheckInDue:
    """Whether a check-in is due today, the tier it takes and the window it would review."""

    due: bool
    due_on: datetime.date | None
    tier: str
    window: Window | None

    @property
    def catch_up(self) -> bool:
        return self.window is not None and self.window.catch_up


def check_in_due(
    today: datetime.date,
    *,
    cadence_days: int,
    last: LastCheckIn | None = None,
    last_deep: datetime.date | None = None,
    first_plan_monday: datetime.date | None = None,
    redesign_since_deep: bool = False,
    light_week_proposed: bool = False,
    deep_deferred_until: datetime.date | None = None,
) -> CheckInDue:
    """week.md, "When a check-in is due". The light cadence makes a check-in due; the deep
    rules set the tier of the one that falls due."""
    cadence = datetime.timedelta(days=cadence_days)
    if last is not None:
        due_on, start = last.date + cadence, last.window.end + DAY
    elif first_plan_monday is not None:
        due_on, start = first_plan_monday + cadence - DAY, first_plan_monday
    else:
        return CheckInDue(due=False, due_on=None, tier="light", window=None)
    window = Window(start, today) if start <= today else None
    deep_from = last_deep or first_plan_monday
    wants_deep = (
        (deep_from is not None and (today - deep_from).days >= DEEP_DAYS)
        or (last_deep is not None and redesign_since_deep)
        or light_week_proposed
        or (last is not None and last.window.catch_up)
    )
    deferred = deep_deferred_until is not None and today <= deep_deferred_until
    catch_up = window is not None and window.catch_up
    deep = wants_deep and not deferred and not catch_up
    return CheckInDue(
        due=today >= due_on, due_on=due_on, tier="deep" if deep else "light", window=window
    )
