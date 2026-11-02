import tomllib
from pathlib import Path
from typing import Any

from support.fixture_instances import coach, instance, rebuilt

from coach.cli.envelope import BUDGET_BYTES

__all__ = ["instance", "rebuilt"]

COUNTS = {
    "rotation_unconfirmed": 1,
    "stall_streak": 10,
    "unexplained_drift": 10,
    "offgrid_anchor_ignored": 1,
}


def draft_hashes(draft: Path) -> dict[str, str]:
    """Each flag key in the Draft's [[flag]] tables, week and line, with its params hash."""
    document: Any = tomllib.loads(draft.read_text())
    tables = [
        *document["flag"],
        *(flag for s in document["session"] for line in s["line"] for flag in line["flag"]),
    ]
    return {table["key"]: table["params_hash"] for table in tables}


def grouped_hashes(rows: Any) -> dict[str, str]:
    return {entry["key"]: entry["params_hash"] for row in rows for entry in row["keys"]}


def test_plan_draft_lists_every_flag_code_with_its_count_and_every_key(instance: Path) -> None:
    run = coach("plan", "draft")

    result = run.envelope["result"]
    hashes = draft_hashes(instance / result["path"])
    assert len(run.stdout.encode("utf-8")) <= BUDGET_BYTES
    assert {row["code"]: row["count"] for row in result["flags"]} == COUNTS
    assert (result["flag_count"], result["flags_truncated"]) == (22, False)
    assert result["flags"][0] == {
        "code": "rotation_unconfirmed",
        "severity": "violation",
        "count": 1,
        "keys": [
            {
                "key": "rotation_unconfirmed@week:2026-11-02",
                "params_hash": hashes["rotation_unconfirmed@week:2026-11-02"],
            }
        ],
    }
    assert len(grouped_hashes(result["flags"])) == 22
    assert hashes.items() <= grouped_hashes(result["flags"]).items()
    assert all(
        entry["key"].startswith(row["code"] + "@")
        for row in result["flags"]
        for entry in row["keys"]
    )
    assert all(set(row) == {"code", "severity", "count", "keys"} for row in result["flags"])


def test_query_flags_on_the_draft_returns_the_rows_plan_draft_lists(instance: Path) -> None:
    drafted = coach("plan", "draft").envelope["result"]

    result = coach("query", "flags", "--draft", drafted["path"]).envelope["result"]

    assert result["rows"] == drafted["flags"]
    assert (result["count"], result["truncated"]) == (4, False)


def test_query_flags_by_code_returns_the_flat_rows_with_their_messages(instance: Path) -> None:
    path = coach("plan", "draft").envelope["result"]["path"]

    result = coach("query", "flags", "--draft", path, "--code", "offgrid_anchor_ignored")

    [row] = result.envelope["result"]["rows"]
    assert row["code"] == "offgrid_anchor_ignored"
    assert row["key"].startswith("offgrid_anchor_ignored@line:2026-11-02/")
    assert row["message"]


def test_query_flags_full_returns_every_flat_row(instance: Path) -> None:
    path = coach("plan", "draft").envelope["result"]["path"]

    result = coach("query", "flags", "--draft", path, "--full").envelope["result"]

    assert (result["count"], result["truncated"], len(result["rows"])) == (22, False, 22)
    assert all("message" in row and "keys" not in row for row in result["rows"])


def test_query_flags_summary_counts_by_code_and_severity(instance: Path) -> None:
    path = coach("plan", "draft").envelope["result"]["path"]

    result = coach("query", "flags", "--draft", path, "--summary").envelope["result"]

    assert result["rows"] == [
        {"code": "offgrid_anchor_ignored", "severity": "warning", "count": 1},
        {"code": "rotation_unconfirmed", "severity": "violation", "count": 1},
        {"code": "stall_streak", "severity": "warning", "count": 10},
        {"code": "unexplained_drift", "severity": "warning", "count": 10},
    ]


def test_query_help_shows_the_full_flag_list_example(instance: Path) -> None:
    examples = coach("query", "--help").envelope["result"]["examples"]

    assert ["coach", "query", "flags", "--full"] in [example["argv"] for example in examples]
