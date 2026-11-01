"""The program Draft read into a form. A malformed value stops the read at once; a key outside
the schema is collected, so adopt reports it as `unknown_key` beside every other violation."""

import hashlib
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from coach.core.errors import Invalid
from coach.core.program.form import (
    CADENCES,
    EMPHASES,
    TIERS,
    WEEKDAYS,
    AcknowledgeEntry,
    Deload,
    Dose,
    Emphasis,
    Line,
    Number,
    ProgramForm,
    Reps,
    Schedule,
    SchemeRef,
    Session,
    SetGroup,
)
from coach.core.registries.ledger import REASONS
from coach.core.registries.program import SESSION_KINDS, VERSION_KINDS

type Table = Mapping[str, object]

DECLARED_EXERCISE_KEYS = (
    "name",
    "load_mode",
    "equipment_kind",
    "pattern",
    "muscles",
    "hevy_title",
    "hevy_exercise_type",
    "hevy_equipment",
    "hevy_muscle_group",
)


@dataclass(frozen=True)
class ParsedDraft:
    hash: str
    form: ProgramForm
    unknown_keys: tuple[str, ...]


def draft_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse_program_draft(data: bytes, *, file: str) -> ParsedDraft:
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise Invalid("invalid_argument", f"{file} is not valid TOML: {error}") from error
    form, unknown = parse_form(document, file=file)
    return ParsedDraft(draft_hash(data), form, unknown)


def parse_form(document: Table, *, file: str) -> tuple[ProgramForm, tuple[str, ...]]:
    """The form and the paths of the keys outside the schema. Reads a Draft and a stored form."""
    unknown: list[str] = []
    top = _Reader(document, (), file, unknown)
    form = ProgramForm(
        name=top.text("name"),
        kind=top.choice("kind", VERSION_KINDS.names()),
        because=top.text("because"),
        emphasis=cast(Emphasis, top.choice("emphasis", EMPHASES)),
        location=top.text("location"),
        schedule=_schedule(top.table("schedule")),
        dose=_dose(top.optional_table("dose")),
        deload=_deload(top.optional_table("deload")),
        sessions=tuple(_session(r) for r in top.tables("session", required=True)),
        exercises=_exercises(top.optional_table("exercise")),
        acknowledgements=tuple(_acknowledge(r) for r in top.tables("acknowledge")),
    )
    top.finish()
    return form, tuple(sorted(unknown))


def _schedule(reader: "_Reader") -> Schedule:
    rotation = reader.texts("rotation")
    if not rotation or len(set(rotation)) != len(rotation):
        raise reader.wrong("rotation", "a list of distinct week names")
    weeks: dict[str, dict[str, str]] = {}
    for week in rotation:
        days = reader.optional_table(week)
        if days is None:
            continue
        weeks[week] = {day: days.text(day) for day in WEEKDAYS if days.has(day)}
        days.finish()
    reader.finish()
    return Schedule(tuple(rotation), weeks)


def _dose(reader: "_Reader | None") -> Dose | None:
    if reader is None:
        return None
    lift = reader.optional_table("lift")
    targets = {} if lift is None else {name: lift.count(name) for name in lift.names()}
    if lift is not None:
        lift.finish()
    dose = Dose(per_muscle=reader.count("per_muscle"), lift=targets)
    reader.finish()
    return dose


def _deload(reader: "_Reader | None") -> Deload | None:
    if reader is None:
        return None
    deload = Deload(
        hard_weeks_ceiling=reader.count("hard_weeks_ceiling"),
        set_cut_pct=reader.percent("set_cut_pct"),
        load_cut_pct=reader.percent("load_cut_pct"),
        rpe_cap=reader.rpe("rpe_cap"),
        test_priority_lifts=reader.boolean("test_priority_lifts"),
    )
    reader.finish()
    return deload


