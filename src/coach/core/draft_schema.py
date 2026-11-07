"""A Draft's JSON Schema, recorded from its parser: while a recording runs, each typed read on a
Draft reader notes the key, its schema and whether it was required, under the table it sits in.
Running the real parser over Drafts that reach every table gives the schema with no second
source of truth."""

import copy
from collections.abc import Callable, Iterable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import cache
from typing import cast

type Json = dict[str, object]
type Path = tuple[str, ...]


@dataclass(frozen=True)
class Named:
    """A key the document chose, such as an exercise id: its value shape is the table's
    `additionalProperties`."""

    key: str


type Step = str | int | Named
type Location = tuple[Step, ...]
type Visit = tuple[int, Location]

ITEMS = "[]"
ANY_KEY = "*"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
TABLE: Json = {"type": "object"}
TEXT: Json = {"type": "string", "minLength": 1}
DATE: Json = {"type": "string", "format": "date"}
BOOLEAN: Json = {"type": "boolean"}
TEXTS: Json = {"type": "array", "items": TEXT}


def tables(*, at_least_one: bool = False) -> Json:
    return {"type": "array", "minItems": 1} if at_least_one else {"type": "array"}


def enum(values: Iterable[str]) -> Json:
    return {"enum": list(values)}


def path_of(location: Location) -> Path:
    return tuple(
        ITEMS if isinstance(step, int) else ANY_KEY if isinstance(step, Named) else step
        for step in location
    )


@dataclass
class _Key:
    fragments: list[Json] = field(default_factory=lambda: [])
    required: set[Visit] = field(default_factory=lambda: set())
    values: set[str] = field(default_factory=lambda: set())
    loose: bool = False
    tested: bool = False


@dataclass
class _Node:
    visits: set[Visit] = field(default_factory=lambda: set())
    keys: dict[str, _Key] = field(default_factory=lambda: {})
    named: _Key | None = None


