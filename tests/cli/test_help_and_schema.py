from pathlib import Path

import pytest
from support.cli import run_coach

from coach.cli.registry import declarations


@pytest.fixture(autouse=True)
def outside_an_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_help_lists_every_declared_leaf() -> None:
    run = run_coach("--help")

    assert run.code == 0
    assert run.envelope["verb"] is None
    names = [leaf["name"] for leaf in run.envelope["result"]["verbs"]]
    assert names == [d.name for d in declarations()]
    assert {"status", "schema"} <= set(names)


def test_no_arguments_prints_the_help() -> None:
    run = run_coach()

    assert run.code == 0
    assert run.envelope["result"]["verbs"]


def test_verb_help_describes_the_leaf_without_running_it() -> None:
    run = run_coach("status", "--help")

    assert run.code == 0
    assert run.envelope["verb"] == "status"
    assert run.envelope["result"]["name"] == "status"
    assert run.envelope["result"]["writes"] == "none"


def test_schema_of_one_verb_is_its_declaration_as_json_schema() -> None:
    run = run_coach("schema", "status")

    assert run.code == 0
    declaration = run.envelope["result"]
    assert declaration["name"] == "status"
    assert declaration["writes"] == "none"
    assert declaration["input"]["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert declaration["input"]["type"] == "object"
    assert declaration["input"]["properties"] == {}
    assert declaration["output"]["required"] == [
        "engine",
        "hevy",
        "workouts",
        "schema_version",
        "kit",
        "export",
    ]
    assert declaration["examples"][0]["argv"] == ["coach", "status"]


def test_schema_without_a_verb_gives_every_declaration() -> None:
    run = run_coach("schema")

    assert run.code == 0
    assert [v["name"] for v in run.envelope["result"]["verbs"]] == [d.name for d in declarations()]


def test_schema_of_the_schema_verb_declares_its_optional_verb_argument() -> None:
    run = run_coach("schema", "schema")

    properties = run.envelope["result"]["input"]["properties"]
    assert properties["verb"]["type"] == "string"
    assert run.envelope["result"]["input"]["required"] == []


def test_schema_of_an_unknown_verb_is_invalid() -> None:
    run = run_coach("schema", "sync")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"
