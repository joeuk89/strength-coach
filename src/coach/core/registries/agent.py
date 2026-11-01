from dataclasses import dataclass

from coach.core.registries.registry import Registry, Row


@dataclass(frozen=True)
class RecordKind:
    name: str
    check_in_only: bool = False

    def describe(self) -> Row:
        return {"name": self.name, "table": f"[[{self.name}]]", "check_in_only": self.check_in_only}


# docs/spec/verbs.md, "Record kinds".
RECORD_KINDS = Registry(
    "record-kinds",
    (
        RecordKind("niggle"),
        RecordKind("followup"),
        RecordKind("decision"),
        RecordKind("annotation"),
        RecordKind("note"),
        RecordKind("workout"),
        RecordKind("weigh_in"),
        RecordKind("sleep_night"),
        RecordKind("activity"),
        RecordKind("status_span"),
        RecordKind("exercise"),
        RecordKind("observation", check_in_only=True),
    ),
)


@dataclass(frozen=True)
class View:
    name: str
    params: tuple[str, ...]

    def describe(self) -> Row:
        return {"name": self.name, "params": list(self.params)}


# docs/spec/verbs.md, "Read views".
VIEWS = Registry(
    "views",
    (
        View("exposures", ("--exercise", "--since", "--last")),
        View("readings", ("--kind", "--last")),
        View("flags", ("--code", "--severity", "--scope", "--summary", "--draft")),
        View("lines", ("--exercise", "--session", "--date", "--changed", "--draft")),
        View("routines", ()),
        View("ledger", ("--kind", "--id", "--open")),
    ),
)
