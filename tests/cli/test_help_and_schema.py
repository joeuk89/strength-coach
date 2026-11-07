from pathlib import Path

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.fixture_instances import serving

from coach.cli.envelope import BUDGET_BYTES
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


def test_help_lists_version_among_the_options_and_in_the_usage() -> None:
    result = run_coach("--help", make_client=serving(FakeHevy(FixedClock()))).envelope["result"]

    (option,) = [o for o in result["options"] if o["name"] == "--version"]
    assert option["help"]
    assert "coach --version" in result["usage"]


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
        "store_schema_version",
        "kit",
        "plan",
        "rotation",
        "program",
        "goal",
        "phase",
        "check_in",
        "niggles",
        "follow_ups_due",
        "decisions",
        "observations",
        "export",
    ]
    assert declaration["examples"][0]["argv"] == ["coach", "status"]


def test_schema_without_a_verb_gives_every_declaration_uncut_over_the_budget() -> None:
    run = run_coach("schema")

    result = run.envelope["result"]
    assert run.code == 0
    assert len(run.stdout.encode("utf-8")) > BUDGET_BYTES
    assert [row["name"] for row in result["rows"]] == [d.name for d in declarations()]
    assert result["rows"][0] == declarations()[0].describe()
    assert (result["count"], result["truncated"]) == (17, False)


def test_schema_without_a_verb_ignores_last() -> None:
    result = run_coach("schema", "--last", "2").envelope["result"]

    assert (len(result["rows"]), result["count"], result["truncated"]) == (17, 17, False)


def test_schema_full_gives_the_same_as_schema() -> None:
    assert run_coach("schema", "--full").stdout == run_coach("schema").stdout


def test_schema_of_the_schema_verb_declares_its_optional_verb_argument() -> None:
    run = run_coach("schema", "schema")

    properties = run.envelope["result"]["input"]["properties"]
    assert properties["verb"]["type"] == "string"
    assert run.envelope["result"]["input"]["required"] == []


def test_schema_of_the_schema_verb_declares_the_registry_names_it_lists() -> None:
    output = run_coach("schema", "schema").envelope["result"]["output"]

    assert output["properties"]["registries"] == {
        "type": "array",
        "items": {"type": "string"},
        "description": output["properties"]["registries"]["description"],
    }
    assert output["properties"]["registries"]["description"]


def test_schema_of_an_unknown_verb_is_invalid() -> None:
    run = run_coach("schema", "sync")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"
