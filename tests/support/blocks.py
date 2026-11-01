"""Scenario builders for the block boundary: a push session (bench on `top_backoff`, the pull-up
on `double_progression`) trained through two Blocks that each close with a light week. Each
writes only through `store` functions or the services that own the record."""

import datetime
from collections.abc import Sequence
from typing import Any

from coach.core.units import KG_PER_LB
from coach.store import exercises
from coach.store.connection import Connection
from support.closed_weeks import closed_through, monday
from support.history import Logged, a_logged_workout
from support.plans import a_frozen_prescription, a_plan_override, a_squat_program, an_approved_plan
from support.program_drafts import a_line, a_session

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


def a_push_program(*lines: dict[str, Any]) -> Connection:
    conn = a_squat_program(a_session("push", *(lines or (BENCH_LINE, PULL_UP_LINE))))
    with conn:
        exercises.update(conn, "bb_bench_press", {"hevy_template_id": BENCH_TEMPLATE})
        exercises.update(conn, "pull_up", {"hevy_template_id": PULL_UP_TEMPLATE})
    return conn


def two_closed_blocks(
    conn: Connection | None = None,
    *,
    bench_tops: Sequence[float] = FLAT_BENCH,
    pull_up_reps: Sequence[int] = (6,) * WEEKS,
    steps: Sequence[dict[str, object]] = (),
) -> Connection:
    """Six weeks of `push` on each Monday, weeks 3 and 6 light, all closed by one Check-in:
    Blocks b-2026-10-30 and b-2026-11-23 closed, b-2026-12-14 open. Bench logs a top set of
    `bench_tops[week]` × 5 at RPE 8 and three back-offs at 85 %, in lb."""
    conn = conn or a_push_program()
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
        a_logged_workout(
            conn,
            f"h-push-{week}",
            monday(week),
            (BENCH_TEMPLATE, tuple((_kg(lb), reps, rpe) for lb, reps, rpe in bench)),
            (PULL_UP_TEMPLATE, pull_ups),
        )
    closed_through(conn, WEEKS)
    return conn


BOUNDARY = datetime.date(2026, 12, 14)


def _kg(lb: float | None) -> float | None:
    return None if lb is None else lb * KG_PER_LB
