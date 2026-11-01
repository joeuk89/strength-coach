from pathlib import Path
from typing import Any

import pytest
from support.cli import run_coach
from support.fixture_instances import coach, instance, rebuilt

__all__ = ["instance", "rebuilt"]


def printed(registry: str) -> list[dict[str, Any]]:
    return run_coach("schema", "--registry", registry, "--full").envelope["result"]["rows"]


RECORD_KINDS = [row["name"] for row in printed("record-kinds")]
VIEWS = [row["name"] for row in printed("views")]


def record(root: Path, table: str) -> str:
    (root / "draft.toml").write_text(f"[[{table}]]\n")
    run = coach("record", "draft.toml")
    assert run.code == 1
    return run.envelope["error"]["code"]


@pytest.mark.parametrize("kind", RECORD_KINDS)
def test_the_record_parser_dispatches_on_every_printed_record_kind(
    instance: Path, kind: str
) -> None:
    assert record(instance, kind) != "unknown_key"


def test_the_record_parser_refuses_a_kind_the_registry_does_not_print(instance: Path) -> None:
    assert record(instance, "workout_plan") == "unknown_key"


@pytest.mark.parametrize("kind", RECORD_KINDS)
def test_query_ledger_reads_every_printed_record_kind(instance: Path, kind: str) -> None:
    assert coach("query", "ledger", "--kind", kind).code == 0


@pytest.mark.parametrize("view", VIEWS)
def test_query_dispatches_on_every_printed_view(instance: Path, view: str) -> None:
    kind = ("--kind", "note") if view == "ledger" else ()

    assert coach("query", view, *kind).code == 0


def test_query_refuses_a_view_the_registry_does_not_print(instance: Path) -> None:
    assert coach("query", "workouts").code == 1


def test_every_flag_the_validator_raised_is_a_printed_code_at_its_severity(
    instance: Path,
) -> None:
    severities = {row["code"]: row["severity"] for row in printed("flags")}

    raised = coach("query", "flags", "--full").envelope["result"]["rows"]

    assert raised
    assert {(f["code"], f["severity"]) for f in raised} <= set(severities.items())
