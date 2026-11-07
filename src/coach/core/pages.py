"""The values `publish` renders into pages (ADR 0012): read from the store by a service, handed
to `render` whole, so no page reads the store itself."""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field

from coach.core.check_in import Window
from coach.core.check_in_card import Card
from coach.core.config import Athlete, ImplementChoice, Location, Units
from coach.core.progress import Progress
from coach.core.rack import ListedRack

type Json = Mapping[str, object]


@dataclass(frozen=True)
class PlatePoolKit:
    """What a page links a plate-pool location with: the kit's short hash on every line link
    and the inventory inline in the set-up link (ADR 0021, "Routine pages"). `racks` holds the
    rack of each implement whose choice lists several hardware ids."""

    location: str
    implements: Mapping[str, str]
    implement: Mapping[str, ImplementChoice]
    short_hash: str
    inventory: bytes | None
    racks: Mapping[str, ListedRack] = field(default_factory=dict[str, ListedRack])

    def hardware_at(self, implement: str, load: float) -> str | None:
        """The hardware a per-line link names for `load`: a list choice names the hardware of
        the row at that load, or its first id when no row has it."""
        choice = self.implement.get(implement, ImplementChoice())
        if not isinstance(choice.hardware, tuple):
            return choice.hardware
        rack = self.racks.get(implement)
        row = next(iter(rack.rows_within(load, load)), None) if rack else None
        if row is not None and row.hardware is not None:
            return row.hardware
        return choice.hardware[0] if choice.hardware else None


@dataclass(frozen=True)
class PageRung:
    """One rung of a line's ladder as the version authors it; `criterion` is in full."""

    rung: int
    name: str
    cues: str | None
    set_groups: tuple[Json, ...]
    criterion: Json
    standing: bool


@dataclass(frozen=True)
class PageLine:
    """One frozen prescription row; `set_groups` carry `load` in athlete units. `ladder` is the
    whole ladder of an `exercise_ladder` line."""

    exercise_id: str
    name: str
    equipment_kind: str | None
    set_groups: tuple[Json, ...]
    steps: tuple[Json, ...] = ()
    flags: tuple[Json, ...] = ()
    change: str = ""
    derived_from: str = ""
    ladder: tuple[PageRung, ...] = ()


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
    """A session the plan derives, or (`derived` false) frozen rows the derivation no longer
    plans, kept so an approved row is never lost. `estimated_sets` stands in for lines."""

    session_id: str
    title: str
    date: datetime.date
    kind: str
    lines: tuple[PageLine, ...]
    estimated_sets: Mapping[str, int] | None = None
    derived: bool = True


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
    check_ins: tuple[CheckInRecord, ...] = ()
