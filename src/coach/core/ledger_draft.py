import datetime
import hashlib
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from coach.core.errors import Invalid
from coach.core.ref import KEY, Ref
from coach.core.registries.agent import RECORD_KINDS
from coach.core.registries.log import STATUS_SPAN_KINDS
from coach.core.registries.program import EQUIPMENT_KINDS, LOAD_MODES, SET_TYPES
from coach.core.registries.registry import Entry, Registry

type Table = Mapping[str, object]

NOTE_ABOUT = ("planned_session", "exercise", "niggle", "follow_up")
EXERCISE_IDENTITY = ("name", "pattern", "muscles")
EXERCISE_EDITABLE = (
    "load_mode",
    "equipment_kind",
    "hevy_title",
    "hevy_exercise_type",
    "hevy_equipment",
    "hevy_muscle_group",
    "hevy_template_id",
)
# cutover.md, "The exercise record": what a new Exercise declares.
NEW_EXERCISE_REQUIRED = (
    *EXERCISE_IDENTITY,
    "load_mode",
    "equipment_kind",
    "hevy_template_id",
    "hevy_title",
)


@dataclass(frozen=True)
class NoteRecord:
    date: datetime.date
    text: str
    about: Ref | None = None
    key: str | None = None


@dataclass(frozen=True)
class WeighInRecord:
    """A reading, or with `withdraws` the withdrawal of one: the service copies its columns."""

    date: datetime.date | None = None
    kg: float | None = None
    withdraws: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class SleepNightRecord:
    night: datetime.date | None = None
    hours: float | None = None
    withdraws: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class ActivityRecord:
    date: datetime.date
    kind: str
    minutes: int
    rpe: float
    quality: bool
    distance_km: float | None = None
    text: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class StatusSpanRecord:
    kind: str | None = None
    from_date: datetime.date | None = None
    to_date: datetime.date | None = None
    text: str | None = None
    withdraws: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class LoggedSetRecord:
    exercise: str
    set_type: str = "working"
    weight_kg: float | None = None
    reps: int | None = None
    duration_s: int | None = None
    distance_m: float | None = None
    rpe: float | None = None
    note: str | None = None


@dataclass(frozen=True)
class WorkoutRecord:
    date: datetime.date
    title: str | None = None
    session_id: str | None = None
    minutes: int | None = None
    session_rpe: float | None = None
    notes: str | None = None
    sets: tuple[LoggedSetRecord, ...] = ()
    key: str | None = None


@dataclass(frozen=True)
class ExerciseRecord:
    """An edit to the Exercise `id`, or a new one: `fields` holds only the columns the file gave."""

    id: str
    fields: Mapping[str, object] = field(default_factory=lambda: {})
    key: str | None = None


type LedgerRecord = (
    NoteRecord
    | WeighInRecord
    | SleepNightRecord
    | ActivityRecord
    | StatusSpanRecord
    | WorkoutRecord
    | ExerciseRecord
)


@dataclass(frozen=True)
class LedgerDraft:
    hash: str
    file: str
    records: tuple[LedgerRecord, ...]

    def keys(self) -> dict[str, int]:
        """Each Draft-local key and the index of the record carrying it."""
        return {r.key: i for i, r in enumerate(self.records) if r.key is not None}


def kind_of(record: LedgerRecord) -> str:
    return KIND_OF[type(record)]


def draft_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse_ledger_draft(data: bytes, *, verb: str, file: str) -> LedgerDraft:
    """A ledger Draft as typed records, one array of tables per kind (verbs.md, "Record kinds")."""
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise Invalid("invalid_argument", f"{file} is not valid TOML: {error}") from error
    records: list[LedgerRecord] = []
    for name, value in document.items():
        parser = _parser(name, verb)
        if not isinstance(value, list) or not all(
            isinstance(t, dict) for t in cast(list[object], value)
        ):
            raise Invalid(
                "invalid_argument", f"{file}: write {name} as an array of tables, [[{name}]]"
            )
        for index, table in enumerate(cast(list[Table], value), start=1):
            records.append(parser(_Fields(table, f"{file}: [[{name}]] #{index}")))
    draft = LedgerDraft(draft_hash(data), file, tuple(records))
    _check_keys(draft)
    return draft


def _parser(name: str, verb: str) -> "Callable[[_Fields], LedgerRecord]":
    if name not in RECORD_KINDS:
        raise Invalid(
            "unknown_key",
            f"[[{name}]] is not a record kind; `coach schema --registry record-kinds` lists them",
        )
    if RECORD_KINDS.get(name).check_in_only and verb != "checkin record":
        raise Invalid(
            "record_kind_not_allowed",
            f"[[{name}]] is recorded only in a check-in file, not by `coach {verb}`",
        )
    parser = PARSERS.get(name)
    if parser is None:
        raise Invalid("invalid_argument", f"this engine does not record [[{name}]] yet")
    return parser


