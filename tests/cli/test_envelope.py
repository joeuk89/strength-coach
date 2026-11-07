import io
import json
from pathlib import Path
from typing import Any

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.fixture_instances import serving
from support.instances import an_instance

from coach.cli import app, registry
from coach.cli.declaration import (
    Argument,
    Call,
    Declaration,
    Json,
    MakeClient,
    Outcome,
    OverBudget,
    always,
    never,
    on_dry_run,
)
from coach.cli.envelope import BUDGET_BYTES
from coach.core.errors import CoachError, Invalid, Refused, Setup, Unreachable
from coach.store.chain import ENGINE as CHAIN


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def no_hevy() -> MakeClient:
    return serving(FakeHevy(FixedClock()))


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: "0.3.0")
    root = an_instance(tmp_path, pin="0.3.0")
    monkeypatch.chdir(root)
    return root


def test_piped_output_is_one_line(instance: Path) -> None:
    run = run_coach("status")

    assert run.stdout.endswith("\n")
    assert run.stdout.count("\n") == 1


def test_terminal_output_is_pretty_printed(instance: Path) -> None:
    run = run_coach("status", stdout=Terminal())

    assert run.stdout.count("\n") > 1
    assert json.loads(run.stdout)["ok"] is True


def test_fields_projects_dotted_paths_of_the_result(instance: Path) -> None:
    run = run_coach("status", "--fields", "engine.version,store_schema_version")

    assert run.code == 0
    assert run.envelope["result"] == {
        "engine": {"version": "0.3.0"},
        "store_schema_version": CHAIN.version,
    }


def test_fields_naming_a_path_the_result_lacks_is_invalid(instance: Path) -> None:
    run = run_coach("status", "--fields=engine.colour")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize("fields", ["warnings", "warnings.0.code", "ok", "verb", "schema_version"])
def test_fields_naming_an_envelope_field_says_it_is_outside_result(
    instance: Path, fields: str
) -> None:
    run = run_coach("status", "--fields", fields, make_client=no_hevy())

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")
    head = fields.split(".")[0]
    assert run.envelope["error"]["message"] == (
        f"--fields: {head!r} is an envelope field, not in result; it is always returned"
    )


def test_fields_naming_the_error_says_it_comes_only_on_failure(instance: Path) -> None:
    run = run_coach("status", "--fields", "error.code", make_client=no_hevy())

    assert run.envelope["error"]["message"] == (
        "--fields: 'error' is an envelope field, not in result; it is returned on failure"
    )


def test_fields_naming_an_unknown_path_says_result_lacks_it(instance: Path) -> None:
    run = run_coach("status", "--fields", "nonsense", make_client=no_hevy())

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")
    assert run.envelope["error"]["message"] == "--fields: result has no 'nonsense'"


@pytest.mark.parametrize(
    "fields",
    [
        "store_schema_version,store_schema_version.x",
        "store_schema_version.x,store_schema_version",
        "engine.version.x",
    ],
)
def test_fields_naming_a_path_below_a_scalar_is_invalid(instance: Path, fields: str) -> None:
    run = run_coach("status", "--fields", fields)

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"
    assert run.stderr == ""


