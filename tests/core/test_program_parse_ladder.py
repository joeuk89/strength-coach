from typing import Any

import pytest
from support.program_drafts import a_draft, a_ladder_line, a_rung, a_session, toml

from coach.core.errors import Invalid
from coach.core.program.form import Advance, Line, ProgramForm, Rung, SetGroup, line_document
from coach.core.program.parse import ParsedDraft, parse_form, parse_program_draft


def parsed(line: dict[str, Any]) -> ParsedDraft:
    return parse_program_draft(toml(a_draft(a_session("practice", line))), file="d.toml")


def the_line(form: ProgramForm) -> Line:
    return form.sessions[0].lines[0]


def test_a_ladder_reads_every_rung_with_the_first_on_the_line_exercise() -> None:
    line = a_ladder_line(
        "plank",
        a_rung(),
        a_rung("side_plank", sets=[{"count": 3, "reps": 8, "rpe": 7}], advance={"reps": 10}),
        advance={"exposures": 3},
    )

    draft = parsed(line)

    ladder = the_line(draft.form).scheme.ladder
    assert draft.unknown_keys == ()
    assert ladder is not None
    assert ladder.rungs == (
        Rung("plank", (SetGroup(2, duration_s=30, rpe=6),), "first cues"),
        Rung("side_plank", (SetGroup(3, reps=8, rpe=7),), "side_plank cues", Advance(reps=10)),
    )
    assert ladder.advance == Advance(exposures=3)


def test_a_ladder_line_stands_on_the_first_rung_sets_and_states_none_of_its_own() -> None:
    draft = parsed(a_ladder_line())

    assert the_line(draft.form).sets == (SetGroup(2, duration_s=30, rpe=6),)


def test_a_ladder_round_trips_through_the_stored_form_unchanged() -> None:
    form = parsed(a_ladder_line()).form

    again, unknown = parse_form(form.to_document(), file="stored")

    assert (again, unknown) == (form, ())
    assert "sets" not in line_document(the_line(form))


def test_sets_on_a_ladder_line_and_a_stray_rung_key_are_unknown_keys() -> None:
    line = a_ladder_line("plank", a_rung(colour="red"), a_rung("side_plank"))
    line["sets"] = [{"count": 1, "duration_s": 30, "rpe": 6}]

    assert parsed(line).unknown_keys == (
        "session.practice.line.plank.scheme.rungs.1.colour",
        "session.practice.line.plank.sets",
    )


def test_an_advance_key_outside_the_five_criterion_keys_is_unknown() -> None:
    line = a_ladder_line("plank", a_rung(advance={"clean_sets": 2}), a_rung("side_plank"))

    assert parsed(line).unknown_keys == (
        "session.practice.line.plank.scheme.rungs.1.advance.clean_sets",
    )


@pytest.mark.parametrize(
    ("line", "where"),
    [
        (a_ladder_line("plank", a_rung("side_plank"), a_rung("dead_bug")), "rungs.1.exercise"),
        (a_ladder_line("plank", a_rung(), a_rung("side_plank", sets=None)), "rungs.2.sets"),
        (a_ladder_line("plank", a_rung(), a_rung("side_plank", cues=3)), "rungs.2.cues"),
        (a_ladder_line(advance={"manual": "yes"}), "advance.manual"),
        (a_ladder_line(advance={"rpe_at_most": 11}), "advance.rpe_at_most"),
        (a_ladder_line(advance={"exposures": 0}), "advance.exposures"),
        ({**a_ladder_line(), "scheme": {"name": "exercise_ladder", "rungs": []}}, "rungs"),
    ],
)
def test_a_malformed_rung_or_criterion_stops_the_read(line: dict[str, Any], where: str) -> None:
    with pytest.raises(Invalid) as raised:
        parsed(line)

    assert f"line.plank.scheme.{where}" in raised.value.message


def test_a_rung_criterion_lays_over_the_scheme_level_one_and_manual_replaces_it() -> None:
    line = a_ladder_line(
        "plank",
        a_rung(),
        a_rung("side_plank", advance={"duration_s": 60}),
        a_rung("dead_bug", advance={"manual": True}),
        advance={"exposures": 3, "rpe_at_most": 7},
    )

    ladder = the_line(parsed(line).form).scheme.ladder

    assert ladder is not None
    assert [ladder.criterion(i) for i in (1, 2, 3)] == [
        Advance(rpe_at_most=7, exposures=3),
        Advance(duration_s=60, rpe_at_most=7, exposures=3),
        Advance(manual=True),
    ]
