import io
import json
from pathlib import Path

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.fixture_instances import serving
from support.instances import an_instance

from coach.cli import app, registry
from coach.cli.declaration import (
    Call,
    Declaration,
    Json,
    MakeClient,
    Outcome,
)
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


def a_listing(rows: int) -> Declaration:
    def listing(call: Call) -> Outcome:
        kept = [{"id": n, "text": "x" * 1000} for n in range(rows)][: call.last]
        return Outcome({"rows": kept, "count": rows, "truncated": len(kept) < rows})

    return Declaration(name="listing", summary="Lists.", writes="none", output={}, run=listing)


def test_a_list_of_any_size_comes_whole_with_no_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "declarations", lambda: (a_listing(100),))

    result = run_coach("listing").envelope["result"]

    assert (len(result["rows"]), result["count"], result["truncated"]) == (100, 100, False)


def test_last_keeps_the_first_n_rows_and_says_more_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "declarations", lambda: (a_listing(100),))

    result = run_coach("listing", "--last", "3").envelope["result"]

    assert [row["id"] for row in result["rows"]] == [0, 1, 2]
    assert (result["count"], result["truncated"]) == (100, True)


def test_a_grouped_flag_list_keeps_every_key(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = [
        {"key": f"stall_streak@line:{n:03}", "params_hash": "sha256:" + "0" * 64}
        for n in range(300)
    ]
    group: Json = {"code": "stall_streak", "severity": "warning", "count": 300, "keys": keys}
    grouping = Declaration(
        name="grouping",
        summary="Groups.",
        writes="none",
        output={},
        run=lambda call: Outcome({"flags": [group], "flag_count": 300}),
    )
    monkeypatch.setattr(registry, "declarations", lambda: (grouping,))

    [row] = run_coach("grouping").envelope["result"]["flags"]

    assert row == group
