"""`coach.toml` parsed whole into typed values (docs/spec/instance.md, "coach.toml")."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from coach.core.equipment import EQUIPMENT_KINDS
from coach.core.errors import Setup

type Units = Literal["kg", "lb"]
type Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

UNITS: tuple[Units, ...] = ("kg", "lb")
WEEKDAYS: tuple[Weekday, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
DEFAULT_CHECKIN_CADENCE_DAYS = 7


@dataclass(frozen=True)
class Engine:
    version: str


@dataclass(frozen=True)
class Athlete:
    units: Units
    bodyweight_units: Units
    week_starts: Weekday
    timezone: str
    available_days: tuple[Weekday, ...]
    session_minutes: int
    checkin_cadence_days: int = DEFAULT_CHECKIN_CADENCE_DAYS


@dataclass(frozen=True)
class Hevy:
    pass


@dataclass(frozen=True)
class IncrementImplement:
    increment: float
    base: float = 0
    max: float | None = None


@dataclass(frozen=True)
class RackImplement:
    rack: tuple[float, ...]


type GridImplement = IncrementImplement | RackImplement


@dataclass(frozen=True)
class ImplementChoice:
    """Which of a plate-pool implement's kit tables apply: a hardware id (`none` included) when
    its tables offer hardware, and on a handle whether it is loaded single rather than a pair."""

    hardware: str | None = None
    single: bool = False


@dataclass(frozen=True)
class PlatePoolLocation:
    name: str
    kit: str
    implements: Mapping[str, str] = field(default_factory=dict[str, str])
    implement: Mapping[str, ImplementChoice] = field(default_factory=dict[str, ImplementChoice])

    def choices(self) -> dict[str, ImplementChoice]:
        return {name: self.implement[name] for name in self.implements.values()}


@dataclass(frozen=True)
class GridLocation:
    name: str
    implements: Mapping[str, str] = field(default_factory=dict[str, str])
    implement: Mapping[str, GridImplement] = field(default_factory=dict[str, GridImplement])


type Location = PlatePoolLocation | GridLocation


@dataclass(frozen=True)
class Config:
    engine: Engine
    athlete: Athlete
    hevy: Hevy | None = None
    locations: tuple[Location, ...] = ()


def parse_config(document: Mapping[str, object]) -> Config:
    """Raise `config_unknown_key` naming the first key that is unknown, missing or misshapen."""
    _only(document, {"engine", "athlete", "hevy", "location"}, ())
    engine = _table(document, "engine", ())
    _only(engine, {"version"}, ("engine",))
    hevy = document.get("hevy")
    if hevy is not None:
        _only(_table(document, "hevy", ()), set(), ("hevy",))
    locations = _optional_table(document, "location", ())
    return Config(
        engine=Engine(version=_field(engine, "version", ("engine",), _nonempty_text)),
        athlete=parse_athlete(_table(document, "athlete", ())),
        hevy=Hevy() if hevy is not None else None,
        locations=tuple(
            _location(name, _table(locations, name, ("location",))) for name in locations
        ),
    )


ATHLETE_FACTS = (
    "units",
    "bodyweight_units",
    "week_starts",
    "timezone",
    "available_days",
    "session_minutes",
    "checkin_cadence_days",
)


def athlete_fact(key: str, value: object) -> object:
    """One `[athlete]` fact checked against its shape, so `init` can check an answer alone."""
    path = ("athlete", key)
    match key:
        case "units" | "bodyweight_units":
            return _units(value, path)
        case "week_starts":
            return _weekday(value, path)
        case "timezone":
            return _nonempty_text(value, path)
        case "available_days":
            return _weekdays(value, path)
        case "session_minutes" | "checkin_cadence_days":
            return _positive_int(value, path)
        case _:
            raise _refuse(path, "is not an [athlete] fact")


def parse_athlete(table: Mapping[str, object]) -> Athlete:
    here = ("athlete",)
    _only(table, set(ATHLETE_FACTS), here)
    return Athlete(
        units=_field(table, "units", here, _units),
        bodyweight_units=_field(table, "bodyweight_units", here, _units),
        week_starts=_field(table, "week_starts", here, _weekday),
        timezone=_field(table, "timezone", here, _nonempty_text),
        available_days=_field(table, "available_days", here, _weekdays),
        session_minutes=_field(table, "session_minutes", here, _positive_int),
        checkin_cadence_days=_positive_int(
            table.get("checkin_cadence_days", DEFAULT_CHECKIN_CADENCE_DAYS),
            (*here, "checkin_cadence_days"),
        ),
    )


def _location(name: str, table: Mapping[str, object]) -> Location:
    path = ("location", name)
    kind = _choice(_required(table, "kind", path), ("plate-pool", "grid"), (*path, "kind"))
    implements = _implements(table, path)
    implement_tables = _optional_table(table, "implement", path)
    if kind == "plate-pool":
        _only(table, {"kind", "kit", "implements", "implement"}, path)
        for implement_name in implements.values():
            _required(implement_tables, implement_name, (*path, "implement"))
        return PlatePoolLocation(
            name=name,
            kit=_field(table, "kit", path, _nonempty_text),
            implements=implements,
            implement={
                key: _implement_choice(
                    _table(implement_tables, key, (*path, "implement")), (*path, "implement", key)
                )
                for key in implement_tables
            },
        )
    _only(table, {"kind", "implements", "implement"}, path)
    implement = {
        key: _grid_implement(
            _table(implement_tables, key, (*path, "implement")), (*path, "implement", key)
        )
        for key in implement_tables
    }
    for kind_name, implement_name in implements.items():
        if implement_name not in implement:
            raise _refuse(
                (*path, "implements", kind_name),
                f"names {implement_name!r}, which is no implement of this location",
            )
    return GridLocation(name=name, implements=implements, implement=implement)


def _implements(table: Mapping[str, object], path: tuple[str, ...]) -> dict[str, str]:
    here = (*path, "implements")
    mapping = _optional_table(table, "implements", path)
    _only(mapping, set(EQUIPMENT_KINDS), here)
    return {kind: _nonempty_text(mapping[kind], (*here, kind)) for kind in mapping}


def _implement_choice(table: Mapping[str, object], path: tuple[str, ...]) -> ImplementChoice:
    _only(table, {"hardware", "single"}, path)
    hardware = table.get("hardware")
    return ImplementChoice(
        hardware=None if hardware is None else _nonempty_text(hardware, (*path, "hardware")),
        single=_bool(table.get("single", False), (*path, "single")),
    )


def _grid_implement(table: Mapping[str, object], path: tuple[str, ...]) -> GridImplement:
    if ("increment" in table) == ("rack" in table):
        raise _refuse(path, "needs exactly one of increment or rack")
    if "rack" in table:
        _only(table, {"rack"}, path)
        loads = table["rack"]
        if not _is_list(loads) or not cast(list[object], loads):
            raise _refuse((*path, "rack"), "must be a list of loads")
        return RackImplement(
            rack=tuple(
                _positive_number(load, (*path, "rack")) for load in cast(list[object], loads)
            )
        )
    _only(table, {"increment", "base", "max"}, path)
    increment = _positive_number(table["increment"], (*path, "increment"))
    base = _number(table.get("base", 0), (*path, "base"))
    top = table.get("max")
    max_ = None if top is None else _number(top, (*path, "max"))
    if max_ is not None and max_ < base:
        raise _refuse((*path, "max"), f"is below base {base}")
    return IncrementImplement(increment=increment, base=base, max=max_)


def _only(table: Mapping[str, object], allowed: set[str], path: tuple[str, ...]) -> None:
    for key in table:
        if key not in allowed:
            raise _refuse((*path, key), "is not a key coach.toml knows")


def _table(table: Mapping[str, object], key: str, path: tuple[str, ...]) -> Mapping[str, object]:
    value = _required(table, key, path)
    if not isinstance(value, Mapping):
        raise _refuse((*path, key), "must be a table")
    return cast(Mapping[str, object], value)


def _optional_table(
    table: Mapping[str, object], key: str, path: tuple[str, ...]
) -> Mapping[str, object]:
    return _table(table, key, path) if key in table else {}


def _required(table: Mapping[str, object], key: str, path: tuple[str, ...]) -> object:
    if key not in table:
        raise _refuse((*path, key), "is missing")
    return table[key]


def _field[T](
    table: Mapping[str, object],
    key: str,
    path: tuple[str, ...],
    check: Callable[[object, tuple[str, ...]], T],
) -> T:
    return check(_required(table, key, path), (*path, key))


def _nonempty_text(value: object, path: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not value:
        raise _refuse(path, f"must be a non-empty string, not {value!r}")
    return value


def _choice(value: object, choices: Sequence[str], path: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise _refuse(path, f"must be one of {', '.join(choices)}, not {value!r}")
    return value


def _units(value: object, path: tuple[str, ...]) -> Units:
    return cast(Units, _choice(value, UNITS, path))


def _weekday(value: object, path: tuple[str, ...]) -> Weekday:
    written = value.lower() if isinstance(value, str) else None
    for day in WEEKDAYS:
        if written in (day, day[:3]):
            return day
    raise _refuse(path, f"must be a weekday such as monday or mon, not {value!r}")


def _bool(value: object, path: tuple[str, ...]) -> bool:
    if not isinstance(value, bool):
        raise _refuse(path, f"must be true or false, not {value!r}")
    return value


def _weekdays(value: object, path: tuple[str, ...]) -> tuple[Weekday, ...]:
    if not _is_list(value) or not cast(list[object], value):
        raise _refuse(path, "must be a non-empty list of weekdays")
    days: tuple[Weekday, ...] = tuple(_weekday(day, path) for day in cast(list[object], value))
    if len(set(days)) != len(days):
        raise _refuse(path, "names a weekday twice")
    return days


def _positive_int(value: object, path: tuple[str, ...]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _refuse(path, f"must be a positive whole number, not {value!r}")
    return value


def _number(value: object, path: tuple[str, ...]) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _refuse(path, f"must be a number, not {value!r}")
    return value


def _positive_number(value: object, path: tuple[str, ...]) -> float:
    number = _number(value, path)
    if number <= 0:
        raise _refuse(path, f"must be above zero, not {value!r}")
    return number


def _is_list(value: object) -> bool:
    return isinstance(value, list | tuple)


def _refuse(path: tuple[str, ...], why: str) -> Setup:
    return Setup("config_unknown_key", f"coach.toml: {'.'.join(path)} {why}")