def _session(reader: "_Reader") -> Session:
    id_ = reader.text("id")
    reader.name_as(("session", id_))
    estimated = reader.optional_table("estimated_sets")
    session = Session(
        id=id_,
        title=reader.text("title"),
        kind=reader.choice("kind", (*SESSION_KINDS.names(), "rehab")),
        tier=reader.choice("tier", TIERS),
        cadence=reader.optional_choice("cadence", CADENCES),
        location=reader.optional_text("location"),
        minutes=reader.optional_count("minutes"),
        scheme=_scheme(reader.optional_table("scheme")),
        estimated_sets=(
            None if estimated is None else {m: estimated.whole(m) for m in estimated.names()}
        ),
        lines=tuple(_line(r) for r in reader.tables("line")),
    )
    reader.finish()
    return session


def _line(reader: "_Reader") -> Line:
    exercise = reader.text("exercise")
    reader.name_as((*reader.path[:-1], exercise))
    scheme = _scheme(reader.optional_table("scheme"))
    if scheme is None:
        raise reader.missing("scheme")
    line = Line(
        exercise=exercise,
        load_mode=reader.optional_text("load_mode"),
        sets=tuple(_group(r) for r in reader.tables("sets", required=True)),
        rest_s=reader.whole("rest_s"),
        cues=reader.optional_text("cues"),
        scheme=scheme,
        start_load=reader.optional_load("start_load"),
        superset=reader.optional_text("superset"),
    )
    reader.finish()
    return line


def _group(reader: "_Reader") -> SetGroup:
    group = SetGroup(
        count=reader.count("count"),
        type=reader.optional_text("type") or "working",
        reps=reader.optional_reps("reps"),
        duration_s=reader.optional_count("duration_s"),
        rpe=reader.optional_rpe("rpe"),
    )
    reader.finish()
    return group


def _scheme(reader: "_Reader | None") -> SchemeRef | None:
    if reader is None:
        return None
    name = reader.text("name")
    return SchemeRef(name, {key: reader.raw(key) for key in reader.names() if key != "name"})


def _exercises(reader: "_Reader | None") -> dict[str, Mapping[str, object]]:
    if reader is None:
        return {}
    declared: dict[str, Mapping[str, object]] = {}
    for id_ in reader.names():
        fields = reader.table(id_)
        declared[id_] = {key: fields.raw(key) for key in DECLARED_EXERCISE_KEYS if fields.has(key)}
        fields.finish()
    return declared


def _acknowledge(reader: "_Reader") -> AcknowledgeEntry:
    entry = AcknowledgeEntry(
        flag=reader.text("flag"),
        because=reader.choice("because", REASONS.names()),
        text=reader.text("text"),
    )
    reader.finish()
    return entry


