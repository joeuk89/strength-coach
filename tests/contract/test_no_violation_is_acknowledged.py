"""validation.md, "Contract tests": no Draft a verb takes leaves a violation, whether as a plan
Draft's `[[acknowledge]]` (`plan apply`) or a `leave_warning` Decision (`record`,
`checkin record`)."""

import pytest

from coach.core.errors import Invalid
from coach.core.flag import REFS
from coach.core.ledger_draft import parse_ledger_draft
from coach.core.plan_input import parse_plan_input
from coach.core.registries.flags import FLAGS, FlagCode, ScopeKind

VIOLATIONS = [code for code in FLAGS.entries if code.severity == "violation"]
DATED = ("week", "session", "line")


def a_key(code: FlagCode, *, calendar_free: bool) -> str:
    kind: ScopeKind = code.scopes[0]
    refs = [f"x-{n}" for n, _ in enumerate(REFS[kind])]
    if kind in DATED and not calendar_free:
        refs.insert(0, "2026-11-02")
    return f"{code.name}@{kind}" + (f":{'/'.join(refs)}" if refs else "")


@pytest.mark.parametrize("code", VIOLATIONS, ids=lambda c: c.name)
def test_a_plan_draft_refuses_a_violation_as_an_acknowledgement(code: FlagCode) -> None:
    draft = (
        "week = 2026-11-02\n[[acknowledge]]\n"
        f'flag = "{a_key(code, calendar_free=False)}"\nparams_hash = "sha256:x"\n'
        'because = "coach_judgement"\ntext = "Leave it."\n'
    )

    with pytest.raises(Invalid):
        parse_plan_input(draft.encode(), file="plan.toml")


@pytest.mark.parametrize("verb", ["record", "checkin record"])
@pytest.mark.parametrize("code", VIOLATIONS, ids=lambda c: c.name)
def test_a_ledger_draft_refuses_a_violation_as_a_leave_warning_decision(
    code: FlagCode, verb: str
) -> None:
    draft = (
        '[[decision]]\nkind = "leave_warning"\n'
        f'flag = "{a_key(code, calendar_free=True)}"\nparams_hash = "sha256:x"\n'
        'until = 2026-12-01\nbecause = "coach_judgement"\ntext = "Leave it."\n'
    )

    with pytest.raises(Invalid):
        parse_ledger_draft(draft.encode(), verb=verb, file="d.toml")


def test_the_same_drafts_take_a_warning() -> None:
    plan = (
        "week = 2026-11-02\n[[acknowledge]]\n"
        'flag = "stall_streak@line:2026-11-02/lower/bb_back_squat"\nparams_hash = "sha256:x"\n'
        'because = "stall"\ntext = "Leave it."\n'
    )
    ledger = (
        '[[decision]]\nkind = "leave_warning"\n'
        'flag = "stall_streak@line:lower/bb_back_squat"\nparams_hash = "sha256:x"\n'
        'until = 2026-12-01\nbecause = "stall"\ntext = "Leave it."\n'
    )

    assert parse_plan_input(plan.encode(), file="plan.toml").acknowledgements
    assert parse_ledger_draft(ledger.encode(), verb="record", file="d.toml").records
