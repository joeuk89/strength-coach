import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from support.fixture_instance import TODAY
from support.fixture_instances import coach, instance, rebuilt
from support.goals import STRENGTH

from coach.cli.declaration import Declaration
from coach.cli.registry import declarations

__all__ = ["instance", "rebuilt"]


def takes_a_draft(declaration: Declaration) -> bool:
    return any(a.key == "draft" and a.positional for a in declaration.arguments)


DRY_RUNS = [d for d in declarations() if d.writes in ("hevy", "git", "github") or takes_a_draft(d)]


def a_plan_draft(root: Path) -> str:
    drafted = coach("plan", "draft", "--week", "2026-11-02").envelope["result"]["path"]
    draft = root / drafted
    draft.write_text(draft.read_text().replace("confirmed = false", "confirmed = true"))
    return drafted


def a_program_draft(root: Path) -> str:
    return coach("program", "show", "--draft", "--out", "program.toml").envelope["result"]["path"]


def written(name: str, text: str) -> Callable[[Path], str]:
    def write(root: Path) -> str:
        (root / name).write_text(text, encoding="utf-8")
        return name

    return write


# A valid Draft of each Draft verb's own kind, made in the instance under test.
DRAFTS: dict[str, Callable[[Path], str]] = {
    "plan apply": a_plan_draft,
    "program adopt": a_program_draft,
    "goal adopt": written("goal.toml", STRENGTH),
    "record": written("record.toml", f'[[note]]\ndate = {TODAY}\ntext = "slept well"\n'),
    "checkin record": written(
        "checkin.toml", f'date = {TODAY}\ntier = "light"\nread = "a steady week"\n'
    ),
    "report": written("report.toml", 'kind = "gap"\ntitle = "No swims"\nbody = "Swims."\n'),
}


def hevy_off(root: Path) -> None:
    """A pulling verb's pull records itself on every run (verbs.md, "The pull"), so its dry run
    is checked with Hevy off, where it runs without the pull."""
    config = root / "coach.toml"
    config.write_text(config.read_text().replace("[hevy]\n", ""))


def hashes(root: Path) -> dict[str, str]:
    """Every file under the instance, the store and the Drafts included, by its content hash."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.mark.parametrize("declaration", DRY_RUNS, ids=lambda d: d.name)
def test_every_writing_or_draft_verb_declares_a_dry_run(declaration: Declaration) -> None:
    assert "--dry-run" in [a.name for a in declaration.arguments]


@pytest.mark.parametrize("declaration", DRY_RUNS, ids=lambda d: d.name)
def test_a_dry_run_on_the_fixture_instance_leaves_the_tree_and_the_store_unchanged(
    instance: Path, declaration: Declaration
) -> None:
    draft = takes_a_draft(declaration)
    positionals = [DRAFTS[declaration.name](instance)] if draft else []
    if declaration.pulls_first:
        hevy_off(instance)
    before = hashes(instance)

    run = coach(*declaration.name.split(), *positionals, "--dry-run")

    assert run.envelope["verb"] == declaration.name
    assert run.envelope["ok"] or not draft, run.stdout
    assert hashes(instance) == before
