from dataclasses import dataclass
from typing import Protocol

type Row = dict[str, object]


class Entry(Protocol):
    @property
    def name(self) -> str: ...

    def describe(self) -> Row: ...


@dataclass(frozen=True)
class Term:
    """An entry that is its name and nothing else."""

    name: str

    def describe(self) -> Row:
        return {"name": self.name}


@dataclass(frozen=True)
class Registry[E: Entry]:
    name: str
    entries: tuple[E, ...]

    def __post_init__(self) -> None:
        names = self.names()
        if len(names) != len(set(names)):
            raise ValueError(f"registry {self.name} repeats a name")

    def names(self) -> tuple[str, ...]:
        return tuple(entry.name for entry in self.entries)

    def get(self, name: str) -> E:
        for entry in self.entries:
            if entry.name == name:
                return entry
        raise KeyError(f"{self.name} has no {name!r}")

    def __contains__(self, name: object) -> bool:
        return name in self.names()

    def rows(self) -> list[Row]:
        return [entry.describe() for entry in self.entries]


def terms(name: str, *values: str) -> Registry[Term]:
    return Registry(name, tuple(Term(value) for value in values))
