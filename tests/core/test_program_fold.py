from dataclasses import replace

from support.prescribe import a_line, a_rotation_form, working

from coach.core.prescription import PlanOverride
from coach.core.program.fold import Folded, fold_overrides
from coach.core.program.form import Line, ProgramForm, SchemeRef


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
