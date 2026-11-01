import hashlib
from pathlib import Path

import pytest
from support.fixture_instances import coach, instance, rebuilt

from coach.cli.declaration import Declaration
from coach.cli.registry import declarations

__all__ = ["instance", "rebuilt"]

ASKED = [d for d in declarations() if d.writes in ("hevy", "git")]


def hashes(root: Path) -> dict[str, str]:
    """Every file under the instance, the store and the Drafts included, by its content hash."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.mark.parametrize("declaration", ASKED, ids=lambda d: d.name)
def test_every_asked_verb_declares_a_dry_run(declaration: Declaration) -> None:
    assert "--dry-run" in [a.name for a in declaration.arguments]


@pytest.mark.parametrize("declaration", ASKED, ids=lambda d: d.name)
def test_a_dry_run_on_the_fixture_instance_leaves_the_tree_and_the_store_unchanged(
    instance: Path, declaration: Declaration
) -> None:
    drafted = coach("plan", "draft", "--week", "2026-11-02").envelope["result"]["path"]
    draft = instance / drafted
    draft.write_text(draft.read_text().replace("confirmed = false", "confirmed = true"))
    positionals = [drafted for a in declaration.arguments if a.positional and a.required]
    before = hashes(instance)

    run = coach(*declaration.name.split(), *positionals, "--dry-run")

    assert run.envelope["verb"] == declaration.name
    assert hashes(instance) == before
