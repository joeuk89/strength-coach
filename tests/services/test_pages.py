import datetime
import re

from support.blocks import two_closed_blocks
from support.closed_weeks import a_check_in, a_planned_squat_week, monday
from support.kit_fixtures import kit_files
from support.pages import the_pages
from support.plans import a_frozen_prescription, a_squat_program
from support.programs import a_config

from coach.core.hevy_actions import MapStatus
from coach.core.mirror import MirroredRoutine
from coach.render.pages import render_pages
from coach.services.pages import page_facts
from coach.store import mirrors, routine_map
from coach.store.connection import Connection

AT_175 = {"type": "working", "count": 4, "range": [6, 8], "rpe": 8, "load": 175}


def a_routine_written(
    conn: Connection, session: str, plan_id: str, status: MapStatus = "active"
) -> None:
    with conn:
        mirrors.upsert_routine(
            conn,
            MirroredRoutine(f"r-{session}", "2026-11-01T08:00:00+00:00", session, None, "{}"),
            "2026-11-01T08:00:00+00:00",
        )
        routine_map.record(
            conn,
            session,
            f"r-{session}",
            status,
            plan_id=plan_id,
            at="2026-11-01T08:00:00+00:00",
            verified=True,
        )


def a_written_squat_week() -> Connection:
    conn = a_squat_program()
    plan_id = a_planned_squat_week(conn, monday(1))
    a_frozen_prescription(
        conn, plan_id, "lower", monday(1), "db_curl", set_groups=[AT_175], change="held"
    )
    a_routine_written(conn, "lower", plan_id)
    return conn


def test_an_active_session_has_a_routine_page_titled_as_its_routine() -> None:
    pages = the_pages(a_written_squat_week(), kits=(kit_files(),))

    page = pages["pages/routines/lower.md"]
    assert "# Lower" in page
    assert "pages/routines/lower.md" in pages["README.md"]


def test_a_routine_page_at_a_plate_pool_location_links_each_loaded_line_with_the_kit_hash() -> None:
    kit = kit_files()

    page = the_pages(a_written_squat_week(), kits=(kit,))["pages/routines/lower.md"]

    assert kit.inventory_sha256 is not None
    short = kit.inventory_sha256[:8]
    assert re.findall(r"\?(?:barbell|dumbbell)[.=][^)]*", page) == [
        f"?dumbbell=175lb&dumbbell.hardware=screw-standard&kit={short}",
    ]
    assert len(re.findall(r"#inventory=", page)) == 1


def test_a_routine_page_at_a_grid_location_has_no_plate_pool_link_even_with_a_kit_file() -> None:
    conn = a_squat_program(location="gym")
    plan_id = a_planned_squat_week(conn, monday(1))
    a_frozen_prescription(
        conn, plan_id, "lower", monday(1), "bb_front_squat", set_groups=[AT_175], change="held"
    )
    a_routine_written(conn, "lower", plan_id)

    page = the_pages(conn, kits=(kit_files(), kit_files("gym")))["pages/routines/lower.md"]

    assert "plate-pool" not in page
    assert "4×6–8 @8 at 175 lb" in page


def test_a_retired_session_has_no_routine_page() -> None:
    conn = a_written_squat_week()
    a_routine_written(conn, "lower", "wp-2026-11-09", status="retired")

    assert "pages/routines/lower.md" not in the_pages(conn)


def test_the_week_page_shows_the_latest_plan_with_its_loads_and_derivation_steps() -> None:
    conn = a_squat_program()
    plan_id = a_planned_squat_week(conn, monday(0))
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        monday(0),
        "bb_front_squat",
        set_groups=[AT_175],
        change="4×6–8 @8: 170 → 175",
        steps=[{"step": "progress", "from": 170, "to": 175, "cause": "hit the top of the range"}],
        flags=[
            {
                "code": "stall_streak",
                "severity": "warning",
                "rn": "rn:autoregulation.4",
                "message": "stalled",
            }
        ],
    )

    page = the_pages(conn)["pages/week.md"]

    assert "# Week of 2026-11-02" in page
    assert "4×6–8 @8 at 175 lb" in page
    assert "| progress | 170 | 175 | hit the top of the range |" in page
    assert (
        "[rn:autoregulation.4](https://github.com/joeuk89/strength-coach/blob/v0.3.0/docs/spec/"
        "autoregulation.md)"
    ) in page


def test_every_page_carries_the_generated_header() -> None:
    pages = the_pages(a_written_squat_week(), kits=(kit_files(),))

    assert all("hand edits are overwritten" in text.splitlines()[0] for text in pages.values())


def test_the_athlete_page_carries_the_profile_verbatim_and_the_last_three_reads() -> None:
    conn = a_squat_program()
    for end in ("2026-11-08", "2026-11-15", "2026-11-22", "2026-11-29"):
        start = (datetime.date.fromisoformat(end) - datetime.timedelta(days=6)).isoformat()
        a_check_in(conn, start, end)
    profile = "Joe trains at home.\n\nNo spotter.\n"

    page = the_pages(conn, profile=profile)["pages/athlete.md"]

    assert f"## Profile\n\n{profile}" in page
    assert [line for line in page.splitlines() if line.startswith("**2026-")] == [
        "**2026-11-15**",
        "**2026-11-22**",
        "**2026-11-29**",
    ]


def test_the_progress_page_shows_each_priority_lifts_e1rm_now() -> None:
    conn = two_closed_blocks(bench_tops=(100, 105, 105, 110, 115, 115), pull_up_reps=(6,) * 6)

    page = render_pages(page_facts(conn, config=a_config(), kits=(), profile=None))[
        "pages/progress.md"
    ]

    bench = next(line for line in page.splitlines() if line.startswith("| bb_bench_press"))
    assert bench.split(" | ")[2] == "141.83"
