from dataclasses import dataclass

from coach.core.registries.registry import Registry, Row


@dataclass(frozen=True)
class RecordKind:
    name: str
    store_table: str
    id_prefix: str | None
    day_column: str | None = None
    event_table: str | None = None
    reading: bool = False
    carries_draft_hash: bool = True
    check_in_only: bool = False

    def describe(self) -> Row:
        return {"name": self.name, "table": f"[[{self.name}]]", "check_in_only": self.check_in_only}


# docs/spec/verbs.md, "Record kinds"; tables and prefixes from schema.md, "Ids" and "Record kinds
# to tables". A note's `an-` is not in that table, since `n-` is a niggle's.
RECORD_KINDS = Registry(
    "record-kinds",
    (
        RecordKind("niggle", "niggle", "n-", event_table="niggle_event"),
        RecordKind("followup", "follow_up", "f-", event_table="follow_up_event"),
        RecordKind("decision", "decision", "d-"),
        RecordKind("annotation", "annotation", "a-"),
        RecordKind("note", "athlete_note", "an-"),
        RecordKind("workout", "workout", "w-"),
        RecordKind("weigh_in", "weigh_in", "wi-", day_column="date", reading=True),
        RecordKind("sleep_night", "sleep_night", "sn-", day_column="night", reading=True),
        RecordKind("activity", "activity", "ac-", reading=True),
        RecordKind("status_span", "status_span", "ss-", day_column="from_date", reading=True),
        RecordKind("exercise", "exercise", None, carries_draft_hash=False),
        RecordKind("observation", "observation", "o-", check_in_only=True),
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
