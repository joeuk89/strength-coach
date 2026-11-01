import pytest

from coach.cli.registry import declarations
from coach.core.registries.agent import RECORD_KINDS
from coach.core.registries.flags import FLAGS, FlagCode

# Leaves verbs.md declares that no ticket has built yet. A leaf leaves this set when it lands,
# and the test below fails until it does.
PENDING_LEAVES = frozenset(
    {
        "import",
        "checkin open",
        "checkin record",
        "record",
        "plan draft",
        "plan apply",
        "program show",
        "program adopt",
        "goal adopt",
        "progress",
        "query",
        "publish",
        "upgrade",
        "init",
    }
)

VIOLATIONS = [code for code in FLAGS.entries if code.severity == "violation"]
DECLARED = frozenset(d.name for d in declarations())


def test_no_pending_leaf_is_already_declared() -> None:
    assert not PENDING_LEAVES & DECLARED


@pytest.mark.parametrize("code", VIOLATIONS, ids=lambda c: c.name)
def test_every_violation_names_a_clearing_verb_or_record(code: FlagCode) -> None:
    assert code.cleared_by
    for clearer in code.cleared_by:
        if clearer.startswith("[["):
            assert clearer.strip("[]") in RECORD_KINDS
        else:
            assert clearer in DECLARED | PENDING_LEAVES


@pytest.mark.parametrize(
    "code", [c for c in FLAGS.entries if c.severity == "warning"], ids=lambda c: c.name
)
def test_a_warning_names_no_clearer(code: FlagCode) -> None:
    assert code.cleared_by == ()
