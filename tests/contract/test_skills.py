"""skills.md, "Contract tests": the verbs a skill names exist and each skill is within budget.
Nothing here reads a sentence; wording is checked at review against the never-list."""

from pathlib import Path

import pytest
from support.skills import TOKEN_BUDGET, skill_files, tokens, undeclared_verbs

from coach.cli.registry import declarations

SKILLS = Path(__file__).resolve().parents[2] / "skills"
LEAVES = frozenset(d.name for d in declarations())

SKILL = """---
name: example
description: A moment.
---

## Read first
The card from `coach checkin open`.

## Verbs
`coach status`, `coach query`
"""


def test_the_plugin_ships_the_five_skills() -> None:
    assert sorted(path.parent.name for path in skill_files(SKILLS)) == [
        "check-in",
        "kit",
        "onboard",
        "plan-week",
        "program",
    ]


@pytest.mark.parametrize("path", skill_files(SKILLS), ids=lambda p: p.parent.name)
def test_every_verb_a_skill_names_is_a_declared_leaf(path: Path) -> None:
    assert undeclared_verbs(path.read_text(encoding="utf-8"), LEAVES) == []


@pytest.mark.parametrize("path", skill_files(SKILLS), ids=lambda p: p.parent.name)
def test_every_skill_is_within_its_token_budget(path: Path) -> None:
    assert tokens(path.read_text(encoding="utf-8")) <= TOKEN_BUDGET


def test_a_skill_naming_only_declared_leaves_passes() -> None:
    assert undeclared_verbs(SKILL, LEAVES) == []


def test_a_planted_verb_in_prose_fails() -> None:
    planted = SKILL.replace("The card", "Run `coach frobnicate`, then the card")

    assert undeclared_verbs(planted, LEAVES) == ["coach frobnicate"]


def test_a_planted_verb_in_the_verbs_list_fails() -> None:
    planted = SKILL.replace("`coach query`", "`coach query`, `coach frobnicate`")

    assert undeclared_verbs(planted, LEAVES) == ["coach frobnicate"]


def test_a_group_word_alone_is_not_a_leaf() -> None:
    planted = SKILL.replace("`coach checkin open`", "`coach checkin`")

    assert undeclared_verbs(planted, LEAVES) == ["coach checkin"]


def test_a_leaf_followed_by_its_arguments_is_the_leaf() -> None:
    named = SKILL.replace("`coach checkin open`", "`coach program show --draft`")

    assert undeclared_verbs(named, LEAVES) == []


def test_a_verbs_entry_must_be_a_bare_leaf() -> None:
    planted = SKILL.replace("`coach query`", "`coach query exposures`")

    assert undeclared_verbs(planted, LEAVES) == ["coach query exposures"]


def test_a_skill_with_no_verbs_list_fails() -> None:
    bare = SKILL.split("## Verbs")[0]

    assert undeclared_verbs(bare, LEAVES) == ["no Verbs list"]


def test_prose_about_the_coach_is_not_a_verb() -> None:
    prose = SKILL.replace("The card", "In the coach's voice and coach.toml, the card")

    assert undeclared_verbs(prose, LEAVES) == []


def test_tokens_are_characters_divided_by_four_frontmatter_included() -> None:
    assert tokens("---\nname: x\n---\n" + "a" * 4) == 5


def test_a_skill_padded_past_six_thousand_characters_is_over_budget() -> None:
    padded = SKILL + "x" * (6001 - len(SKILL))

    assert tokens(padded) > TOKEN_BUDGET
    assert tokens(padded[:6000]) <= TOKEN_BUDGET
