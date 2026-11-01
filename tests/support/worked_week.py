"""The worked six-day version adopted, ready for a plan Draft of next week."""

from coach.services.plan_apply import DryRun, dry_run
from coach.services.program import adopt
from coach.store import exercises
from coach.store.connection import Connection
from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import SQUAT_TEMPLATE, squat_logged
from support.program_drafts import WORKED_DRAFT_COMPLETE
from support.programs import a_config, the_worked_store

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
                exercises.update(conn, str(row["id"]), {"hevy_template_id": f"T-{n:04d}"})
        exercises.update(conn, "bb_back_squat", {"hevy_template_id": SQUAT_TEMPLATE})
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
    """The dry run of next week's Draft with the squat pinned at 115 lb."""
    data = a_plan_draft(conn, overrides=PIN, acknowledge=acknowledge, hevy=True)
    return dry_run(
        conn,
        data,
        file="plan.toml",
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )
