"""A core session split across two Hevy workouts on a day that also plans a daily practice
session and an optional conditioning session (docs/spec/week.md, "Match")."""

from typing import Any, cast

from support.check_in_cards import opened
from support.closed_weeks import closed_through, monday
from support.history import a_logged_workout, an_annotation
from support.plans import (
    SQUAT_LINE,
    SQUAT_TEMPLATE,
    a_frozen_prescription,
    a_plan_override,
    a_squat_program,
    an_approved_plan,
)
from support.program_drafts import a_line, a_session

from coach.core.check_in_card import Card
from coach.core.closed_week.week import ClosedWeek
from coach.services.closed_weeks import closed_weeks
from coach.store import exercises
from coach.store.connection import Connection

BENCH_TEMPLATE = "BP-0001"
DB_BENCH_TEMPLATE = "3601968B"
HANG_TEMPLATE = "B9380898"
PULL_UP_TEMPLATE = "PU-0001"
SWING_TEMPLATE = "F8A0FCCA"
BENCH_LINE = a_line("bb_bench_press", sets=[{"count": 3, "reps": [6, 8], "rpe": 8}])
LOWER = a_session("lower", SQUAT_LINE, BENCH_LINE)
HANG = a_session(
    "daily-hang",
    a_line(
        "dead_hang", scheme={"name": "hold"}, start_load=None, sets=[{"count": 3, "duration_s": 30}]
    ),
    kind="practice",
    tier="optional",
    cadence="daily",
)
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
SQUATS = (SQUAT_TEMPLATE, ((54.0, 8, 8.0),) * 4)
# Five reps under a bottom of six: three reps missed. RPE 9 is one over target, not effort off.
BENCH = (BENCH_TEMPLATE, ((45.0, 5, 9.0),) * 3)


def a_split_monday(
    *, second_routine: str | None = None, second: Any = BENCH, bench: str = "bb_bench_press"
) -> Connection:
    """`lower`, `daily-hang` and `cond-swings` all planned on Monday 2 Nov 2026, `lower`
    frozen with its squat and bench lines. `h-1` logs the squats in the morning and `h-2` the
    rest of the session in the afternoon. A `bench` other than the authored one freezes under a
    `swap_exercise` override."""
    conn = a_squat_program(
        LOWER, HANG, SWINGS, schedule={"rotation": ["A"], "A": {"mon": ["lower", "cond-swings"]}}
    )
    with conn:
        exercises.update(conn, "bb_bench_press", {"hevy_template_id": BENCH_TEMPLATE})
    plan_id = an_approved_plan(conn, monday(0))
    if bench != "bb_bench_press":
        a_plan_override(conn, plan_id, "swap_exercise", "lower", "bb_bench_press", to=bench)
    for exercise, sets in (("bb_back_squat", 4), (bench, 3)):
        a_frozen_prescription(
            conn,
            plan_id,
            "lower",
            monday(0),
            exercise,
            set_groups=[{"type": "working", "count": sets, "range": [6, 8], "rpe": 8}],
            change="held",
        )
    a_logged_workout(conn, "h-1", monday(0), SQUATS, minutes=40, started="07:00")
    a_logged_workout(
        conn, "h-2", monday(0), second, routine_id=second_routine, minutes=25, started="15:00"
    )
    return conn


def the_week(conn: Connection) -> ClosedWeek:
    closed_through(conn, 1)
    [week] = closed_weeks(conn).weeks
    return week


def matched_on_monday(week: ClosedWeek) -> dict[str, tuple[str, ...]]:
    return {
        s.session.session_id: s.workout_ids
        for s in week.sessions
        if s.session.date.isoformat() == monday(0)
    }


def facts(card: Card, name: str) -> dict[str, Any]:
    field = next((f for f in card.fields if f.name == name), None)
    return {} if field is None else cast(dict[str, Any], field.facts)


def test_both_workouts_of_a_split_session_match_the_core_session() -> None:
    week = the_week(a_split_monday())

    assert matched_on_monday(week) == {
        "lower": ("h-1", "h-2"),
        "cond-swings": (),
        "daily-hang": (),
    }


def test_the_second_workout_matches_the_core_session_with_its_routine_id_too() -> None:
    week = the_week(a_split_monday(second_routine="r-lower"))

    assert matched_on_monday(week)["lower"] == ("h-1", "h-2")


def test_the_second_workout_is_no_activity_and_counts_for_no_optional_session() -> None:
    card = opened(a_split_monday())

    assert facts(card, "activities").get("rows", []) == []
    assert facts(card, "sessions")["optional"] == {"done": 0, "planned": 8}


def test_the_dose_and_the_lift_rows_include_the_second_workouts_sets() -> None:
    conn = a_split_monday()

    lifts = [r["exercise"] for r in facts(opened(conn), "lifts")["rows"]]
    week = the_week(conn)

    assert sorted(lifts) == ["bb_back_squat", "bb_bench_press"]
    assert week.dose["chest"] == 3


def test_the_core_sessions_row_reads_against_minutes_and_rpe_over_both_workouts() -> None:
    [lower] = facts(opened(a_split_monday()), "sessions")["core"]

    assert lower == {
        "session": f"planned_session:{monday(0)}/lower",
        "kind": "lifting",
        "state": "matched",
        "workouts": ["h-1", "h-2"],
        "minutes": 65,
        "session_rpe": 8.4,
        "sets_logged": 7,
        "sets_prescribed": 7,
        "gate_passed": True,
        "against": {"reps_missed": 3, "effort_off": 0, "rpe_missing": 0},
    }


def test_a_match_claiming_a_second_workout_for_the_core_session_leaves_the_first_on_it() -> None:
    conn = a_split_monday(second=(HANG_TEMPLATE, ((None, 30, 8.0),) * 3))
    an_annotation(
        conn, "a-1", "match", "workout:h-2", planned_session=f"planned_session:{monday(0)}/lower"
    )

    assert matched_on_monday(the_week(conn))["lower"] == ("h-1", "h-2")


def test_a_swings_workout_logged_in_lifting_mode_beside_the_split_is_still_an_activity() -> None:
    conn = a_split_monday()
    a_logged_workout(
        conn, "h-3", monday(0), (SWING_TEMPLATE, ((24.0, 12, 8.0),) * 12), started="18:00"
    )

    rows = facts(opened(conn), "activities")["rows"]

    assert matched_on_monday(the_week(conn))["cond-swings"] == ("h-3",)
    assert [(r["id"], r["kind"]) for r in rows] == [("h-3", "conditioning")]


def test_a_workout_sharing_nothing_with_the_open_sessions_on_its_date_is_unmatched() -> None:
    conn = a_split_monday()
    with conn:
        exercises.update(conn, "pull_up", {"hevy_template_id": PULL_UP_TEMPLATE})
    a_logged_workout(
        conn, "h-3", monday(0), (PULL_UP_TEMPLATE, ((None, 8, 8.0),) * 3), started="18:00"
    )

    week = the_week(conn)

    assert "h-3" not in {w for s in week.sessions for w in s.workout_ids}


def test_a_workout_logging_only_the_swapped_out_exercise_does_not_join_the_session() -> None:
    week = the_week(a_split_monday(bench="db_bench_press"))

    assert matched_on_monday(week)["lower"] == ("h-1",)


def test_a_workout_logging_the_swapped_to_exercise_joins_the_session() -> None:
    conn = a_split_monday(bench="db_bench_press", second=(DB_BENCH_TEMPLATE, ((20.0, 8, 8.0),) * 3))

    assert matched_on_monday(the_week(conn))["lower"] == ("h-1", "h-2")
