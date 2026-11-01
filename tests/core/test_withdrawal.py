import pytest

from coach.core.errors import Invalid
from coach.core.withdrawal import withdrawable

WEIGH_IN = {"id": "wi-0001", "date": "2026-10-29", "kg": 82.0, "withdraws": None}


def test_a_stored_row_no_one_has_withdrawn_is_withdrawable() -> None:
    assert withdrawable("weigh_in", "wi-0001", WEIGH_IN, None) == WEIGH_IN


@pytest.mark.parametrize(
    ("stored", "withdrawn_by", "code", "message"),
    [
        (None, None, "draft_ref_unresolved", "[[weigh_in]] withdraws wi-0001, which is not stored"),
        (
            {**WEIGH_IN, "withdraws": "wi-0000"},
            None,
            "state_conflict",
            "wi-0001 is itself a withdrawal; it cannot be withdrawn",
        ),
        (WEIGH_IN, "wi-0002", "state_conflict", "wi-0001 is already withdrawn by wi-0002"),
    ],
)
def test_a_missing_withdrawing_or_withdrawn_row_is_refused(
    stored: dict[str, object] | None, withdrawn_by: str | None, code: str, message: str
) -> None:
    with pytest.raises(Invalid) as raised:
        withdrawable("weigh_in", "wi-0001", stored, withdrawn_by)

    assert (raised.value.code, raised.value.message) == (code, message)
