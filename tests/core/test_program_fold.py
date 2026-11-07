from dataclasses import replace

from support.prescribe import a_line, a_rotation_form, working
from support.program_drafts import a_draft, a_ladder_line, a_rung, a_session, toml

from coach.core.prescription import PlanOverride
from coach.core.program.fold import Folded, fold_overrides
from coach.core.program.form import Line, ProgramForm, SchemeRef, SetGroup
from coach.core.program.parse import parse_program_draft
from coach.render.program_draft import program_draft


def on_squat(kind: str, **params: object) -> PlanOverride:
    return PlanOverride(kind, "lower-a", "bb_back_squat", params=params)


def a_form() -> ProgramForm:
    form = a_rotation_form()
    lower = form.sessions[0]
    lines = (*lower.lines, a_line("bb_bench_press", start_load=60))
    return replace(form, sessions=(replace(lower, lines=lines), *form.sessions[1:]))


def lower_lines(form: ProgramForm) -> tuple[Line, ...]:
    session = form.session("lower-a")
    assert session is not None
    return session.lines


def test_a_swap_folds_to_the_lines_exercise_load_mode_and_start_load() -> None:
    folded = fold_overrides(
        a_form(),
        (on_squat("swap_exercise", to="goblet_squat", start_load=24, load_mode="total"),),
    )

    squat = lower_lines(folded.form)[0]
    assert (squat.exercise, squat.load_mode, squat.start_load) == ("goblet_squat", "total", 24)
    assert squat.sets == a_line().sets
    assert folded.folded == (Folded("lower-a", "bb_back_squat", "swap_exercise"),)


def a_per_side_squat_form() -> ProgramForm:
    form = a_rotation_form()
    lower = form.sessions[0]
    lines = (a_line(load_mode="per_side"), *lower.lines[1:])
    return replace(form, sessions=(replace(lower, lines=lines), *form.sessions[1:]))


def test_a_swap_without_a_load_mode_keeps_the_lines_load_mode() -> None:
    folded = fold_overrides(
        a_per_side_squat_form(), (on_squat("swap_exercise", to="bb_front_squat", start_load=60),)
    )

    squat = lower_lines(folded.form)[0]
    assert (squat.exercise, squat.load_mode, squat.start_load) == ("bb_front_squat", "per_side", 60)


def test_a_swap_with_a_load_mode_replaces_the_lines_load_mode() -> None:
    folded = fold_overrides(
        a_per_side_squat_form(),
        (on_squat("swap_exercise", to="goblet_squat", start_load=24, load_mode="total"),),
    )

    assert lower_lines(folded.form)[0].load_mode == "total"


def test_a_pin_folds_to_the_start_load_and_is_named_a_folded_pin() -> None:
    pin = PlanOverride("pin_load", "lower-a", "bb_bench_press", params={"load": 100})

    folded = fold_overrides(a_form(), (pin,))

    assert lower_lines(folded.form)[1].start_load == 100
    assert folded.pins == frozenset({("lower-a", "bb_bench_press")})


def test_a_swap_and_a_pin_on_one_line_fold_together_with_the_pin_as_the_start_load() -> None:
    folded = fold_overrides(
        a_form(),
        (
            on_squat("swap_exercise", to="goblet_squat", start_load=24),
            on_squat("pin_load", load=26),
        ),
    )

    squat = lower_lines(folded.form)[0]
    assert (squat.exercise, squat.start_load) == ("goblet_squat", 26)
    assert folded.pins == frozenset({("lower-a", "goblet_squat")})


def test_restate_sets_hold_and_drop_line_fold_into_the_line() -> None:
    sets = (working(3, 5, 7),)
    bench = PlanOverride("drop_line", "lower-a", "bb_bench_press")

    folded = fold_overrides(
        a_form(), (on_squat("restate_sets", sets=sets), on_squat("hold"), bench)
    )

    [squat] = lower_lines(folded.form)
    assert squat.sets == sets
    assert squat.scheme == SchemeRef("hold")


def test_session_and_week_kinds_never_fold_and_the_draft_is_an_amend() -> None:
    form = a_form()

    folded = fold_overrides(
        form,
        (
            PlanOverride("drop_session", "lower-a"),
            PlanOverride("minimum_week", params={"keep": ("push-a",)}),
        ),
    )

    assert folded.form.sessions == form.sessions
    assert folded.form.kind == "amend"
    assert folded.folded == ()


def a_ladder_form() -> ProgramForm:
    draft = toml(a_draft(a_session("core", a_ladder_line("plank", a_rung(), a_rung("side_plank")))))
    return parse_program_draft(draft, file="d.toml").form


def test_a_swap_or_restated_sets_on_a_ladder_line_leaves_its_rungs_and_is_not_folded() -> None:
    form = a_ladder_form()
    on_plank = ("core", "plank")

    folded = fold_overrides(
        form,
        (
            PlanOverride("swap_exercise", *on_plank, params={"to": "dead_bug"}),
            PlanOverride(
                "restate_sets", *on_plank, params={"sets": (SetGroup(4, duration_s=50, rpe=7),)}
            ),
        ),
    )

    redrafted = parse_program_draft(program_draft(folded.form).encode(), file="d.toml").form
    assert redrafted.sessions == form.sessions
    assert folded.folded == ()