def _check_keys(draft: LedgerDraft) -> None:
    seen: set[str] = set()
    for record in draft.records:
        if record.key is None:
            continue
        if not KEY.fullmatch(record.key):
            raise Invalid("invalid_argument", f"{draft.file}: key {record.key!r} is not a word")
        if record.key in seen:
            raise Invalid("invalid_argument", f"{draft.file}: key {record.key!r} is used twice")
        seen.add(record.key)
    keys = draft.keys()
    for ref in local_refs(draft):
        index = keys.get(cast(str, ref.local_key))
        if index is None or kind_of(draft.records[index]) != ref.record_kind:
            raise Invalid(
                "draft_ref_unresolved",
                f"{draft.file}: {ref} names no [[{ref.record_kind}]] with key = "
                f"{ref.local_key!r} in the file",
            )


def local_refs(draft: LedgerDraft) -> list[Ref]:
    return [
        r.about
        for r in draft.records
        if isinstance(r, NoteRecord) and r.about and r.about.local_key
    ]


class _Fields:
    """Reads one table's values by type, and refuses any key nobody read."""

    def __init__(self, table: Table, where: str) -> None:
        self.table = table
        self.where = where
        self.read: set[str] = set()

    def has(self, name: str) -> bool:
        return name in self.table

    def raw(self, name: str) -> object | None:
        self.read.add(name)
        return self.table.get(name)

    def text(self, name: str, *, required: bool = False) -> str | None:
        value = self._value(name, required)
        if value is None or (isinstance(value, str) and value):
            return value
        raise self.wrong(name, "a non-empty string")

    def number(self, name: str, *, required: bool = False, low: float = 0.0) -> float | None:
        value = self._value(name, required)
        if value is None:
            return None
        if isinstance(value, int | float) and not isinstance(value, bool) and value >= low:
            return float(value)
        raise self.wrong(name, f"a number of at least {low:g}")

    def integer(self, name: str, *, required: bool = False) -> int | None:
        value = self._value(name, required)
        if value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0):
            return value
        raise self.wrong(name, "a whole number of at least 0")

    def boolean(self, name: str, *, required: bool = False) -> bool | None:
        value = self._value(name, required)
        if value is None or isinstance(value, bool):
            return value
        raise self.wrong(name, "true or false")

    def date(self, name: str, *, required: bool = False) -> datetime.date | None:
        value = self._value(name, required)
        if value is None or type(value) is datetime.date:
            return value
        if isinstance(value, str):
            try:
                return datetime.date.fromisoformat(value)
            except ValueError:
                pass
        raise self.wrong(name, "a date, 2026-10-30")

    def term(self, name: str, registry: Registry[Entry], *, required: bool = False) -> str | None:
        value = self.text(name, required=required)
        if value is None or value in registry:
            return value
        raise self.wrong(name, f"one of {', '.join(registry.names())}")

    def ref(self, name: str, kinds: tuple[str, ...]) -> Ref | None:
        value = self.text(name)
        if value is None:
            return None
        ref = Ref.parse(value)
        if ref.kind not in kinds:
            raise self.wrong(name, f"a ref to one of {', '.join(kinds)}")
        return ref

    def tables(self, name: str) -> list["_Fields"]:
        value = self.raw(name)
        if value is None:
            return []
        if not isinstance(value, list) or not all(
            isinstance(t, dict) for t in cast(list[object], value)
        ):
            raise self.wrong(name, "an array of tables")
        return [
            _Fields(t, f"{self.where} {name} #{i}")
            for i, t in enumerate(cast(list[Table], value), 1)
        ]

    def key(self) -> str | None:
        return self.text("key")

    def done[R](self, record: R) -> R:
        unknown = sorted(set(self.table) - self.read)
        if unknown:
            raise Invalid("unknown_key", f"{self.where}: unknown key {', '.join(unknown)}")
        return record

    def only(self, *names: str) -> None:
        extra = sorted(set(self.table) - set(names))
        if extra:
            raise Invalid(
                "invalid_argument",
                f"{self.where}: a withdrawing row carries only withdraws; drop {', '.join(extra)}",
            )

    def _value(self, name: str, required: bool) -> object | None:
        value = self.raw(name)
        if value is None and required:
            raise Invalid("invalid_argument", f"{self.where}: {name} is required")
        return value

    def wrong(self, name: str, wanted: str) -> Invalid:
        return Invalid("invalid_argument", f"{self.where}: {name} must be {wanted}")


def _note(f: _Fields) -> NoteRecord:
    return f.done(
        NoteRecord(
            date=_req(f.date("date", required=True)),
            text=_req(f.text("text", required=True)),
            about=f.ref("about", NOTE_ABOUT),
            key=f.key(),
        )
    )


