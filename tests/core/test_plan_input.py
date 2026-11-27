import pytest

from coach.core.errors import Invalid
from coach.core.plan_input import parse_plan_input

KEY = "no_e1rm@line:2026-11-02/lower/bb_back_squat"


def a_draft(because: str, text: str) -> bytes:
    return (
        f'week = 2026-11-02\n\n[[acknowledge]]\nflag = "{KEY}"\nparams_hash = "sha256:0f"\n'
        f'because = "{because}"\ntext = "{text}"\n'
    ).encode()


def test_a_stub_left_empty_is_no_acknowledgement() -> None:
    assert parse_plan_input(a_draft("", ""), file="plan.toml").acknowledgements == ()


def test_a_filled_stub_is_an_acknowledgement() -> None:
    [found] = parse_plan_input(
        a_draft("kit", "A mislabelled plate."), file="plan.toml"
    ).acknowledgements

    assert (str(found.key), found.params_hash, found.because) == (KEY, "sha256:0f", "kit")


@pytest.mark.parametrize(("because", "text"), [("kit", ""), ("", "A mislabelled plate.")])
def test_a_stub_with_only_one_of_because_and_text_filled_is_refused(
    because: str, text: str
) -> None:
    with pytest.raises(Invalid) as refused:
        parse_plan_input(a_draft(because, text), file="plan.toml")

    assert refused.value.code == "invalid_argument"


def test_a_stub_still_names_a_warning_a_plan_leaves() -> None:
    draft = a_draft("", "").replace(b"no_e1rm", b"load_off_grid")

    with pytest.raises(Invalid) as refused:
        parse_plan_input(draft, file="plan.toml")

    assert refused.value.code == "invalid_argument"
