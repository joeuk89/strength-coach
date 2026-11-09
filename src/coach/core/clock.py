import datetime
from typing import Protocol


class Clock(Protocol):
    """The athlete's timezone, and today and now in it, so nothing below `cli` reads the system
    clock."""

    @property
    def zone(self) -> datetime.tzinfo: ...

    def today(self) -> datetime.date: ...

    def now(self) -> datetime.datetime: ...
