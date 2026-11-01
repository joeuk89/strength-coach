from contextlib import closing

import pytest

from coach.core.registries.agent import RECORD_KINDS, RecordKind
from coach.store.connection import open_store

# schema.md, "Ids": the prefix of each table that has one.
SCHEMA_PREFIXES = {
    "workout": "w-",
    "decision": "d-",
    "niggle": "n-",
    "niggle_event": "ne-",
    "follow_up": "f-",
    "follow_up_event": "fe-",
    "observation": "o-",
    "annotation": "a-",
    "goal": "g-",
    "milestone": "m-",
    "phase": "ph-",
    "weigh_in": "wi-",
    "sleep_night": "sn-",
    "activity": "ac-",
    "status_span": "ss-",
    "import_run": "ir-",
    "acknowledgement": "ak-",
    "program_version": "pv-",
    "week_plan": "wp-",
    "check_in": "ci-",
}


def columns_by_table() -> dict[str, set[str]]:
    with closing(open_store(":memory:")) as conn:
        tables = [t for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {t: {row[1] for row in conn.execute(f"PRAGMA table_info({t})")} for t in tables}


COLUMNS = columns_by_table()


@pytest.mark.parametrize("kind", RECORD_KINDS.entries, ids=RECORD_KINDS.names())
def test_every_record_kind_table_is_in_the_schema(kind: RecordKind) -> None:
    assert kind.store_table in COLUMNS
    if kind.event_table is not None:
        assert f"{kind.store_table}_id" in COLUMNS[kind.event_table]
    if kind.day_column is not None:
        assert kind.day_column in COLUMNS[kind.store_table]
    assert ("draft_hash" in COLUMNS[kind.store_table]) == kind.carries_draft_hash


@pytest.mark.parametrize("kind", RECORD_KINDS.entries, ids=RECORD_KINDS.names())
def test_every_id_prefix_matches_the_schema_ids_table(kind: RecordKind) -> None:
    if kind.store_table in SCHEMA_PREFIXES:
        assert kind.id_prefix == SCHEMA_PREFIXES[kind.store_table]


def test_kinds_without_a_schema_prefix() -> None:
    unlisted = {k.name: k.id_prefix for k in RECORD_KINDS.entries if k.store_table not in SCHEMA_PREFIXES}

    assert unlisted == {"note": "an-", "exercise": None}
    assert "an-" not in SCHEMA_PREFIXES.values()


def test_the_readings_and_their_day_columns() -> None:
    readings = {k.name: k.day_column for k in RECORD_KINDS.entries if k.reading}

    assert readings == {
        "weigh_in": "date",
        "sleep_night": "night",
        "activity": None,
        "status_span": "from_date",
    }
