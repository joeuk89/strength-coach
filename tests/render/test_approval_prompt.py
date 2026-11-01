from support.worked_week import a_dry_run, the_worked_week

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
        acknowledged.checked, acknowledged.actions, acknowledged.write_plan_hash, units="lb"
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
