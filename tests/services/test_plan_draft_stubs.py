import tomllib
from typing import Any

from support.clock import FixedClock
from support.history import a_status_span
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import a_squat_program, squat_logged
from support.programs import a_config

from coach.services.plan_apply import DryRun, dry_run
from coach.store import exercises
from coach.store.connection import Connection


def run(conn: Connection, data: bytes) -> DryRun:
    return dry_run(
        conn, data, file="plan.toml", config=a_config(), kits=(kit_files(),), clock=FixedClock()
    )


def a_three_warning_week() -> Connection:
    """The squat logged at 101 lb, off the rack and too far from failure for an e1RM, then two
    ill days: `over_rep_cap`, `offgrid_anchor_ignored` and `rpe_ceiling_unchecked`."""
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(101, 15, 7)] * 4)
    a_status_span(conn, "ss-0001", "ill", "2026-10-28", "2026-10-29")
    return conn


def stubs(data: bytes) -> list[dict[str, Any]]:
    return tomllib.loads(data.decode("utf-8"))["acknowledge"]


def test_a_draft_with_three_warnings_carries_three_stubs_matching_the_dry_run() -> None:
    conn = a_three_warning_week()
    draft = a_plan_draft(conn)

    dry = run(conn, draft)

    assert [(s["flag"], s["params_hash"], s["because"], s["text"]) for s in stubs(draft)] == [
        (f.key, f.params_hash, "", "") for f in dry.flags
    ]
    assert [f.code for f in dry.flags] == [
        "over_rep_cap",
        "offgrid_anchor_ignored",
        "rpe_ceiling_unchecked",
    ]


def test_untouched_stubs_pass_the_dry_run_with_each_warning_unacknowledged() -> None:
    conn = a_three_warning_week()

    dry = run(conn, a_plan_draft(conn))

    assert dry.write_plan_hash.startswith("sha256:")
    assert dry.acknowledgements == ()
    assert [f.left for f in dry.flags] == [None, None, None]


def test_hevy_template_missing_has_its_flag_table_under_its_line_with_hevy_on() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    with conn:
        exercises.update(conn, "bb_back_squat", {"hevy_template_id": None})

    with_hevy = tomllib.loads(a_plan_draft(conn, hevy=True).decode("utf-8"))
    without = tomllib.loads(a_plan_draft(conn).decode("utf-8"))

    [line] = with_hevy["session"][0]["line"]
    assert "hevy_template_missing@line:2026-11-02/lower/bb_back_squat" in {
        f["key"] for f in line["flag"]
    }
    assert all(
        f["code"] != "hevy_template_missing" for f in without["session"][0]["line"][0]["flag"]
    )
