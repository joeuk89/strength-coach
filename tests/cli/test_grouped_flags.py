import dataclasses
import datetime
import tomllib
from pathlib import Path
from typing import Any

import pytest
from support.fixture_instances import coach, instance, rebuilt

from coach.cli.verbs import plan_draft as plan_draft_verb
from coach.core.flag import Flag, Scope
from coach.services.plan_draft import PlanDraftResult

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


def thirty_codes_of_two_keys(week: datetime.date) -> tuple[Flag, ...]:
    return tuple(
        Flag(f"sample_{n:02}", "warning", Scope("week", monday), {}, None, "a sample flag")
        for n in range(30)
        for monday in (week, week + datetime.timedelta(weeks=1))
    )


def test_plan_draft_lists_thirty_flag_codes_and_every_key_with_no_options(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    derive = plan_draft_verb.plan_draft

    def with_thirty_codes(*args: Any, **kwargs: Any) -> PlanDraftResult:
        drafted = derive(*args, **kwargs)
        flags = thirty_codes_of_two_keys(drafted.draft.week)
        return dataclasses.replace(
            drafted, draft=dataclasses.replace(drafted.draft, template_checks=flags)
        )

    monkeypatch.setattr(plan_draft_verb, "plan_draft", with_thirty_codes)

    result = coach("plan", "draft").envelope["result"]

    sampled = [row for row in result["flags"] if row["code"].startswith("sample_")]
    assert [row["code"] for row in sampled] == [f"sample_{n:02}" for n in range(30)]
    assert all(len(row["keys"]) == 2 for row in sampled)
    assert (len(result["flags"]), result["flag_count"], result["flags_truncated"]) == (
        34,
        82,
        False,
    )


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


def test_the_plan_apply_dry_run_lists_every_flag_whole(
    instance: Path,
) -> None:
    draft, hashes = a_confirmed_plan_draft(instance)

    result = coach("plan", "apply", draft, "--dry-run").envelope["result"]

    assert (len(result["flags"]), result["flag_count"]) == (21, 21)
    assert "flags_truncated" not in result
    assert all(
        set(row)
        == {"key", "code", "severity", "scope", "params", "params_hash", "rn", "message", "left"}
        for row in result["flags"]
    )
    assert {row["key"]: row["params_hash"] for row in result["flags"]} == {
        key: digest for key, digest in hashes.items() if not key.startswith("rotation_")
    }
    first = result["flags"][0]
    assert (first["key"], first["code"], first["severity"], first["left"]) == (
        "stall_streak@line:2026-11-02/lower-a/bb_romanian_deadlift",
        "stall_streak",
        "warning",
        None,
    )
    assert first["params_hash"] == hashes[first["key"]]
    assert first["message"]


def test_the_plan_apply_dry_run_never_cuts_its_flags_to_last(instance: Path) -> None:
    draft, _ = a_confirmed_plan_draft(instance)

    result = coach("plan", "apply", draft, "--dry-run", "--last", "2").envelope["result"]

    assert (len(result["flags"]), result["flag_count"]) == (21, 21)


def test_full_changes_no_dry_run_flag(instance: Path) -> None:
    draft, _ = a_confirmed_plan_draft(instance)

    default = coach("plan", "apply", draft, "--dry-run").envelope["result"]["flags"]
    full = coach("plan", "apply", draft, "--dry-run", "--full").envelope["result"]["flags"]

    assert default == full
