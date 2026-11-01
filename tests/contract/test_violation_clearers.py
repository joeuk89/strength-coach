import pytest

from coach.cli.registry import declarations
from coach.core.registries.agent import RECORD_KINDS
from coach.core.registries.flags import FLAGS, FlagCode

# Leaves verbs.md declares that are not built yet. Remove each one as it lands, or the test below
# fails.
PENDING_LEAVES = frozenset(
    {
        "checkin open",
        "checkin record",
        "plan draft",
        "plan apply",
        "program show",
        "program adopt",
        "goal adopt",
        "progress",
        "upgrade",
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
