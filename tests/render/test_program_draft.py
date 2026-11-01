import dataclasses
import tomllib

from support.program_drafts import WORKED_DRAFT

from coach.core.program.defaults import fill
from coach.core.program.parse import parse_program_draft
from coach.render.program_draft import program_draft


def test_a_version_emits_as_an_amend_draft_that_parses_back_to_the_same_form() -> None:
    form = parse_program_draft(WORKED_DRAFT.encode(), file="v1.toml").form
    filled = fill(form, priority_lifts=("bb_bench_press",), phase=None, session_minutes=60).form

    text = program_draft(filled)

    again = parse_program_draft(text.encode(), file="draft.toml")
    assert again.unknown_keys == ()
    assert again.form == dataclasses.replace(filled, kind="amend")
    assert tomllib.loads(text)["dose"] == {"per_muscle": 10, "lift": {"bb_bench_press": 8}}


def test_a_folded_pin_is_labelled_on_its_start_load() -> None:
    form = parse_program_draft(WORKED_DRAFT.encode(), file="v1.toml").form

    text = program_draft(form, folded_pins=frozenset({("a-mon-lower", "bb_back_squat")}))

    labelled = [line.strip() for line in text.splitlines() if "# folded pin" in line]
    assert labelled == ["start_load = 120  # folded pin"]
    assert parse_program_draft(text.encode(), file="draft.toml").form == dataclasses.replace(
        form, kind="amend"
    )