class Recording:
    def __init__(self) -> None:
        self._nodes: dict[Path, _Node] = {}
        self._run = 0
        self._placed: dict[int, Location] = {}

    def next_run(self) -> None:
        self._run += 1
        self._placed = {}

    def visit(self, table: object, at: Location | None) -> Location:
        """Where a reader over `table` sits: `at`, else where a read placed it, else the top."""
        location = at if at is not None else self._placed.get(id(table), ())
        self._placed[id(table)] = location
        self._node(path_of(location)).visits.add((self._run, location))
        return location

    def place(self, value: object, at: Location) -> None:
        """Remember where a read value's tables sit, for a reader built over them later."""
        if isinstance(value, dict):
            self._placed[id(cast(object, value))] = at
        elif isinstance(value, list | tuple):
            for index, item in enumerate(cast(Iterable[object], value), start=1):
                if isinstance(item, dict):
                    self._placed[id(cast(object, item))] = (*at, index)

    def note(
        self,
        at: Location,
        key: Step,
        fragment: Json | None,
        *,
        required: bool = False,
        value: object = None,
        presence: bool = False,
    ) -> None:
        """One read: `fragment` None reads any value, or with `presence` only tests the key."""
        node = self._node(path_of(at))
        if isinstance(key, Named):
            node.named = node.named or _Key()
            entry = node.named
        else:
            entry = node.keys.setdefault(str(key), _Key())
        visit = (self._run, at)
        if fragment is None:
            entry.loose = entry.loose or not presence
            entry.tested = entry.tested or presence
        else:
            if fragment not in entry.fragments:
                entry.fragments.append(fragment)
            if required:
                entry.required.add(visit)
            if isinstance(value, str):
                entry.values.add(value)

    def values(self, at: Path, key: str) -> set[str]:
        node = self._nodes.get(at)
        entry = node.keys.get(key) if node else None
        return set(entry.values) if entry else set()

    def paths(self) -> set[Path]:
        """Every key path a read named."""
        found: set[Path] = set()
        for path, node in self._nodes.items():
            found.update((*path, key) for key in node.keys)
            if node.named is not None:
                found.add((*path, ANY_KEY))
        return found

    def unreached(self) -> list[str]:
        """The tables a read named that no recorded document entered."""
        missing: list[str] = []
        for path, node in self._nodes.items():
            for key, entry in node.keys.items():
                if self._unreached(path, key, entry):
                    missing.append(".".join((*path, key)))
        return sorted(missing)

    def schema(
        self, at: Path = (), replace: Mapping[Path, Callable[[Json], Json]] | None = None
    ) -> Json:
        """The table at `at` as JSON Schema; `replace` rewrites the recorded shape of a table."""
        node = self._nodes.get(at, _Node())
        properties: Json = {
            key: self._property(at, key, entry, replace or {}) for key, entry in node.keys.items()
        }
        required = [
            key
            for key, entry in node.keys.items()
            if node.visits <= entry.required and not entry.tested
        ]
        named: object = False
        if node.named is not None:
            named = self._property(at, ANY_KEY, node.named, replace or {})
        shape: Json = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": named,
        }
        rewrite = (replace or {}).get(at)
        return rewrite(shape) if rewrite else shape

    def _property(
        self, at: Path, key: str, entry: _Key, replace: Mapping[Path, Callable[[Json], Json]]
    ) -> Json:
        shapes: list[Json] = []
        for fragment in entry.fragments:
            shape = self._filled(at, key, fragment, replace)
            if shape not in shapes:
                shapes.append(shape)
        if not shapes:
            return self._read_elsewhere(at, key, replace)
        if len(shapes) == 1:
            return shapes[0]
        return {"anyOf": shapes}

    def _read_elsewhere(
        self, at: Path, key: str, replace: Mapping[Path, Callable[[Json], Json]]
    ) -> Json:
        """A value read whole and handed to another reader: its shape is that reader's."""
        if (*at, key, ITEMS) in self._nodes:
            return {"type": "array", "items": self.schema((*at, key, ITEMS), replace)}
        if (*at, key) in self._nodes:
            return self.schema((*at, key), replace)
        return {}

    def _filled(
        self, at: Path, key: str, fragment: Json, replace: Mapping[Path, Callable[[Json], Json]]
    ) -> Json:
        if fragment == TABLE and (*at, key) in self._nodes:
            return self.schema((*at, key), replace)
        if fragment.get("type") == "array" and "items" not in fragment:
            items = (*at, key, ITEMS)
            return fragment | {"items": self.schema(items, replace) if items in self._nodes else {}}
        return fragment

    def _unreached(self, at: Path, key: str, entry: _Key) -> bool:
        if not entry.fragments:
            return not entry.loose
        for fragment in entry.fragments:
            if fragment == TABLE and (*at, key) not in self._nodes:
                return True
            if (
                fragment.get("type") == "array"
                and "items" not in fragment
                and (*at, key, ITEMS) not in self._nodes
            ):
                return True
        return False

    def _node(self, path: Path) -> _Node:
        return self._nodes.setdefault(path, _Node())


_CURRENT: ContextVar[Recording | None] = ContextVar("draft_recording", default=None)


def current() -> Recording | None:
    return _CURRENT.get()


def record(read: Callable[[bytes], object], documents: Iterable[str]) -> Recording:
    """Run `read` over each document under one recording."""
    found = Recording()
    token = _CURRENT.set(found)
    try:
        for document in documents:
            found.next_run()
            read(document.encode("utf-8"))
    finally:
        _CURRENT.reset(token)
    return found


def as_recorded(recording: Recording) -> Json:
    return recording.schema()


@dataclass(frozen=True)
class DraftKind:
    """A Draft a verb reads: its parser, one minimal example, and the coverage Drafts that
    with the example reach every table and branch the parser reads. `shaped` turns the
    recording into the schema, where a registry states a shape the parser reads loosely."""

    kind: str
    read: Callable[[bytes], object]
    example: str
    coverage: tuple[str, ...]
    shaped: Callable[[Recording], Json] = as_recorded

    def recording(self) -> Recording:
        return record(self.read, (self.example, *self.coverage))

    def describe(self) -> Json:
        """What `coach schema <verb>` shows of the Draft."""
        return copy.deepcopy(_described(self))


@cache
def _described(kind: DraftKind) -> Json:
    schema = {"$schema": DIALECT, **kind.shaped(kind.recording())}
    return {"kind": kind.kind, "schema": schema, "example": kind.example}
