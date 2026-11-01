"""The values `publish` renders into pages (ADR 0012): read from the store by a service, handed
to `render` whole, so no page reads the store itself."""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field

from coach.core.check_in import Window
from coach.core.check_in_card import Card
from coach.core.config import Athlete, Dumbbells, Location, Units
from coach.core.progress import Progress

type Json = Mapping[str, object]


@dataclass(frozen=True)
class PlatePoolKit:
    """What a page links a plate-pool location with: the kit's short hash on every line link
    and the inventory inline in the set-up link (ADR 0021, "Routine pages")."""

    location: str
    collars: str
    dumbbells: Dumbbells
    implements: Mapping[str, str]
    short_hash: str
    inventory: bytes | None


@dataclass(frozen=True)
class PageLine:
    """One frozen prescription row; `set_groups` carry `load` in athlete units."""

    exercise_id: str
    name: str
    equipment_kind: str | None
    set_groups: tuple[Json, ...]
    steps: tuple[Json, ...] = ()
    flags: tuple[Json, ...] = ()
    change: str = ""
    derived_from: str = ""


@dataclass(frozen=True)
class RoutinePage:
    """An active Session as its routine stands: the frozen lines of its first planned date in
    the plan that last wrote it."""

    session_id: str
    title: str
    week: str | None
    location: str | None
    lines: tuple[PageLine, ...]
    kit: PlatePoolKit | None = None


@dataclass(frozen=True)
class PlannedSessionPage:
    session_id: str
    title: str
    date: datetime.date
    lines: tuple[PageLine, ...]


@dataclass(frozen=True)
class WeekPage:
    """The plan in force: its frozen prescriptions with their derivation steps."""

    plan_id: str
    week: str
    position: str
    approved_at: str
    sessions: tuple[PlannedSessionPage, ...]
    overrides: tuple[Json, ...] = ()


@dataclass(frozen=True)
class DecisionRead:
    id: str
    kind: str
    because: str
    text: str
    until: str | None = None
    session_id: str | None = None
    exercise_id: str | None = None


@dataclass(frozen=True)
class CheckInRecord:
    """A `current` Check-in row and the card over its window as the store stands now; `read`
    is the only frozen text."""

    id: str
    date: datetime.date
    tier: str
    window: Window
    readiness: str | None
    read: str
    card: Card
    decisions: tuple[DecisionRead, ...] = ()


@dataclass(frozen=True)
class NiggleRead:
    id: str
    site: str
    status: str
    opened: str
    constraints: tuple[Json, ...] = ()


@dataclass(frozen=True)
class FollowUpRead:
    id: str
    text: str
    due: str | None


@dataclass(frozen=True)
class AthletePage:
    """The profile verbatim beside sections generated from config and the store (ADR 0009)."""

    profile: str | None
    athlete: Athlete
    locations: tuple[Location, ...]
    niggles: tuple[NiggleRead, ...] = ()
    follow_ups: tuple[FollowUpRead, ...] = ()
    observations: tuple[str, ...] = ()
    decisions: tuple[DecisionRead, ...] = ()
    reads: tuple[tuple[datetime.date, str], ...] = ()


@dataclass(frozen=True)
class Pages:
    units: Units
    bodyweight_units: Units
    pin: str
    athlete: AthletePage
    progress: Progress
    week: WeekPage | None = None
    routines: tuple[RoutinePage, ...] = ()
    check_ins: tuple[CheckInRecord, ...] = field(default_factory=tuple[CheckInRecord, ...])
