from pathlib import Path

from support.check_lists import COLUMN_REGISTRIES, check_lists, mismatches

from coach.core import registries

SCHEMA_SQL = (Path(__file__).resolve().parents[2] / "src/coach/store/schema.sql").read_text(
    encoding="utf-8"
)


def registry_names(name: str) -> tuple[str, ...] | None:
    found = registries.find(name)
    return found.names() if found else None


def test_every_check_list_equals_its_registry() -> None:
    assert mismatches(SCHEMA_SQL, registry_names) == []


def test_the_check_lists_are_found() -> None:
    lists = check_lists(SCHEMA_SQL)

    assert lists[("decision", "because")] == (
        "pain",
        "kit",
        "stall",
        "fatigue",
        "schedule",
        "athlete_request",
        "coach_judgement",
        "progress",
    )
    assert lists[("tombstone", "source")] == ("event", "full")
    assert set(COLUMN_REGISTRIES) <= set(lists)


def test_a_value_added_to_a_registry_and_not_the_ddl_fails() -> None:
    def with_extra_reason(name: str) -> tuple[str, ...] | None:
        names = registry_names(name)
        return (*names, "boredom") if name == "reasons" and names else names

    problems = mismatches(SCHEMA_SQL, with_extra_reason)

    assert len(problems) == 4
    assert all("only in the registry ['boredom']" in p for p in problems)


def test_a_value_added_to_the_ddl_and_not_the_registry_fails() -> None:
    planted = SCHEMA_SQL.replace("'gone','back'", "'gone','back','lost'")

    assert mismatches(planted, registry_names) == [
        "tombstone.kind differs from tombstone-kinds: "
        "only in the DDL ['lost'], only in the registry []"
    ]


def test_a_new_kind_column_without_a_registry_fails() -> None:
    planted = (
        SCHEMA_SQL + "\nCREATE TABLE shelf (\n  kind TEXT NOT NULL CHECK (kind IN ('a','b'))\n);\n"
    )

    assert mismatches(planted, registry_names) == ["shelf.kind has a CHECK list and no registry"]
