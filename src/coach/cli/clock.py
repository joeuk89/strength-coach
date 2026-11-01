import datetime
import os
from collections.abc import Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coach.core.errors import Setup

LOCALTIME = "/etc/localtime"
FALLBACK_TIMEZONE = "UTC"


@dataclass(frozen=True)
class SystemClock:
    zone: ZoneInfo

    def now(self) -> datetime.datetime:
        return datetime.datetime.now(self.zone)

    def today(self) -> datetime.date:
        return self.now().date()


def clock_for(timezone: str) -> SystemClock:
    zone = _zone(timezone)
    if zone is None:
        raise Setup(
            "config_unknown_key",
            f"coach.toml: athlete.timezone {timezone!r} is not an IANA timezone name",
        )
    return SystemClock(zone)


def machine_timezone(env: Mapping[str, str]) -> str:
    """The machine's IANA zone name: `TZ` when it names one, else the `/etc/localtime` link."""
    candidates = [env.get("TZ", "").removeprefix(":")]
    if os.path.islink(LOCALTIME):
        _, marker, name = os.readlink(LOCALTIME).partition("zoneinfo/")
        candidates.append(name if marker else "")
    return next((name for name in candidates if _zone(name)), FALLBACK_TIMEZONE)


def _zone(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name) if name else None
    except (ZoneInfoNotFoundError, ValueError):
        return None
