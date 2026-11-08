"""Scenario builders for the block boundary: a push session (bench on `top_backoff`, the pull-up
on `double_progression`) trained through two Blocks that each close with a light week. Each
writes only through `store` functions or the services that own the record."""

import datetime
from collections.abc import Sequence

from coach.core.goal import Milestone, Target
from coach.core.units import KG_PER_LB
from coach.services.program import adopt
from coach.store import exercises
from coach.store.connection import Connection
from support.clock import FixedClock
from support.closed_weeks import closed_through, monday
from support.history import Logged, a_logged_workout
from support.kit_fixtures import kit_files
from support.plans import a_frozen_prescription, a_plan_override, an_approved_plan
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config, a_goal, a_library_store, a_phase

BENCH_TEMPLATE = "BP-0001"
PULL_UP_TEMPLATE = "PU-0001"
TOP_SETS = [{"count": 1, "reps": 5, "rpe": 8}, {"count": 3, "reps": 5, "rpe": 7}]
BENCH_LINE = a_line(
    "bb_bench_press",
    sets=TOP_SETS,
    scheme={"name": "top_backoff", "pct_of_top": 85},
    start_load=100,
)
PULL_UP_LINE = a_line("pull_up", sets=[{"count": 3, "reps": [5, 8], "rpe": 8}], start_load=None)
LIGHT_WEEKS = (2, 5)
WEEKS = 6
FLAT_BENCH = (100.0,) * WEEKS


WHY = "Look athletic in a t-shirt, and bench my bodyweight before I'm 40."
MILESTONES = (
    Milestone("bb_bench_press", Target("load_x_reps", load=110, reps=5)),
    Milestone("bb_bench_press", Target("bodyweight_multiple", 0.75)),
)


def a_drill(*lines: dict[str, object]) -> dict[str, object]:
    """A practice session scheduled like any other."""
    return a_session("drill", *lines, kind="practice", tier="optional")


def a_push_program(
    bench_line: dict[str, object] = BENCH_LINE,
    pull_up_line: dict[str, object] = PULL_UP_LINE,
    practice_pull_ups: bool = False,
) -> Connection:
    """The worked Goal with a `why` and two bench milestones, the maintenance Phase, and `push`
    adopted on 30 Oct 2026. With `practice_pull_ups` the pull-up line stands alone in `drill`."""
    conn = a_library_store()
    a_goal(conn, why=WHY, milestones=MILESTONES)
    a_phase(conn, "maintenance")
    sessions = (
        (a_session("push", bench_line), a_drill(pull_up_line))
        if practice_pull_ups
        else (a_session("push", bench_line, pull_up_line),)
    )
    adopt(
        conn,
        toml(a_draft(*sessions)),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )
    with conn:
        exercises.update(conn, "bb_bench_press", {"hevy_template_id": BENCH_TEMPLATE})
        exercises.update(conn, "pull_up", {"hevy_template_id": PULL_UP_TEMPLATE})
    return conn


def two_closed_blocks(
    *,
    bench_tops: Sequence[float] = FLAT_BENCH,
    pull_up_reps: Sequence[int] = (6,) * WEEKS,
    steps: Sequence[dict[str, object]] = (),
    bench_line: dict[str, object] = BENCH_LINE,
    thursday_pull_ups: bool = False,
    pull_up_line: dict[str, object] = PULL_UP_LINE,
    practice_pull_ups: bool = False,
) -> Connection:
    """Six weeks of `push` on each Monday, weeks 3 and 6 light, all closed by one Check-in:
    Blocks b-2026-10-30 and b-2026-11-23 closed, b-2026-12-14 open. Bench logs a top set of
    `bench_tops[week]` × 5 at RPE 8 and three back-offs at 85 %, in lb. With
    `thursday_pull_ups` each ordinary week also logs the week's pull-ups in an unplanned
    Thursday workout, so each Block holds three ordinary pull-up exposures. With
    `practice_pull_ups` the pull-up line stands alone in the practice session `drill` and its
    Monday log moves to Wednesday, matched to `drill`."""
    conn = a_push_program(bench_line, pull_up_line, practice_pull_ups)
    for week in range(WEEKS):
        plan_id = an_approved_plan(conn, monday(week))
        a_frozen_prescription(
            conn,
            plan_id,
            "push",
            monday(week),
            "bb_bench_press",
            set_groups=[{"type": "working", **group} for group in TOP_SETS],
            change="held",
            steps=steps,
        )
        if week in LIGHT_WEEKS:
            a_plan_override(conn, plan_id, "light_week", None, None)
        top = bench_tops[week]
        bench: tuple[Logged, ...] = ((top, 5, 8), *[(top * 0.85, 5, 7)] * 3)
        pull_ups: tuple[Logged, ...] = tuple((None, pull_up_reps[week], 8) for _ in range(3))
        bench_sets = (BENCH_TEMPLATE, tuple((_kg(lb), reps, rpe) for lb, reps, rpe in bench))
        if practice_pull_ups:
            a_logged_workout(conn, f"h-push-{week}", monday(week), bench_sets)
            a_logged_workout(
                conn,
                f"h-drill-{week}",
                _days_after_monday(week, 2),
                (PULL_UP_TEMPLATE, pull_ups),
                session_id="drill",
            )
        else:
            a_logged_workout(
                conn, f"h-push-{week}", monday(week), bench_sets, (PULL_UP_TEMPLATE, pull_ups)
            )
        if thursday_pull_ups and week not in LIGHT_WEEKS:
            a_logged_workout(
                conn, f"h-pull-{week}", _days_after_monday(week, 3), (PULL_UP_TEMPLATE, pull_ups)
            )
    closed_through(conn, WEEKS)
    return conn


def _days_after_monday(week: int, days: int) -> str:
    return (datetime.date.fromisoformat(monday(week)) + datetime.timedelta(days=days)).isoformat()


BOUNDARY = datetime.date(2026, 12, 14)


def _kg(lb: float | None) -> float | None:
    return None if lb is None else lb * KG_PER_LB
