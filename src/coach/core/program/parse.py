"""The program Draft read into a form. A malformed value stops the read at once; a key outside
the schema is collected, so adopt reports it as `unknown_key` beside every other violation."""

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast, overload

from coach.core.draft_fields import draft_hash
from coach.core.draft_reader import Reader, Table, is_int
from coach.core.draft_schema import BOOLEAN, TEXT, TEXTS, Json, Location
from coach.core.errors import Invalid
from coach.core.muscles import MUSCLES_WANTED, read_muscles
from coach.core.program.form import (
    CADENCES,
    EMPHASES,
    TIERS,
    WEEKDAYS,
    AcknowledgeEntry,
    Advance,
    Deload,
    Dose,
    Emphasis,
    ExerciseLadder,
    LiftDose,
    Line,
    Number,
    ProgramForm,
    Reps,
    Rung,
    Schedule,
    SchemeRef,
    Session,
    SetGroup,
)
from coach.core.registries.ledger import REASONS
from coach.core.registries.program import (
    EQUIPMENT_KINDS,
    LOAD_MODES,
    SESSION_KINDS,
    VERSION_KINDS,
)

SESSION_IDS: Json = {"anyOf": [TEXT, {"type": "array", "minItems": 1, "items": TEXT}]}
COUNT: Json = {"type": "integer", "minimum": 1}
PERCENT: Json = {"type": "number", "minimum": 0, "maximum": 100}
RPE: Json = {"type": "number", "exclusiveMinimum": 0, "maximum": 10}
LOAD: Json = {"type": "number", "minimum": 0}
REPS: Json = {
    "anyOf": [
        COUNT,
        {"type": "array", "prefixItems": [COUNT, COUNT], "minItems": 2, "maxItems": 2},
        {"type": "string", "pattern": "^[0-9]+\\+$"},
    ]
}
MUSCLES: Json = {
    "type": "object",
    "properties": {
        "primary": {"type": "array", "items": {"type": "string"}},
        "secondary": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["primary", "secondary"],
    "additionalProperties": False,
}

LINED_KINDS = ("lifting", "conditioning", "practice")

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
        name=top.text("name", required=True),
        kind=top.choice("kind", VERSION_KINDS.names(), required=True),
        because=top.text("because", required=True),
        emphasis=cast(Emphasis, top.choice("emphasis", EMPHASES, required=True)),
        location=top.text("location", required=True),
        schedule=_schedule(top.table("schedule", required=True)),
        dose=_dose(top.table("dose")),
        deload=_deload(top.table("deload")),
        sessions=tuple(
            _session(r) for r in top.tables("session", required=True, at_least_one=True)
        ),
        exercises=_exercises(top.table("exercise")),
        acknowledgements=tuple(
            _acknowledge(r) for r in top.tables("acknowledge", at_least_one=True)
        ),
    )
    top.finish()
    return form, tuple(sorted(unknown))


def _schedule(reader: "_Reader") -> Schedule:
    rotation = reader.texts("rotation")
    if not rotation or len(set(rotation)) != len(rotation):
        raise reader.wrong("rotation", "a list of distinct week names")
    weeks: dict[str, dict[str, tuple[str, ...]]] = {}
    for week in rotation:
        days = reader.table(week)
        if days is None:
            continue
        weeks[week] = {day: days.session_ids(day) for day in WEEKDAYS if days.has(day)}
        days.finish()
    reader.finish()
    return Schedule(tuple(rotation), weeks)


def _dose(reader: "_Reader | None") -> Dose | None:
    if reader is None:
        return None
    lift = reader.table("lift")
    targets = {} if lift is None else {name: _lift_dose(lift, name) for name in lift.names()}
    if lift is not None:
        lift.finish()
    dose = Dose(per_muscle=reader.count("per_muscle", required=True), lift=targets)
    reader.finish()
    return dose


def _lift_dose(reader: "_Reader", lift: str) -> LiftDose:
    if not isinstance(reader.raw(lift), Mapping):
        return LiftDose(reader.count(lift, required=True))
    table = reader.table(lift, required=True)
    dose = LiftDose(
        table.count("sets", required=True),
        tuple(table.texts("counts")) if table.has("counts") else (),
    )
    table.finish()
    return dose


def _deload(reader: "_Reader | None") -> Deload | None:
    if reader is None:
        return None
    deload = Deload(
        hard_weeks_ceiling=reader.count("hard_weeks_ceiling", required=True),
        set_cut_pct=reader.percent("set_cut_pct"),
        load_cut_pct=reader.percent("load_cut_pct"),
        rpe_cap=reader.rpe("rpe_cap", required=True),
        test_priority_lifts=reader.true_or_false("test_priority_lifts"),
    )
    reader.finish()
    return deload