def _weigh_in(f: _Fields) -> WeighInRecord:
    if f.has("withdraws"):
        f.only("withdraws", "key")
        return f.done(WeighInRecord(withdraws=f.text("withdraws"), key=f.key()))
    return f.done(
        WeighInRecord(
            date=f.date("date", required=True), kg=f.number("kg", required=True), key=f.key()
        )
    )


def _sleep_night(f: _Fields) -> SleepNightRecord:
    if f.has("withdraws"):
        f.only("withdraws", "key")
        return f.done(SleepNightRecord(withdraws=f.text("withdraws"), key=f.key()))
    hours = _req(f.number("hours", required=True))
    if hours > 24:
        raise f.wrong("hours", "at most 24")
    return f.done(SleepNightRecord(night=f.date("night", required=True), hours=hours, key=f.key()))


def _activity(f: _Fields) -> ActivityRecord:
    return f.done(
        ActivityRecord(
            date=_req(f.date("date", required=True)),
            kind=_req(f.text("kind", required=True)),
            minutes=_req(f.integer("minutes", required=True)),
            rpe=_req(f.number("rpe", required=True)),
            quality=_req(f.boolean("quality", required=True)),
            distance_km=f.number("distance_km"),
            text=f.text("text"),
            key=f.key(),
        )
    )


def _status_span(f: _Fields) -> StatusSpanRecord:
    if f.has("withdraws"):
        f.only("withdraws", "key")
        return f.done(StatusSpanRecord(withdraws=f.text("withdraws"), key=f.key()))
    from_date = f.date("from_date", required=True)
    to_date = f.date("to_date")
    if from_date and to_date and to_date < from_date:
        raise f.wrong("to_date", f"on or after from_date {from_date}")
    return f.done(
        StatusSpanRecord(
            kind=f.term("kind", STATUS_SPAN_KINDS, required=True),
            from_date=from_date,
            to_date=to_date,
            text=f.text("text"),
            key=f.key(),
        )
    )


def _logged_set(f: _Fields) -> LoggedSetRecord:
    return f.done(
        LoggedSetRecord(
            exercise=_req(f.text("exercise", required=True)),
            set_type=f.term("set_type", SET_TYPES) or "working",
            weight_kg=f.number("weight_kg"),
            reps=f.integer("reps"),
            duration_s=f.integer("duration_s"),
            distance_m=f.number("distance_m"),
            rpe=f.number("rpe"),
            note=f.text("note"),
        )
    )


def _workout(f: _Fields) -> WorkoutRecord:
    return f.done(
        WorkoutRecord(
            date=_req(f.date("date", required=True)),
            title=f.text("title"),
            session_id=f.text("session_id"),
            minutes=f.integer("minutes"),
            session_rpe=f.number("session_rpe"),
            notes=f.text("notes"),
            sets=tuple(_logged_set(s) for s in f.tables("sets")),
            key=f.key(),
        )
    )


def _exercise(f: _Fields) -> ExerciseRecord:
    id_ = _req(f.text("id", required=True))
    fields: dict[str, object] = {}
    for name in ("name", "pattern", *EXERCISE_EDITABLE):
        if name == "load_mode":
            value = f.term(name, LOAD_MODES)
        elif name == "equipment_kind":
            value = f.term(name, EQUIPMENT_KINDS)
        else:
            value = f.text(name)
        if value is not None:
            fields[name] = value
    muscles = f.raw("muscles")
    if muscles is not None:
        fields["muscles"] = _muscles(muscles, f)
    return f.done(ExerciseRecord(id=id_, fields=fields, key=f.key()))


def _muscles(value: object, f: _Fields) -> dict[str, list[str]]:
    wanted = "a table {primary = [...], secondary = [...]} of muscle names"
    if not isinstance(value, dict):
        raise f.wrong("muscles", wanted)
    table = cast(dict[str, object], value)
    if set(table) != {"primary", "secondary"}:
        raise f.wrong("muscles", wanted)
    muscles: dict[str, list[str]] = {}
    for part in ("primary", "secondary"):
        names = table[part]
        if not isinstance(names, list) or not all(
            isinstance(n, str) for n in cast(list[object], names)
        ):
            raise f.wrong("muscles", wanted)
        muscles[part] = list(cast(list[str], names))
    return muscles


def _req[T](value: T | None) -> T:
    assert value is not None
    return value


PARSERS: dict[str, Callable[[_Fields], LedgerRecord]] = {
    "note": _note,
    "weigh_in": _weigh_in,
    "sleep_night": _sleep_night,
    "activity": _activity,
    "status_span": _status_span,
    "workout": _workout,
    "exercise": _exercise,
}
KIND_OF: dict[type, str] = {
    NoteRecord: "note",
    WeighInRecord: "weigh_in",
    SleepNightRecord: "sleep_night",
    ActivityRecord: "activity",
    StatusSpanRecord: "status_span",
    WorkoutRecord: "workout",
    ExerciseRecord: "exercise",
}
