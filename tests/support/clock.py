import datetime

NOON = datetime.datetime(2026, 10, 30, 12, 0, tzinfo=datetime.UTC)


class FixedClock:
    def __init__(self, now: datetime.datetime = NOON) -> None:
        self.moment = now

    def today(self) -> datetime.date:
        return self.moment.date()

    def now(self) -> datetime.datetime:
        return self.moment


def at(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(day, NOON.time(), tzinfo=datetime.UTC)
