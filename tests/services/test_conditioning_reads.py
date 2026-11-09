"""A conditioning workout's sets anchor its own session's lines and nothing else (ADR 0010):
a lifting line on the same exercise, its e1RM and `coach progress` never read them."""

import datetime

from support.clock import FixedClock
from support.closed_weeks import closed_through, monday
from support.history import a_logged_workout
from support.kit_fixtures import kit_files
from support.plans import SQUAT_LINE, SQUAT_TEMPLATE, an_approved_plan, squat_logged
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config, a_goal, a_library_store, a_phase

from coach.core.prescription import LinePrescription
from coach.core.progress import LiftProgress
from coach.services.plan_draft import plan_draft
from coach.services.program import adopt
from coach.services.progress import progress
from coach.store import exercises
from coach.store.connection import Connection

SWING_TEMPLATE = "F8A0FCCA"
SWINGS = a_session(
    "cond-swings",
    a_line("kb_swing", scheme={"name": "hold"}, start_load=35, sets=[{"count": 1, "reps": 12}]),
    kind="conditioning",
    tier="optional",
    minutes=16,
    scheme={
        "name": "emom_density",
        "minutes": 12,
        "minutes_cap": 16,
        "minutes_step": 2,
        "reps": {"kb_swing": 12},
        "reps_cap": {"kb_swing": 15},
        "rpe_target": 8,
    },
)
HINGE = a_session(
    "hinge",
    a_line(
        "kb_swing",
        sets=[{"count": 1, "reps": 5, "rpe": 8}, {"count": 3, "reps": 5, "rpe": 7}],
        scheme={"name": "top_backoff", "pct_of_top": 85},
        start_load=35,
    ),
)
SCHEDULE = {"rotation": ["A"], "A": {"mon": ["lower", "cond-swings"], "wed": ["hinge"]}}
# 40 kg × 10 @ RPE 9 is 11 reps to failure: an e1RM point well above any lifting swing here.
HEAVY_SWINGS = ((40.0, 10, 9.0),) * 3


def a_swings_program() -> Connection:
    """Swings as the priority lift, on `top_backoff` in `hinge` on Wednesdays and as the
    conditioning session beside `lower` on Mondays, adopted on 30 Oct 2026."""
    conn = a_library_store()
    a_goal(conn, priority_lifts=("kb_swing",))
    a_phase(conn, "maintenance")
    with conn:
        exercises.update(conn, "bb_back_squat", {"hevy_template_id": SQUAT_TEMPLATE})
    adopt(
        conn,
        toml(a_draft(a_session("lower", SQUAT_LINE), SWINGS, HINGE, schedule=SCHEDULE)),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )
    return conn


def a_week_of(*, lifting_swings: bool, conditioning_swings: bool) -> Connection:
    """The first week approved; `h-2`, matched to `cond-swings`, logs heavy swings. The lifting
    swings were logged in an unmatched workout the Wednesday before."""
    conn = a_swings_program()
    if lifting_swings:
        a_logged_workout(conn, "h-0", "2026-10-28", (SWING_TEMPLATE, ((24.0, 5, 8.0),) * 4))
    an_approved_plan(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 8)] * 4)
    if conditioning_swings:
        a_logged_workout(conn, "h-2", monday(0), (SWING_TEMPLATE, HEAVY_SWINGS))
    return conn


def next_week_line(conn: Connection, session_id: str) -> LinePrescription:
    draft = plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(datetime.datetime(2026, 11, 8)),
        week=datetime.date.fromisoformat(monday(1)),
        position="A",
    ).draft
    [line] = [
        line
        for s in draft.sessions
        if s.session.session_id == session_id
        for line in s.lines
        if line.exercise_id == "kb_swing"
    ]
    return line


def swings_progress(conn: Connection) -> LiftProgress:
    closed_through(conn, 1)
    found = progress(
        conn,
        on=datetime.date(2026, 11, 8),
        units="lb",
        bodyweight_units="kg",
        full=True,
        zone=datetime.UTC,
    )
    [lift] = found.lifts
    return lift


def test_the_conditioning_swings_change_nothing_on_the_lifting_swing_line() -> None:
    without = next_week_line(a_week_of(lifting_swings=True, conditioning_swings=False), "hinge")
    with_ = next_week_line(a_week_of(lifting_swings=True, conditioning_swings=True), "hinge")

    assert with_ == without
    assert with_.derived_from == "exposure:h-0/kb_swing"


def test_a_lifting_line_with_only_conditioning_history_falls_to_its_start_load() -> None:
    line = next_week_line(a_week_of(lifting_swings=False, conditioning_swings=True), "hinge")

    top = line.groups[0].load
    assert line.derived_from == "start_load"
    assert top is not None and top.amount == 35


def test_the_conditioning_hold_line_still_anchors_on_its_own_heavy_swings() -> None:
    line = next_week_line(a_week_of(lifting_swings=True, conditioning_swings=True), "cond-swings")

    assert line.derived_from == "exposure:h-2/kb_swing"


def test_the_conditioning_swings_change_no_priority_lift_figure_in_progress() -> None:
    without = swings_progress(a_week_of(lifting_swings=True, conditioning_swings=False))
    with_ = swings_progress(a_week_of(lifting_swings=True, conditioning_swings=True))

    assert without.e1rm_now is not None
    assert with_ == without
