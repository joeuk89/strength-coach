import io
import json
from pathlib import Path

import pytest
from support.cli import run_coach
from support.instances import an_instance

from coach.cli import app, registry
from coach.cli.declaration import Call, Declaration, Outcome
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
    run = run_coach("status", "--fields", "engine.version,schema_version")

    assert run.code == 0
    assert run.envelope["result"] == {"engine": {"version": "0.3.0"}, "schema_version": 1}


def test_fields_naming_a_path_the_result_lacks_is_invalid(instance: Path) -> None:
    run = run_coach("status", "--fields=engine.colour")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize(
    "fields",
    ["schema_version,schema_version.x", "schema_version.x,schema_version", "engine.version.x"],
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
