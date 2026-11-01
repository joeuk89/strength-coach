import pytest

from coach.core.errors import Invalid
from coach.core.ledger_draft import parse_ledger_draft

REASON = 'because = "coach_judgement"\ntext = "agreed"\n'
UNTIL = "until = 2026-12-01\n"
WARNING = 'kind = "leave_warning"\nparams_hash = "h"\n'


def parse(text: str) -> None:
    parse_ledger_draft(text.encode("utf-8"), verb="record", file="d.toml")


def test_a_decision_carries_no_outcome_field() -> None:
    with pytest.raises(Invalid) as raised:
        parse(f'[[decision]]\nkind = "defer_deep_review"\n{UNTIL}outcome = "taken"\n{REASON}')

    assert raised.value.code == "unknown_key"
    assert "outcome" in raised.value.message


def test_a_decision_kind_outside_the_registry_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        parse(f'[[decision]]\nkind = "block_reset"\n{REASON}')

    assert raised.value.code == "invalid_argument"
    assert "one of override, park_session" in raised.value.message


@pytest.mark.parametrize(
    "body",
    [
        'kind = "training_max"\nexercise = "bb_bench_press"\nload = 100\nuntil = 2026-12-01\n',
        f'{WARNING}flag = "cadence_slow@exercise:x"\n',
        f'{WARNING}flag = "cadence_slow@line:2026-10-26/s/x"\n{UNTIL}',
        f'{WARNING}flag = "not_a_code@exercise:x"\n{UNTIL}',
        'kind = "against_research"\nref = "niggle:n-0001"\n',
        'kind = "activity_cap"\nactivity_kind = "run"\n',
        'kind = "activity_cap"\nactivity_kind = "run"\nweekly_distance = 17\nweekly_minutes = 90\n',
        'kind = "decline_ceiling"\nblock = "2026-10-05"\n',
        'kind = "retire"\ndecision = "n-0001"\n',
        'kind = "training_max"\nexercise = "bb_bench_press"\n',
    ],
)
def test_a_decision_off_its_kind_s_shape_is_refused(body: str) -> None:
    with pytest.raises(Invalid):
        parse(f"[[decision]]\n{body}{REASON}")


@pytest.mark.parametrize(
    "reason", ['because = "pain"\n', 'text = "x"\n', 'because = "boredom"\ntext = "x"\n']
)
def test_a_decision_carries_the_reason_triple(reason: str) -> None:
    with pytest.raises(Invalid):
        parse(f'[[decision]]\nkind = "defer_deep_review"\nuntil = 2026-11-07\n{reason}')
