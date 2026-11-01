from pathlib import Path

import pytest
from support.fixture_instance import FIXTURE, regenerate, tree


@pytest.fixture(scope="session")
def fresh(tmp_path_factory: pytest.TempPathFactory) -> Path:
    scratch = tmp_path_factory.mktemp("generation")
    target = scratch / "instance"
    regenerate(scratch, target)
    return target


def test_the_committed_fixture_instance_is_a_fresh_generation_byte_for_byte(fresh: Path) -> None:
    committed, generated = tree(FIXTURE), tree(fresh)

    assert sorted(committed) == sorted(generated)
    differing = [path for path in committed if committed[path] != generated[path]]
    assert differing == [], "regenerate it from tests/: uv run python -m support.fixture_instance"
