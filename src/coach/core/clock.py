import datetime
from typing import Protocol


class Clock(Protocol):
    """Today and now in the athlete's timezone, so nothing below `cli` reads the system clock."""

    def today(self) -> datetime.date: ...

    def now(self) -> datetime.datetime: ...
