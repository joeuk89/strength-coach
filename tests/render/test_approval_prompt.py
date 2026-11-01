from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import SQUAT_TEMPLATE, squat_logged
from support.program_drafts import WORKED_DRAFT_COMPLETE
from support.programs import a_config, the_worked_store

from coach.render.approval_prompt import approval_prompt
from coach.services.plan_apply import DryRun, dry_run
from coach.services.program import adopt
from coach.store import exercises
from coach.store.connection import Connection

PROMPT_BUDGET = 40
PIN = """
[[override]]
kind = "pin_load"
session = "a-mon-lower"
exercise = "bb_back_squat"
load = 115
because = "coach_judgement"
text = "Open under the model; the last squat was a grinder."
"""


def the_worked_week() -> Connection:
    """The worked six-day version, every exercise with a Hevy template, and the squat last
    logged at 121 lb, off the rack."""
    conn = the_worked_store()
    with conn:
        for n, row in enumerate(exercises.every(conn)):
            if not row["hevy_template_id"]:
                template = SQUAT_TEMPLATE if row["id"] == "bb_back_squat" else f"T-{n:04d}"
                exercises.update(conn, str(row["id"]), {"hevy_template_id": template})
    config = a_config(hevy=True)
    adopt(
        conn,
        WORKED_DRAFT_COMPLETE.encode(),
        file="v1.toml",
        config=config,
        kits=(kit_files(),),
        clock=FixedClock(),
    )
    squat_logged(conn, "h-1", "2026-10-26", *[(121, 8, 8)] * 4)
    return conn


def a_dry_run(conn: Connection, *, acknowledge: str = "") -> DryRun:
    data = a_plan_draft(conn, overrides=PIN, acknowledge=acknowledge, hevy=True)
    return dry_run(
        conn,
        data,
        file="plan.toml",
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


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
