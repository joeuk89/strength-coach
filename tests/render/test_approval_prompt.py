import datetime

from support.worked_week import a_dry_run, the_worked_week

from coach.core.hevy_actions import HevyActions
from coach.core.plan_summary import PlanSummary, SummaryLine, SummarySession
from coach.core.planned_week import RotationPosition
from coach.core.prescription import PlanOverride
from coach.render.approval_prompt import approval_prompt

PROMPT_BUDGET = 40


def test_the_prompt_for_the_worked_week_fits_the_budget_and_carries_every_part() -> None:
    conn = the_worked_week()
    raised = a_dry_run(conn)
    warning = next(f for f in raised.flags if f.code == "offgrid_anchor_ignored")
    acknowledged = a_dry_run(
        conn,
        acknowledge=f'[[acknowledge]]\nflag = "{warning.key}"\n'
        f'params_hash = "{warning.params_hash}"\nbecause = "kit"\n'
        'text = "The 121 was a mislabelled plate."\n',
    )

    prompt = approval_prompt(
        acknowledged.summary, acknowledged.actions, acknowledged.write_plan_hash, units="lb"
    )

    lines = prompt.splitlines()
    assert len(lines) <= PROMPT_BUDGET
    assert lines[0] == "Plan 2026-11-02 to 2026-11-08, rotation week A"
    assert "Mon 2026-11-02 a-mon-lower (home)" in lines
    assert "  bb_back_squat 4×6–8 at 115 lb · 4×6–8 @8: 120 → 115" in lines
    assert (
        "  pin_load a-mon-lower/bb_back_squat (coach_judgement): "
        "Open under the model; the last squat was a grinder."
    ) in lines
    assert (
        "  offgrid_anchor_ignored@line:2026-11-02/a-mon-lower/bb_back_squat (kit, weekplan): "
        "The 121 was a mislabelled plate."
    ) in lines
    assert "Warnings not left" in lines
    assert any(line.startswith("  rpe_ceiling_unchecked@line:") for line in lines)
    assert "  create folder: Program" in lines
    assert lines[-1] == f"Write plan hash {acknowledged.write_plan_hash}"


def a_pin(exercise_id: str) -> PlanOverride:
    return PlanOverride(
        "pin_load",
        "lower",
        exercise_id,
        params={"load": 50},
        because="coach_judgement",
        text="It goes up one step.",
    )


def test_the_overrides_mark_each_pin_a_recovery_ceiling_reduced_or_cancelled() -> None:
    groups = [{"type": "normal", "count": 3, "load": 40.0, "load_kg": 18.14, "reps": 10}]
    session = SummarySession(
        "lower",
        datetime.date(2026, 11, 2),
        "home",
        (
            SummaryLine("db_farmers_walk", groups, "held", pin_outcome="no_effect"),
            SummaryLine("bb_hip_thrust", groups, "held", pin_outcome="reduced"),
            SummaryLine("bb_back_squat", groups, "held"),
        ),
    )
    summary = PlanSummary(
        week=datetime.date(2026, 11, 2),
        position=RotationPosition("A", "plan_in_force"),
        supersedes=None,
        sessions=(session,),
        overrides=(a_pin("db_farmers_walk"), a_pin("bb_hip_thrust"), a_pin("bb_back_squat")),
        flags=(),
    )

    lines = approval_prompt(summary, HevyActions(), "sha256:w", units="lb").splitlines()

    overrides = lines[lines.index("Overrides") + 1 : lines.index("Overrides") + 4]
    assert overrides == [
        "  pin_load lower/db_farmers_walk (coach_judgement): It goes up one step."
        " · no effect: a recovery ceiling holds the line",
        "  pin_load lower/bb_hip_thrust (coach_judgement): It goes up one step."
        " · reduced by a recovery ceiling",
        "  pin_load lower/bb_back_squat (coach_judgement): It goes up one step.",
    ]


def test_each_line_the_illness_cap_binds_says_so_and_when_it_ends() -> None:
    groups = [{"type": "normal", "count": 3, "load": 40.0, "load_kg": 18.14, "reps": 10}]
    session = SummarySession(
        "lower",
        datetime.date(2026, 11, 2),
        "home",
        (
            SummaryLine("bb_back_squat", groups, "held", illness_cap="illness until 2026-11-04"),
            SummaryLine(
                "bb_hip_thrust",
                groups,
                "held",
                illness_cap="illness until this lift is trained once",
            ),
            SummaryLine("db_farmers_walk", groups, "held"),
        ),
    )
    summary = PlanSummary(
        week=datetime.date(2026, 11, 2),
        position=RotationPosition("A", "plan_in_force"),
        supersedes=None,
        sessions=(session,),
        overrides=(),
        flags=(),
    )

    lines = approval_prompt(summary, HevyActions(), "sha256:w", units="lb").splitlines()

    assert [line.split(" · ")[-1] for line in lines[2:5]] == [
        "illness cap until 2026-11-04",
        "illness cap until this lift is trained once",
        "held",
    ]
