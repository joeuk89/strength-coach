"""The generated CLAUDE.md names verbs the way a skill does, so the same verb check holds it."""

from support.skills import unknown_verb_spans

from coach.cli.registry import declarations
from coach.render.instance_files import claude_md

LEAVES = frozenset(d.name for d in declarations())


def test_every_verb_the_generated_claude_md_names_is_a_declared_leaf() -> None:
    assert unknown_verb_spans(claude_md("0.3.0"), LEAVES) == []


def test_a_planted_verb_in_the_generated_claude_md_fails() -> None:
    planted = claude_md("0.3.0").replace("`coach record`", "`coach climb`")

    assert unknown_verb_spans(planted, LEAVES) == ["coach climb"]


def test_an_option_of_coach_itself_is_not_a_verb() -> None:
    assert unknown_verb_spans("`coach --help` lists the verbs.", LEAVES) == []
