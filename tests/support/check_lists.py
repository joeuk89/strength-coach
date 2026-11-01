"""Every CHECK list in `schema.sql` over a registry-backed column, against its registry."""

import re
from collections.abc import Callable, Mapping

CHECKED_COLUMNS = frozenset({"kind", "status", "because", "source"})
TABLE = re.compile(r"^CREATE TABLE (\w+)")
CHECK = re.compile(r"^\s*(\w+)\s+TEXT\b.*?CHECK \(\1 IN \(([^)]*)\)\)")

COLUMN_REGISTRIES: Mapping[tuple[str, str], str] = {
    ("exercise", "load_mode"): "load-modes",
    ("exercise", "equipment_kind"): "equipment-kinds",
    ("exercise", "source"): "exercise-sources",
    ("program_version", "kind"): "version-kinds",
    ("program_session", "kind"): "session-kinds",
    ("acknowledgement", "because"): "reasons",
    ("week_plan", "status"): "plan-statuses",
    ("override", "kind"): "override-kinds",
    ("override", "because"): "reasons",
    ("workout", "source"): "workout-sources",
    ("logged_set", "set_type"): "set-types",
    ("tombstone", "kind"): "tombstone-kinds",
    ("tombstone", "source"): "import-pulls",
    ("annotation", "kind"): "annotation-kinds",
    ("annotation", "because"): "reasons",
    ("weigh_in", "source"): "weigh-in-sources",
    ("sleep_night", "source"): "sleep-night-sources",
    ("status_span", "kind"): "status-span-kinds",
    ("check_in", "status"): "check-in-statuses",
    ("decision", "kind"): "decision-kinds",
    ("decision", "because"): "reasons",
    ("niggle_event", "status"): "niggle-statuses",
    ("niggle_constraint", "kind"): "constraint-kinds",
    ("follow_up_event", "kind"): "follow-up-events",
    ("goal", "kind"): "goal-kinds",
    ("goal", "status"): "goal-statuses",
    ("phase", "kind"): "phase",
    ("routine_map", "status"): "routine-statuses",
    ("import_run", "kind"): "import-pulls",
}


def check_lists(sql: str) -> dict[tuple[str, str], tuple[str, ...]]:
    found: dict[tuple[str, str], tuple[str, ...]] = {}
    table = ""
    for line in sql.splitlines():
        if match := TABLE.match(line):
            table = match.group(1)
        elif match := CHECK.match(line):
            values = tuple(v.strip().strip("'") for v in match.group(2).split(","))
            found[(table, match.group(1))] = values
    return found


def mismatches(sql: str, registry_names: Callable[[str], tuple[str, ...] | None]) -> list[str]:
    problems: list[str] = []
    for (table, column), values in check_lists(sql).items():
        name = COLUMN_REGISTRIES.get((table, column))
        if name is None:
            if column in CHECKED_COLUMNS:
                problems.append(f"{table}.{column} has a CHECK list and no registry")
            continue
        names = registry_names(name)
        if names is None:
            problems.append(f"{table}.{column}: no registry {name!r}")
        elif set(values) != set(names):
            only_ddl = sorted(set(values) - set(names))
            only_registry = sorted(set(names) - set(values))
            problems.append(
                f"{table}.{column} differs from {name}: "
                f"only in the DDL {only_ddl}, only in the registry {only_registry}"
            )
    return problems
