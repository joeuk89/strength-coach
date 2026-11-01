import json
from pathlib import Path

import pytest
from support.cli import run_coach
from support.instances import an_instance

from coach.cli import app
from coach.cli.declaration import Declaration, Example
from coach.cli.registry import declarations

MAX_LEAVES = 16

EXAMPLES = [
    pytest.param(declaration, example, id=" ".join(example.argv))
    for declaration in declarations()
    for example in declaration.examples
]


def test_there_are_at_most_sixteen_leaves() -> None:
    assert 0 < len(declarations()) <= MAX_LEAVES


def test_leaf_names_are_unique() -> None:
    names = [d.name for d in declarations()]

    assert len(names) == len(set(names))


@pytest.mark.parametrize("declaration", declarations(), ids=lambda d: d.name)
def test_every_leaf_declares_an_example(declaration: Declaration) -> None:
    assert declaration.examples


@pytest.mark.parametrize(("declaration", "example"), EXAMPLES)
def test_every_example_prints_exactly_one_json_document(
    declaration: Declaration, example: Example, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: "0.3.0")
    monkeypatch.chdir(an_instance(tmp_path, pin="0.3.0"))

    run = run_coach(*example.argv)

    document = json.loads(run.stdout)
    assert document["verb"] == declaration.name
    assert run.stdout.count("\n") == 1
