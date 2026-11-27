import datetime
import tomllib

import pytest
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import SQUAT_LINE, SQUAT_TEMPLATE, a_squat_program, squat_logged
from support.program_drafts import a_line, a_session
from support.programs import a_config

from coach.core.errors import Invalid
from coach.core.mirror import Routine
from coach.render.approval_prompt import approval_prompt
from coach.services.hevy_import import import_hevy
from coach.services.plan_apply import ApplyResult, DryRun, apply, dry_run
from coach.services.record import record
from coach.services.status import status
from coach.store import exercises, routine_map, week_plans
from coach.store.connection import Connection

BENCH_TEMPLATE = "BP-0001"
LATER = FixedClock(datetime.datetime(2026, 10, 31, 9, 0, tzinfo=datetime.UTC))

AVOID_BENCH = """
[[niggle]]
site = "left shoulder"
date = 2026-10-29
status = "reported"

[[niggle.constraints]]
kind = "avoid"
exercise = "bb_bench_press"
"""


def an_avoided_bench(
    *sessions: dict[str, object], bench: dict[str, object] | None = None
) -> Connection:
    """`lower` holds the squat and the bench; an open niggle avoids the bench."""
    conn = a_squat_program(
        *(sessions or (a_session("lower", SQUAT_LINE, a_line("bb_bench_press")),))
    )
    with conn:
        exercises.update(conn, "bb_bench_press", bench or {"hevy_template_id": BENCH_TEMPLATE})
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    record(conn, AVOID_BENCH.encode(), file="niggle.toml", clock=FixedClock())
    return conn


def checked(conn: Connection, data: bytes) -> DryRun:
    return dry_run(
        conn,
        data,
        file="plan.toml",
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


def applied(conn: Connection, hevy: FakeHevy, data: bytes) -> ApplyResult:
    config = a_config(hevy=True)
    digest = dry_run(
        conn, data, file="plan.toml", config=config, kits=(kit_files(),), clock=FixedClock()
    ).write_plan_hash
    return apply(
        conn,
        hevy,
        data,
        file="plan.toml",
        expect=digest,
        config=config,
        kits=(kit_files(),),
        clock=FixedClock(),
    )


def templates(routine: Routine) -> list[str]:
    return [e.hevy_template_id for e in routine.exercises]


def test_a_week_with_an_avoided_line_applies_and_verifies_without_that_exercise() -> None:
    conn = an_avoided_bench()
    hevy = FakeHevy(FixedClock())

    result = applied(conn, hevy, a_plan_draft(conn, hevy=True))

    assert [(o.session_id, o.outcome) for o in result.routines] == [("lower", "verified")]
    assert templates(hevy.routine(routine_map.mapped(conn)["lower"])) == [SQUAT_TEMPLATE]


def test_an_avoided_line_needs_no_hevy_template_and_creates_none() -> None:
    conn = an_avoided_bench(bench={"hevy_template_id": None, "hevy_title": None})
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)

    found = checked(conn, data)
    result = applied(conn, hevy, data)

    assert "hevy_template_missing" not in {flag.code for flag in found.flags}
    assert found.actions.templates == ()
    assert [(o.session_id, o.outcome) for o in result.routines] == [("lower", "verified")]
    assert ("POST", "/v1/exercise_templates") not in hevy.calls


def test_a_session_whose_every_line_is_avoided_gets_no_routine() -> None:
    conn = an_avoided_bench(
        a_session("lower", SQUAT_LINE), a_session("upper", a_line("bb_bench_press"))
    )
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)

    found = checked(conn, data)
    result = applied(conn, hevy, data)

    assert found.actions.to_json()["routines"] == {
        "update": [],
        "create": [{"session": "lower", "routine": None}],
        "retire": [],
    }
    assert [o.session_id for o in result.routines] == ["lower"]
    assert set(routine_map.mapped(conn)) == {"lower"}


def test_the_draft_and_the_prompt_still_name_the_avoided_line_and_its_cause() -> None:
    conn = an_avoided_bench()
    data = a_plan_draft(conn, hevy=True)

    found = checked(conn, data)
    prompt = approval_prompt(found.summary, found.actions, found.write_plan_hash, units="lb")

    [drafted] = tomllib.loads(data.decode())["session"]
    bench = drafted["line"][1]
    assert (bench["exercise"], bench["change"], bench["sets"]) == ("bb_bench_press", "dropped", [])
    assert bench["step"][-1] == {"step": "niggle", "cause": "avoid niggle:n-0001"}
    [lower] = found.summary.sessions
    assert [(line.exercise_id, line.change, line.set_groups) for line in lower.lines][1] == (
        "bb_bench_press",
        "dropped",
        [],
    )
    assert "  bb_bench_press no working set · dropped (avoid niggle:n-0001)" in prompt.splitlines()