def test_fields_and_full_together_are_invalid(instance: Path) -> None:
    run = run_coach("status", "--fields", "engine", "--full")

    assert run.code == 1
    assert run.envelope["verb"] == "status"
    assert run.envelope["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize("last", ["0", "-3", "ten"])
def test_last_takes_a_positive_whole_number(instance: Path, last: str) -> None:
    run = run_coach("status", "--last", last)

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


def test_an_unknown_verb_is_invalid_with_one_json_document(instance: Path) -> None:
    run = run_coach("sync")

    assert run.code == 1
    assert run.envelope["ok"] is False
    assert run.envelope["verb"] is None
    assert run.envelope["error"]["code"] == "invalid_argument"


def test_an_unknown_option_is_invalid(instance: Path) -> None:
    run = run_coach("status", "--colour")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


def test_an_unexpected_failure_still_prints_one_envelope(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(app, "engine_version", broken)

    run = run_coach("status")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "internal_error"
    assert "RuntimeError" in run.stderr


@pytest.mark.parametrize(
    ("kind", "code"), [(Invalid, 1), (Refused, 3), (Unreachable, 4), (Setup, 5)]
)
def test_each_typed_error_exits_with_its_class(
    monkeypatch: pytest.MonkeyPatch, kind: type[CoachError], code: int
) -> None:
    def fail(call: Call) -> Outcome:
        raise kind("some_code", "it failed")

    failing = Declaration(name="fail", summary="Fails.", writes="none", output={}, run=fail)
    monkeypatch.setattr(registry, "declarations", lambda: (failing,))

    run = run_coach("fail")

    assert run.code == code
    assert run.stdout.count("\n") == 1
    assert run.envelope["ok"] is False
    assert run.envelope["verb"] == "fail"
    assert run.envelope["error"]["code"] == "some_code"


# Ten rows this wide pass the budget, and the first five fit it.
WIDE = BUDGET_BYTES // 6


def a_listing(rows: int, *, width: int = 100, over_budget: OverBudget = never) -> Declaration:
    def listing(call: Call) -> Outcome:
        kept = [{"id": n, "text": "x" * width} for n in range(rows)][: call.last]
        return Outcome({"rows": kept, "count": rows, "truncated": len(kept) < rows})

    return Declaration(
        name="listing",
        summary="Lists.",
        writes="none",
        output={},
        run=listing,
        arguments=(Argument("--dry-run", "validate only", takes_value=False),),
        over_budget=over_budget,
    )


def test_rows_past_the_budget_are_cut_from_the_end_and_marked_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "declarations", lambda: (a_listing(10, width=WIDE),))

    run = run_coach("listing")

    result = run.envelope["result"]
    assert len(run.stdout.encode("utf-8")) <= BUDGET_BYTES
    assert [row["id"] for row in result["rows"]] == [0, 1, 2, 3, 4]
    assert (result["count"], result["truncated"]) == (10, True)


def test_rows_under_the_budget_are_left_as_the_list_rule_kept_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "declarations", lambda: (a_listing(4),))

    result = run_coach("listing").envelope["result"]

    assert (len(result["rows"]), result["truncated"]) == (4, False)


def test_full_lifts_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "declarations", lambda: (a_listing(10, width=WIDE),))

    result = run_coach("listing", "--full").envelope["result"]

    assert len(result["rows"]) == 10


def test_a_verb_declared_over_budget_keeps_every_row_past_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = a_listing(10, width=WIDE, over_budget=always)
    monkeypatch.setattr(registry, "declarations", lambda: (listing,))

    run = run_coach("listing")

    assert len(run.stdout.encode("utf-8")) > BUDGET_BYTES
    assert (len(run.envelope["result"]["rows"]), run.envelope["result"]["truncated"]) == (10, False)


def test_a_verb_over_budget_on_its_dry_run_fits_the_budget_without_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = a_listing(10, width=WIDE, over_budget=on_dry_run)
    monkeypatch.setattr(registry, "declarations", lambda: (listing,))

    dry_run = run_coach("listing", "--dry-run").envelope["result"]
    real = run_coach("listing")

    assert len(dry_run["rows"]) == 10
    assert len(real.stdout.encode("utf-8")) <= BUDGET_BYTES
    assert (len(real.envelope["result"]["rows"]), real.envelope["result"]["truncated"]) == (5, True)


