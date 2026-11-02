from support.program_drafts import WORKED_DRAFT, a_draft, a_session, toml

from coach.core.program.defaults import fill
from coach.core.program.form import Deload, Dose, LiftDose, ProgramForm
from coach.core.program.parse import parse_program_draft

PRIORITY = ("bb_bench_press", "pull_up")


def form_of(draft: dict[str, object]) -> ProgramForm:
    return parse_program_draft(toml(draft), file="d.toml").form


def test_the_worked_draft_is_filled_with_the_hypertrophy_defaults() -> None:
    form = parse_program_draft(WORKED_DRAFT.encode(), file="v1.toml").form

    filled = fill(form, priority_lifts=PRIORITY, phase=None, session_minutes=60)

    assert filled.form.dose == Dose(10, {"bb_bench_press": LiftDose(8), "pull_up": LiftDose(8)})
    assert filled.form.deload == Deload(6, 40, 0, 8, True)
    assert filled.filled == ("dose", "deload", "session.a-mon-lower.minutes")
    minutes = {s.id: s.minutes for s in filled.form.sessions}
    assert minutes == {"pt-tuesday": None, "a-mon-lower": 60, "b-sat-push": 90, "a-sat-pull": 90}


def test_an_authored_line_is_never_changed() -> None:
    form = parse_program_draft(WORKED_DRAFT.encode(), file="v1.toml").form

    filled = fill(form, priority_lifts=PRIORITY, phase=None, session_minutes=60)

    assert [s.lines for s in filled.form.sessions] == [s.lines for s in form.sessions]


def test_strength_cuts_thirty_percent_of_sets() -> None:
    filled = fill(
        form_of(a_draft(emphasis="strength")),
        priority_lifts=("bb_bench_press",),
        phase="maintenance",
        session_minutes=60,
    )

    assert filled.form.dose == Dose(10, {"bb_bench_press": LiftDose(8)})
    assert filled.form.deload == Deload(6, 30, 0, 8, True)


def test_a_surplus_fills_the_upper_half_of_the_band_and_a_deficit_holds_the_default() -> None:
    surplus = fill(form_of(a_draft()), priority_lifts=PRIORITY, phase="surplus", session_minutes=60)
    deficit = fill(form_of(a_draft()), priority_lifts=PRIORITY, phase="deficit", session_minutes=60)

    assert surplus.form.dose == Dose(15, {"bb_bench_press": LiftDose(10), "pull_up": LiftDose(10)})
    assert deficit.form.dose == Dose(10, {"bb_bench_press": LiftDose(8), "pull_up": LiftDose(8)})


def test_maintenance_fills_a_third_of_the_dose_and_no_planned_deload() -> None:
    filled = fill(
        form_of(a_draft(emphasis="maintenance")),
        priority_lifts=PRIORITY,
        phase=None,
        session_minutes=60,
    )

    assert filled.form.dose == Dose(4, {"bb_bench_press": LiftDose(3), "pull_up": LiftDose(3)})
    assert filled.form.deload == Deload(6, 0, 0, 8, False)


def test_an_authored_dose_deload_and_minutes_stand() -> None:
    draft = a_draft(
        a_session("push", minutes=45),
        dose={"per_muscle": 12, "lift": {}},
        deload={
            "hard_weeks_ceiling": 5,
            "set_cut_pct": 50,
            "load_cut_pct": 10,
            "rpe_cap": 7,
            "test_priority_lifts": False,
        },
    )

    filled = fill(form_of(draft), priority_lifts=PRIORITY, phase=None, session_minutes=60)

    assert filled.filled == ()
    assert filled.form.dose == Dose(12, {})
    assert filled.form.deload == Deload(5, 50, 10, 7, False)
    assert filled.form.sessions[0].minutes == 45


def test_only_a_lifting_session_takes_the_athletes_minutes() -> None:
    drill = a_session("drill", kind="practice", tier="optional", cadence="daily")

    filled = fill(form_of(a_draft(drill)), priority_lifts=(), phase=None, session_minutes=60)

    assert filled.form.sessions[0].minutes is None
