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


def a_confirmed_plan_draft(instance: Path) -> tuple[str, dict[str, str]]:
    """The fixture's plan Draft with its rotation confirmed, and each flag key `plan draft`
    lists with its params hash."""
    drafted = coach("plan", "draft").envelope["result"]
    path = instance / drafted["path"]
    path.write_text(path.read_text().replace("confirmed = false", "confirmed = true"))
    return str(path), grouped_hashes(drafted["flags"])


def test_the_plan_apply_dry_run_lists_every_flag_with_what_an_acknowledgement_needs(
    instance: Path,
) -> None:
    draft, hashes = a_confirmed_plan_draft(instance)

    result = coach("plan", "apply", draft, "--dry-run").envelope["result"]

    assert (len(result["flags"]), result["flag_count"]) == (21, 21)
    assert "flags_truncated" not in result
    assert all(
        set(row) == {"key", "code", "severity", "params_hash", "left"} for row in result["flags"]
    )
    assert {row["key"]: row["params_hash"] for row in result["flags"]} == {
        key: digest for key, digest in hashes.items() if not key.startswith("rotation_")
    }
    assert result["flags"][0] == {
        "key": "stall_streak@line:2026-11-02/lower-a/bb_romanian_deadlift",
        "code": "stall_streak",
        "severity": "warning",
        "params_hash": hashes["stall_streak@line:2026-11-02/lower-a/bb_romanian_deadlift"],
        "left": None,
    }


def test_the_plan_apply_dry_run_never_cuts_its_flags_to_last(instance: Path) -> None:
    draft, _ = a_confirmed_plan_draft(instance)

    result = coach("plan", "apply", draft, "--dry-run", "--last", "2").envelope["result"]

    assert (len(result["flags"]), result["flag_count"]) == (21, 21)


def test_each_dry_run_flag_carries_the_params_hash_full_shows(instance: Path) -> None:
    draft, _ = a_confirmed_plan_draft(instance)

    brief = coach("plan", "apply", draft, "--dry-run").envelope["result"]["flags"]
    full = coach("plan", "apply", draft, "--dry-run", "--full").envelope["result"]["flags"]

    assert [(f["key"], f["params_hash"]) for f in brief] == [
        (f["key"], f["params_hash"]) for f in full
    ]
    assert all("message" in f and "params" in f and "scope" in f for f in full)
