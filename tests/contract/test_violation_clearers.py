import pytest

from coach.cli.registry import declarations
from coach.core.registries.agent import RECORD_KINDS
from coach.core.registries.flags import FLAGS, FlagCode

VIOLATIONS = [code for code in FLAGS.entries if code.severity == "violation"]
DECLARED = frozenset(d.name for d in declarations())


@pytest.mark.parametrize("code", VIOLATIONS, ids=lambda c: c.name)
def test_every_violation_names_a_clearing_verb_or_record(code: FlagCode) -> None:
    assert code.cleared_by
    for clearer in code.cleared_by:
        if clearer.startswith("[["):
            assert clearer.strip("[]") in RECORD_KINDS
        else:
            assert clearer in DECLARED


@pytest.mark.parametrize(
    "code", [c for c in FLAGS.entries if c.severity == "warning"], ids=lambda c: c.name
)
def test_a_warning_names_no_clearer(code: FlagCode) -> None:
    assert code.cleared_by == ()