def a_stuck_plan(conn: Connection, hevy: FakeHevy, data: bytes) -> str:
    """The WeekPlan approved with the avoided line frozen with no set, its push stopped on the
    first read-back; returns the approved hash."""
    digest = checked(conn, data).write_plan_hash
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        apply(
            conn,
            hevy,
            data,
            file="plan.toml",
            expect=digest,
            config=a_config(hevy=True),
            kits=(kit_files(),),
            clock=FixedClock(),
        )
    return digest


def test_a_week_plan_frozen_with_an_empty_set_row_verifies_on_resume() -> None:
    conn = an_avoided_bench(
        a_session("lower", SQUAT_LINE, a_line("bb_bench_press")),
        a_session("upper", a_line("bb_bench_press")),
        bench={"hevy_template_id": None},
    )
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = a_stuck_plan(conn, hevy, data)
    frozen = {
        (r["session_id"], r["exercise_id"]): r["set_groups"]
        for r in week_plans.prescriptions(conn, "wp-2026-11-02")
    }

    found = checked(conn, data)
    resumed = applied(conn, hevy, data)

    assert frozen[("lower", "bb_bench_press")] == frozen[("upper", "bb_bench_press")] == []
    assert routine_map.every(conn)[0][2] == "active"
    assert (found.resumes, found.write_plan_hash) == ("wp-2026-11-02", digest)
    assert found.actions.to_json() == {
        "folders_to_create": [],
        "routines": {
            "update": [{"session": "lower", "routine": routine_map.mapped(conn)["lower"]}],
            "create": [],
            "retire": [],
        },
        "templates_to_create": [],
    }
    assert [(o.session_id, o.outcome) for o in resumed.routines] == [("lower", "verified")]
    assert templates(hevy.routine(routine_map.mapped(conn)["lower"])) == [SQUAT_TEMPLATE]
    shown = approval_prompt(found.summary, found.actions, found.write_plan_hash, units="lb")
    assert "  bb_bench_press no working set · dropped (avoid niggle:n-0001)" in shown.splitlines()


def test_an_import_after_the_push_raises_no_routine_drift_for_that_routine() -> None:
    conn = an_avoided_bench()
    hevy = FakeHevy(FixedClock())
    applied(conn, hevy, a_plan_draft(conn, hevy=True))

    found = import_hevy(conn, hevy, LATER, full=False, units="lb")

    assert [f.code for f in found.warnings if f.code == "routine_drift"] == []


def test_status_lists_no_unverified_routine_for_a_session_whose_every_line_is_avoided() -> None:
    conn = a_squat_program(
        a_session("lower", SQUAT_LINE), a_session("upper", a_line("bb_bench_press"))
    )
    with conn:
        exercises.update(conn, "bb_bench_press", {"hevy_template_id": BENCH_TEMPLATE})
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    hevy = FakeHevy(FixedClock())
    applied(conn, hevy, a_plan_draft(conn, hevy=True))
    record(conn, AVOID_BENCH.encode(), file="niggle.toml", clock=FixedClock())
    applied(conn, hevy, a_plan_draft(conn, hevy=True, week=datetime.date(2026, 11, 9)))

    shown = status(
        conn,
        FixedClock(datetime.datetime(2026, 11, 10, 9, 0, tzinfo=datetime.UTC)),
        engine_version="0.3.0",
        pin="0.3.0",
        hevy_on=True,
        exported={},
        units="lb",
    ).plan

    assert shown is not None
    assert (shown.week, shown.routines_verified, shown.routines_unverified) == (
        "2026-11-09",
        2,
        (),
    )


def test_an_import_skips_a_routine_its_plan_wrote_for_a_session_whose_every_line_is_avoided() -> (
    None
):
    conn = an_avoided_bench(
        a_session("lower", SQUAT_LINE), a_session("upper", a_line("bb_bench_press"))
    )
    hevy = FakeHevy(FixedClock())
    applied(conn, hevy, a_plan_draft(conn, hevy=True))
    with conn:
        routine_map.record(
            conn,
            "upper",
            routine_map.mapped(conn)["lower"],
            "unverified",
            plan_id="wp-2026-11-02",
            at="2026-10-30T09:00:00Z",
            verified=False,
        )

    found = import_hevy(conn, hevy, LATER, full=False, units="lb")

    assert [f for f in found.warnings if f.code == "routine_drift"] == []
