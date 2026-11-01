"""The diff between two versions, derived from their forms and never stored (ADR 0015)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from coach.core.program.form import ProgramForm

VERSION_FIELDS = ("name", "emphasis", "location", "schedule", "dose", "deload", "exercise")

type Document = Mapping[str, object]


@dataclass(frozen=True)
class LineChange:
    exercise: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class SessionChange:
    id: str
    fields: tuple[str, ...]
    lines_added: tuple[str, ...]
    lines_removed: tuple[str, ...]
    lines_changed: tuple[LineChange, ...]


@dataclass(frozen=True)
class ProgramDiff:
    version: Mapping[str, tuple[object, object]]
    sessions_added: tuple[str, ...]
    sessions_removed: tuple[str, ...]
    sessions_changed: tuple[SessionChange, ...]
    filled: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not (
            self.version or self.sessions_added or self.sessions_removed or self.sessions_changed
        )

    def to_json(self) -> dict[str, object]:
        version: dict[str, object] = {}
        for name, (before, after) in self.version.items():
            entry: dict[str, object] = {"from": before, "to": after}
            if name in self.filled:
                entry["filled"] = True
            version[name] = entry
        return {
            "empty": self.empty,
            "version": version,
            "sessions": {
                "added": list(self.sessions_added),
                "removed": list(self.sessions_removed),
                "changed": [
                    {
                        "id": change.id,
                        "fields": list(change.fields),
                        "lines": {
                            "added": list(change.lines_added),
                            "removed": list(change.lines_removed),
                            "changed": [
                                {"exercise": line.exercise, "fields": list(line.fields)}
                                for line in change.lines_changed
                            ],
                        },
                    }
                    for change in self.sessions_changed
                ],
            },
            "filled": list(self.filled),
        }


def diff(
    previous: ProgramForm | None, current: ProgramForm, filled: Sequence[str] = ()
) -> ProgramDiff:
    before = previous.to_document() if previous else {}
    after = current.to_document()
    version = {
        name: (before.get(name), after.get(name))
        for name in VERSION_FIELDS
        if before.get(name) != after.get(name)
    }
    added, removed, changed = _keyed_changes(
        _by(before.get("session"), "id"), _by(after.get("session"), "id")
    )
    return ProgramDiff(
        version=version,
        sessions_added=added,
        sessions_removed=removed,
        sessions_changed=tuple(
            change for old, new in changed if (change := _session_change(old, new)) is not None
        ),
        filled=tuple(filled),
    )


def _session_change(old: Document, new: Document) -> SessionChange | None:
    added, removed, changed = _keyed_changes(
        _by(old.get("line"), "exercise"), _by(new.get("line"), "exercise")
    )
    lines = tuple(
        LineChange(str(b["exercise"]), fields)
        for a, b in changed
        if (fields := _fields_changed(a, b, ("exercise",)))
    )
    fields = _fields_changed(old, new, ("id", "line"))
    if not (fields or added or removed or lines):
        return None
    return SessionChange(str(new["id"]), fields, added, removed, lines)


def _keyed_changes(
    before: Mapping[str, Document], after: Mapping[str, Document]
) -> tuple[tuple[str, ...], tuple[str, ...], list[tuple[Document, Document]]]:
    added = tuple(key for key in after if key not in before)
    removed = tuple(key for key in before if key not in after)
    both = [(before[key], after[key]) for key in after if key in before]
    return added, removed, both


def _fields_changed(old: Document, new: Document, ignore: tuple[str, ...]) -> tuple[str, ...]:
    names = dict.fromkeys([*old, *new])
    return tuple(n for n in names if n not in ignore and old.get(n) != new.get(n))


def _by(items: object, key: str) -> dict[str, Document]:
    documents = cast(Sequence[Document], items or [])
    return {str(item[key]): item for item in documents}