def _session(reader: "_Reader") -> Session:
    id_ = reader.text("id", required=True)
    reader.name_as(("session", id_))
    estimated = reader.table("estimated_sets")
    title = reader.text("title", required=True)
    kind = reader.choice("kind", (*SESSION_KINDS.names(), "rehab"), required=True)
    session = Session(
        id=id_,
        title=title,
        kind=kind,
        tier=reader.choice("tier", TIERS, required=True),
        cadence=reader.choice("cadence", CADENCES),
        location=reader.text("location"),
        minutes=reader.count("minutes"),
        scheme=_scheme(reader.table("scheme")),
        estimated_sets=(
            None
            if estimated is None
            else {m: estimated.whole(m, required=True) for m in estimated.names()}
        ),
        lines=tuple(
            _line(r) for r in reader.tables("line", required=kind in LINED_KINDS, at_least_one=True)
        ),
    )
    reader.finish()
    return session


def parse_line(document: Table, *, file: str) -> Line:
    """One line document in the form's shape; a rehab session's stored lines read through it."""
    return _line(_Reader(document, ("line",), file, []))


def parse_set_groups(groups: Sequence[Table], *, file: str, where: str) -> tuple[SetGroup, ...]:
    """A line's whole set groups outside a form; a key outside the group's shape is refused."""
    unknown: list[str] = []
    parsed = tuple(_group(_Reader(group, (where,), file, unknown)) for group in groups)
    if unknown:
        raise Invalid("unknown_key", f"{file}: unknown key {', '.join(unknown)}")
    return parsed


def _line(reader: "_Reader") -> Line:
    exercise = reader.text("exercise", required=True)
    reader.name_as((*reader.path[:-1], exercise))
    scheme = _scheme(reader.table("scheme"), line_exercise=exercise)
    if scheme is None:
        raise reader.missing("scheme")
    # A ladder's rungs carry the sets; the line stands on the first until a rung is chosen.
    sets = (
        scheme.ladder.rungs[0].sets
        if scheme.ladder
        else tuple(_group(r) for r in reader.tables("sets", required=True, at_least_one=True))
    )
    line = Line(
        exercise=exercise,
        load_mode=reader.text("load_mode"),
        sets=sets,
        rest_s=reader.whole("rest_s", required=True),
        cues=reader.text("cues"),
        scheme=scheme,
        start_load=reader.load("start_load"),
        superset=reader.text("superset"),
    )
    reader.finish()
    return line


def _group(reader: "_Reader") -> SetGroup:
    group = SetGroup(
        count=reader.count("count", required=True),
        type=reader.text("type") or "working",
        reps=reader.reps("reps"),
        duration_s=reader.count("duration_s"),
        rpe=reader.rpe("rpe"),
    )
    reader.finish()
    return group


def _scheme(reader: "_Reader | None", *, line_exercise: str | None = None) -> SchemeRef | None:
    if reader is None:
        return None
    name = reader.text("name", required=True)
    ladder = (
        _ladder(reader, line_exercise)
        if name == "exercise_ladder" and line_exercise is not None
        else None
    )
    params = {key: reader.raw(key) for key in reader.names() if key != "name"}
    return SchemeRef(name, params, ladder)


def _ladder(reader: "_Reader", line_exercise: str) -> ExerciseLadder:
    rungs = tuple(
        _rung(r, line_exercise if index == 0 else None)
        for index, r in enumerate(reader.tables("rungs", required=True, at_least_one=True))
    )
    return ExerciseLadder(rungs, _advance(reader.table("advance")))


def _rung(reader: "_Reader", line_exercise: str | None) -> Rung:
    """The first rung is the line's exercise, so it may leave `exercise` unsaid."""
    if line_exercise is None:
        exercise = reader.text("exercise", required=True)
    else:
        exercise = reader.text("exercise") or line_exercise
        if exercise != line_exercise:
            raise reader.wrong("exercise", f"the line's exercise {line_exercise!r}, or unsaid")
    rung = Rung(
        exercise=exercise,
        sets=tuple(_group(r) for r in reader.tables("sets", required=True, at_least_one=True)),
        cues=reader.text("cues"),
        advance=_advance(reader.table("advance")),
    )
    reader.finish()
    return rung


def _advance(reader: "_Reader | None") -> Advance:
    if reader is None:
        return Advance()
    advance = Advance(
        reps=reader.count("reps"),
        duration_s=reader.count("duration_s"),
        rpe_at_most=reader.rpe("rpe_at_most"),
        exposures=reader.count("exposures"),
        manual=reader.boolean("manual"),
    )
    reader.finish()
    return advance


def _exercises(reader: "_Reader | None") -> dict[str, Mapping[str, object]]:
    if reader is None:
        return {}
    declared: dict[str, Mapping[str, object]] = {}
    for id_ in reader.names():
        declared[id_] = _declared_exercise(reader.table(id_, required=True))
    return declared


def _declared_exercise(reader: "_Reader") -> dict[str, object]:
    fields: dict[str, object] = {}
    for key in DECLARED_EXERCISE_KEYS:
        if not reader.has(key):
            continue
        if key == "muscles":
            fields[key] = reader.muscles(key)
        elif key == "load_mode":
            fields[key] = reader.choice(key, LOAD_MODES.names())
        elif key == "equipment_kind":
            fields[key] = reader.choice(key, EQUIPMENT_KINDS.names())
        else:
            fields[key] = reader.text(key)
    reader.finish()
    return fields