class _Reader:
    """One table's values read by type; `finish` records every key nobody read."""

    def __init__(self, table: Table, path: tuple[str, ...], file: str, unknown: list[str]) -> None:
        self.values = table
        self.path = path
        self.file = file
        self.unknown = unknown
        self.read: set[str] = set()

    def name_as(self, path: tuple[str, ...]) -> None:
        self.path = path

    def names(self) -> list[str]:
        self.read.update(self.values)
        return list(self.values)

    def has(self, key: str) -> bool:
        return key in self.values

    def raw(self, key: str) -> object:
        self.read.add(key)
        return self.values.get(key)

    def finish(self) -> None:
        self.unknown.extend(
            ".".join((*self.path, key)) for key in self.values if key not in self.read
        )

    def text(self, key: str) -> str:
        value = self.optional_text(key)
        if value is None:
            raise self.missing(key)
        return value

    def optional_text(self, key: str) -> str | None:
        value = self.raw(key)
        if value is None or (isinstance(value, str) and value):
            return value
        raise self.wrong(key, "a non-empty string")

    def texts(self, key: str) -> list[str]:
        value = self.raw(key)
        if not _is_list(value) or not all(isinstance(v, str) and v for v in _items(value)):
            raise self.wrong(key, "a list of names")
        return [cast(str, v) for v in _items(value)]

    def choice(self, key: str, choices: Sequence[str]) -> str:
        value = self.optional_choice(key, choices)
        if value is None:
            raise self.missing(key)
        return value

    def optional_choice(self, key: str, choices: Sequence[str]) -> str | None:
        value = self.optional_text(key)
        if value is None or value in choices:
            return value
        raise self.wrong(key, f"one of {', '.join(choices)}")

    def count(self, key: str) -> int:
        value = self.optional_count(key)
        if value is None:
            raise self.missing(key)
        return value

    def optional_count(self, key: str) -> int | None:
        value = self.raw(key)
        if value is None or (_is_int(value) and cast(int, value) > 0):
            return cast(int | None, value)
        raise self.wrong(key, "a whole number above 0")

    def whole(self, key: str) -> int:
        value = self.raw(key)
        if value is None:
            raise self.missing(key)
        if _is_int(value) and cast(int, value) >= 0:
            return cast(int, value)
        raise self.wrong(key, "a whole number of at least 0")

    def percent(self, key: str) -> Number:
        value = self.raw(key)
        if _is_number(value) and 0 <= cast(float, value) <= 100:
            return cast(Number, value)
        raise self.wrong(key, "a percentage from 0 to 100")

    def rpe(self, key: str) -> Number:
        value = self.optional_rpe(key)
        if value is None:
            raise self.missing(key)
        return value

    def optional_rpe(self, key: str) -> Number | None:
        value = self.raw(key)
        if value is None or (_is_number(value) and 0 < cast(float, value) <= 10):
            return cast(Number | None, value)
        raise self.wrong(key, "an RPE above 0 and at most 10")

    def optional_load(self, key: str) -> Number | None:
        value = self.raw(key)
        if value is None or (_is_number(value) and cast(float, value) >= 0):
            return cast(Number | None, value)
        raise self.wrong(key, "a load of at least 0 in athlete units")

    def boolean(self, key: str) -> bool:
        value = self.raw(key)
        if isinstance(value, bool):
            return value
        raise self.wrong(key, "true or false")

    def optional_reps(self, key: str) -> Reps | None:
        value = self.raw(key)
        if value is None:
            return None
        if _is_int(value) and cast(int, value) > 0:
            return cast(int, value)
        if _is_list(value):
            pair = _items(value)
            if len(pair) == 2 and all(_is_int(n) and cast(int, n) > 0 for n in pair):
                low, high = cast(int, pair[0]), cast(int, pair[1])
                if low <= high:
                    return (low, high)
        if isinstance(value, str) and value.endswith("+") and value[:-1].isdigit():
            return value
        raise self.wrong(key, 'a rep count, a range [6, 8] or an open top "8+"')

    def table(self, key: str) -> "_Reader":
        reader = self.optional_table(key)
        if reader is None:
            raise self.missing(key)
        return reader

    def optional_table(self, key: str) -> "_Reader | None":
        value = self.raw(key)
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise self.wrong(key, "a table")
        return _Reader(cast(Table, value), (*self.path, key), self.file, self.unknown)

    def tables(self, key: str, *, required: bool = False) -> list["_Reader"]:
        value = self.raw(key)
        if value is None and not required:
            return []
        if not _is_list(value) or not _items(value):
            raise self.wrong(key, "an array of tables with at least one entry")
        items = _items(value)
        if not all(isinstance(item, Mapping) for item in items):
            raise self.wrong(key, "an array of tables")
        return [
            _Reader(cast(Table, item), (*self.path, key, str(i)), self.file, self.unknown)
            for i, item in enumerate(items, start=1)
        ]

    def missing(self, key: str) -> Invalid:
        return Invalid("invalid_argument", f"{self._where(key)} is required")

    def wrong(self, key: str, wanted: str) -> Invalid:
        return Invalid("invalid_argument", f"{self._where(key)} must be {wanted}")

    def _where(self, key: str) -> str:
        return f"{self.file}: {'.'.join((*self.path, key))}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_list(value: object) -> bool:
    return isinstance(value, list | tuple)


def _items(value: object) -> Sequence[object]:
    return cast(Sequence[object], value)
