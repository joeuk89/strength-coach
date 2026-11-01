"""`coach.toml` parsed whole into typed values (docs/spec/instance.md, "coach.toml")."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from coach.core.equipment import EQUIPMENT_KINDS
from coach.core.errors import Setup

type Units = Literal["kg", "lb"]
type Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
type Dumbbells = Literal["pair", "single"]

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
DUMBBELLS: tuple[Dumbbells, ...] = ("pair", "single")
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
class PlatePoolLocation:
    name: str
    kit: str
    collars: str
    dumbbells: Dumbbells
    implements: Mapping[str, str] = field(default_factory=dict[str, str])


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
        engine=Engine(version=_text(engine, "version", ("engine",))),
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

    def fact(key: str) -> object:
        return _required(table, key, here)

    return Athlete(
        units=_units(fact("units"), (*here, "units")),
        bodyweight_units=_units(fact("bodyweight_units"), (*here, "bodyweight_units")),
        week_starts=_weekday(fact("week_starts"), (*here, "week_starts")),
        timezone=_nonempty_text(fact("timezone"), (*here, "timezone")),
        available_days=_weekdays(fact("available_days"), (*here, "available_days")),
        session_minutes=_positive_int(fact("session_minutes"), (*here, "session_minutes")),
        checkin_cadence_days=_positive_int(
            table.get("checkin_cadence_days", DEFAULT_CHECKIN_CADENCE_DAYS),
            (*here, "checkin_cadence_days"),
        ),
    )


def _location(name: str, table: Mapping[str, object]) -> Location:
    path = ("location", name)
    kind = _choice(_required(table, "kind", path), ("plate-pool", "grid"), (*path, "kind"))
    implements = _implements(table, path)
    if kind == "plate-pool":
        _only(table, {"kind", "kit", "collars", "dumbbells", "implements"}, path)
        return PlatePoolLocation(
            name=name,
            kit=_nonempty_text(_required(table, "kit", path), (*path, "kit")),
            collars=_nonempty_text(_required(table, "collars", path), (*path, "collars")),
            dumbbells=cast(
                Dumbbells,
                _choice(_required(table, "dumbbells", path), DUMBBELLS, (*path, "dumbbells")),
            ),
            implements=implements,
        )
    _only(table, {"kind", "implements", "implement"}, path)
    implement_tables = _optional_table(table, "implement", path)
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


def _text(table: Mapping[str, object], key: str, path: tuple[str, ...]) -> str:
    return _nonempty_text(_required(table, key, path), (*path, key))


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
    return cast(Weekday, _choice(value, WEEKDAYS, path))


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