def _acknowledge(reader: "_Reader") -> AcknowledgeEntry:
    entry = AcknowledgeEntry(
        flag=reader.text("flag", required=True),
        because=reader.choice("because", REASONS.names(), required=True),
        text=reader.text("text", required=True),
        params_hash=reader.text("params_hash"),
    )
    reader.finish()
    return entry


class _Reader(Reader):
    """One table's values read by type; `finish` records every key nobody read."""

    def __init__(
        self,
        table: Table,
        path: tuple[str, ...],
        file: str,
        unknown: list[str],
        *,
        at: Location | None = None,
    ) -> None:
        super().__init__(table, at=at)
        self.path = path
        self.file = file
        self.unknown = unknown

    def _where(self, key: str) -> str:
        return f"{self.file}: {'.'.join((*self.path, key))}"

    def _child(self, table: Table, key: str, index: int | None, at: Location) -> "_Reader":
        steps = (key,) if index is None else (key, str(index))
        return _Reader(table, (*self.path, *steps), self.file, self.unknown, at=at)

    def name_as(self, path: tuple[str, ...]) -> None:
        self.path = path

    def finish(self) -> None:
        self.unknown.extend(
            ".".join((*self.path, key)) for key in self.values if key not in self.read
        )

    def texts(self, key: str) -> list[str]:
        value = self._typed(key, TEXTS, required=True)
        if not _is_list(value) or not all(isinstance(v, str) and v for v in _items(value)):
            raise self.wrong(key, "a list of names")
        names = [cast(str, v) for v in _items(value)]
        self.chosen.update(names)
        return names

    def session_ids(self, key: str) -> tuple[str, ...]:
        value = self._typed(key, SESSION_IDS, required=True)
        ids = [value] if isinstance(value, str) else _items(value) if _is_list(value) else []
        if ids and all(isinstance(v, str) and v for v in ids):
            return tuple(cast(str, v) for v in ids)
        raise self.wrong(key, "a session id or a non-empty list of session ids")

    @overload
    def count(self, key: str, *, required: Literal[True]) -> int: ...
    @overload
    def count(self, key: str, *, required: bool = False) -> int | None: ...
    def count(self, key: str, *, required: bool = False) -> int | None:
        value = self._present(key, COUNT, required=required)
        if value is None or (is_int(value) and cast(int, value) > 0):
            return cast(int | None, value)
        raise self.wrong(key, "a whole number above 0")

    def percent(self, key: str) -> Number:
        value = self._typed(key, PERCENT, required=True)
        if _is_number(value) and 0 <= cast(float, value) <= 100:
            return cast(Number, value)
        raise self.wrong(key, "a percentage from 0 to 100")

    @overload
    def rpe(self, key: str, *, required: Literal[True]) -> Number: ...
    @overload
    def rpe(self, key: str, *, required: bool = False) -> Number | None: ...
    def rpe(self, key: str, *, required: bool = False) -> Number | None:
        value = self._present(key, RPE, required=required)
        if value is None or (_is_number(value) and 0 < cast(float, value) <= 10):
            return cast(Number | None, value)
        raise self.wrong(key, "an RPE above 0 and at most 10")

    def load(self, key: str) -> Number | None:
        value = self._typed(key, LOAD)
        if value is None or (_is_number(value) and cast(float, value) >= 0):
            return cast(Number | None, value)
        raise self.wrong(key, "a load of at least 0 in athlete units")

    def muscles(self, key: str) -> dict[str, list[str]]:
        muscles = read_muscles(self._typed(key, MUSCLES, required=True))
        if muscles is None:
            raise self.wrong(key, MUSCLES_WANTED)
        return muscles

    def true_or_false(self, key: str) -> bool:
        """A required boolean; left out, it reads as the wrong value rather than a missing key."""
        value = self._typed(key, BOOLEAN, required=True)
        if isinstance(value, bool):
            return value
        raise self.wrong(key, "true or false")

    def reps(self, key: str) -> Reps | None:
        value = self._typed(key, REPS)
        if value is None:
            return None
        if is_int(value) and cast(int, value) > 0:
            return cast(int, value)
        if _is_list(value):
            pair = _items(value)
            if len(pair) == 2 and all(is_int(n) and cast(int, n) > 0 for n in pair):
                low, high = cast(int, pair[0]), cast(int, pair[1])
                if low <= high:
                    return (low, high)
        if isinstance(value, str) and value.endswith("+") and value[:-1].isdigit():
            return value
        raise self.wrong(key, 'a rep count, a range [6, 8] or an open top "8+"')


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_list(value: object) -> bool:
    return isinstance(value, list | tuple)


def _items(value: object) -> Sequence[object]:
    return cast(Sequence[object], value)