def test_the_largest_row_list_is_cut_first(monkeypatch: pytest.MonkeyPatch) -> None:
    def card(call: Call) -> Outcome:
        def rows(n: int) -> Json:
            return {
                "rows": [{"text": "y" * (BUDGET_BYTES // 8)}] * n,
                "count": n,
                "truncated": False,
            }

        return Outcome({"lifts": rows(8), "activities": rows(2)})

    monkeypatch.setattr(
        registry,
        "declarations",
        lambda: (
            Declaration(
                name="card",
                summary="A card.",
                writes="none",
                output={},
                run=card,
            ),
        ),
    )

    result = run_coach("card").envelope["result"]

    assert len(result["activities"]["rows"]) == 2
    assert result["lifts"]["truncated"] is True
    assert len(result["lifts"]["rows"]) < 8


def test_a_json_schema_naming_rows_count_and_truncated_is_not_a_row_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def describe(call: Call) -> Outcome:
        shape: Json = {"rows": {"type": "array"}, "count": {}, "truncated": {}}
        return Outcome(
            {"declarations": [{"properties": shape, "text": "z" * (BUDGET_BYTES + 1000)}]}
        )

    monkeypatch.setattr(
        registry,
        "declarations",
        lambda: (
            Declaration(
                name="describe",
                summary="Describes.",
                writes="none",
                output={},
                run=describe,
            ),
        ),
    )

    run = run_coach("describe")

    assert run.code == 0


def a_group(code: str, keys: int) -> Json:
    return {
        "code": code,
        "severity": "warning",
        "count": keys,
        "keys": [
            {"key": f"{code}@line:{n:03}", "params_hash": "sha256:" + "0" * 64} for n in range(keys)
        ],
    }


def a_grouping(result: Json) -> Declaration:
    return Declaration(
        name="grouping",
        summary="Groups.",
        writes="none",
        output={},
        run=lambda call: Outcome(result),
    )


def test_a_grouped_list_past_the_budget_loses_trailing_keys_from_the_longest_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups: Any = [
        a_group("stall_streak", 60),
        a_group("rep_range_missed", 5),
        a_group("dose_under_target", 1),
    ]
    grouping = a_grouping({"rows": groups, "count": 3, "truncated": False})
    monkeypatch.setattr(registry, "declarations", lambda: (grouping,))

    run = run_coach("grouping")

    result = run.envelope["result"]
    longest, *rest = result["rows"]
    assert len(run.stdout.encode("utf-8")) <= BUDGET_BYTES
    assert [row["code"] for row in result["rows"]] == [
        "stall_streak",
        "rep_range_missed",
        "dose_under_target",
    ]
    assert (result["count"], result["truncated"]) == (3, False)
    assert (longest["count"], longest["keys_truncated"]) == (60, True)
    assert 0 < len(longest["keys"]) < 60
    assert longest["keys"] == groups[0]["keys"][: len(longest["keys"])]
    assert rest == groups[1:]


def test_grouped_rows_outside_a_row_list_are_fitted_the_same_way(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flags = [a_group("stall_streak", 40), a_group("rep_range_missed", 30)]
    grouping = a_grouping({"flags": flags, "flag_count": 70, "flags_truncated": False})
    monkeypatch.setattr(registry, "declarations", lambda: (grouping,))

    run = run_coach("grouping")

    result = run.envelope["result"]
    assert len(run.stdout.encode("utf-8")) <= BUDGET_BYTES
    assert [row["code"] for row in result["flags"]] == ["stall_streak", "rep_range_missed"]
    assert all(row["keys_truncated"] for row in result["flags"])
    assert result["flags_truncated"] is False


def test_keys_are_trimmed_before_any_flat_row(monkeypatch: pytest.MonkeyPatch) -> None:
    flat: Json = {"rows": [{"text": "x" * 100}] * 5, "count": 5, "truncated": False}
    grouping = a_grouping(
        {
            "flags": [a_group("stall_streak", 60)],
            "flag_count": 60,
            "flags_truncated": False,
            "notes": flat,
        }
    )
    monkeypatch.setattr(registry, "declarations", lambda: (grouping,))

    result = run_coach("grouping").envelope["result"]

    assert result["flags"][0]["keys_truncated"] is True
    assert (len(result["notes"]["rows"]), result["notes"]["truncated"]) == (5, False)
