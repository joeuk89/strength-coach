import datetime
from collections.abc import Callable

from coach.core.clock import Clock

# Hevy answers 429 after about seven rapid writes; a burst of three, then one every 3 s.
WRITE_BURST = 3
WRITE_INTERVAL_S = 3.0


class TokenBucket:
    """`take()` returns once a token is free, sleeping for it when none is.

    Time slept counts as elapsed even when the clock stands still, so a fixed clock cannot stall it.
    """

    def __init__(
        self,
        clock: Clock,
        sleeper: Callable[[float], None],
        *,
        burst: int = WRITE_BURST,
        interval_s: float = WRITE_INTERVAL_S,
    ) -> None:
        self._clock = clock
        self._sleeper = sleeper
        self._burst = burst
        self._interval_s = interval_s
        self._tokens = float(burst)
        self._at: datetime.datetime | None = None

    def take(self) -> None:
        now = self._clock.now()
        if self._at is not None:
            now = max(now, self._at)
            refill = (now - self._at).total_seconds() / self._interval_s
            self._tokens = min(float(self._burst), self._tokens + refill)
        self._at = now
        if self._tokens < 1:
            wait = (1 - self._tokens) * self._interval_s
            self._sleeper(wait)
            self._at = now + datetime.timedelta(seconds=wait)
            self._tokens = 1.0
        self._tokens -= 1
