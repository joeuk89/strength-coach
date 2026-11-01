import io
import json
from pathlib import Path

import pytest
from support.cli import run_coach
from support.instances import an_instance

from coach.cli import app, registry
from coach.cli.declaration import (
    Argument,
    Call,
    Declaration,
    Json,
    Outcome,
    OverBudget,
    always,
    never,
    on_dry_run,
)
from coach.core.errors import CoachError, Invalid, Refused, Setup, Unreachable


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


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
    assert run.envelope["result"] == {"engine": {"version": "0.3.0"}, "store_schema_version": 1}


def test_fields_naming_a_path_the_result_lacks_is_invalid(instance: Path) -> None:
    run = run_coach("status", "--fields=engine.colour")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


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

    failing = Declaration(
        name="fail", summary="Fails.", writes="none", needs_instance=False, output={}, run=fail
    )
    monkeypatch.setattr(registry, "declarations", lambda: (failing,))

    run = run_coach("fail")

    assert run.code == code
    assert run.stdout.count("\n") == 1
    assert run.envelope["ok"] is False
    assert run.envelope["verb"] == "fail"
    assert run.envelope["error"]["code"] == "some_code"


def a_listing(rows: int, *, width: int = 100, over_budget: OverBudget = never) -> Declaration:
    def listing(call: Call) -> Outcome:
        kept = [{"id": n, "text": "x" * width} for n in range(rows)][: call.last]
        return Outcome({"rows": kept, "count": rows, "truncated": len(kept) < rows})

    return Declaration(
        name="listing",
        summary="Lists.",
        writes="none",
        needs_instance=False,
        output={},
        run=listing,
        arguments=(Argument("--dry-run", "validate only", takes_value=False),),
        over_budget=over_budget,
    )


def test_rows_past_3_kb_are_cut_from_the_end_and_marked_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "declarations", lambda: (a_listing(10, width=500),))

    run = run_coach("listing")

    result = run.envelope["result"]
    assert len(run.stdout.encode("utf-8")) <= 3 * 1024
    assert [row["id"] for row in result["rows"]] == [0, 1, 2, 3, 4]
    assert (result["count"], result["truncated"]) == (10, True)


def test_rows_under_3_kb_are_left_as_the_list_rule_kept_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "declarations", lambda: (a_listing(4),))

    result = run_coach("listing").envelope["result"]

    assert (len(result["rows"]), result["truncated"]) == (4, False)


def test_full_lifts_the_3_kb_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "declarations", lambda: (a_listing(10, width=500),))

    result = run_coach("listing", "--full").envelope["result"]

    assert len(result["rows"]) == 10


def test_a_verb_declared_over_budget_keeps_every_row_past_3_kb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = a_listing(10, width=500, over_budget=always)
    monkeypatch.setattr(registry, "declarations", lambda: (listing,))

    run = run_coach("listing")

    assert len(run.stdout.encode("utf-8")) > 3 * 1024
    assert (len(run.envelope["result"]["rows"]), run.envelope["result"]["truncated"]) == (10, False)


def test_a_verb_over_budget_on_its_dry_run_fits_3_kb_without_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = a_listing(10, width=500, over_budget=on_dry_run)
    monkeypatch.setattr(registry, "declarations", lambda: (listing,))

    dry_run = run_coach("listing", "--dry-run").envelope["result"]
    real = run_coach("listing")

    assert len(dry_run["rows"]) == 10
    assert len(real.stdout.encode("utf-8")) <= 3 * 1024
    assert (len(real.envelope["result"]["rows"]), real.envelope["result"]["truncated"]) == (5, True)


def test_the_largest_row_list_is_cut_first(monkeypatch: pytest.MonkeyPatch) -> None:
    def card(call: Call) -> Outcome:
        def rows(n: int) -> Json:
            return {"rows": [{"text": "y" * 400}] * n, "count": n, "truncated": False}

        return Outcome({"lifts": rows(8), "activities": rows(2)})

    monkeypatch.setattr(
        registry,
        "declarations",
        lambda: (
            Declaration(
                name="card",
                summary="A card.",
                writes="none",
                needs_instance=False,
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
        return Outcome({"declarations": [{"properties": shape, "text": "z" * 4000}]})

    monkeypatch.setattr(
        registry,
        "declarations",
        lambda: (
            Declaration(
                name="describe",
                summary="Describes.",
                writes="none",
                needs_instance=False,
                output={},
                run=describe,
            ),
        ),
    )

    run = run_coach("describe")

    assert run.code == 0
