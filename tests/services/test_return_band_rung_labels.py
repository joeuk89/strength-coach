from typing import cast

import pytest
from support.check_in_cards import field_of, opened
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.ladders import a_ladder_program, ladder_rung_decision, logged
from support.pages import the_pages
from support.plan_drafts import a_plan_draft
from support.plans import squat_logged
from support.program_drafts import a_ladder_line, a_rung
from support.programs import a_config

from coach.cli.verbs.plan_apply import dry_run_result
from coach.core.mirror import RoutineExercise
from coach.core.routine_projection import routine_diff
from coach.services.plan_apply import DryRun, apply, dry_run
from coach.services.projections import projection, session_facts
from coach.services.record import record
from coach.store import week_plans
from coach.store.connection import Connection

DEAD_BUG = "D8911FC4"
RUNG_ONE = "rung 1 · 3×8 @8 · lower for 4 s"
RUNG_TWO = "rung 2 · 3×8 @8 · lower for 6 s"
RUNG_THREE = "rung 3 · 3×8 @8 · lower for 8 s"
FIFTY_TWO_DAYS_OFF = "2026-09-04"
EIGHTEEN_DAYS_OFF = "2026-10-08"
TRAINED_LAST_WEEK = "2026-10-26"
TEMPO_LADDER = a_ladder_line(
    "dead_bug",
    a_rung(cues="lower for 4 s", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
    a_rung("dead_bug", cues="lower for 6 s", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
    a_rung("dead_bug", cues="lower for 8 s", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
    a_rung("dead_bug", cues="lower for 10 s", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
)


def standing_after_a_layoff(rung: int, last_trained: str) -> Connection:
    conn = a_ladder_program(TEMPO_LADDER)
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    logged(conn, "dead_bug", last_trained, 8)
    record(conn, ladder_rung_decision(rung).encode(), file="d.toml", clock=FixedClock())
    return conn


def the_dry_run(conn: Connection, data: bytes) -> DryRun:
    return dry_run(
        conn,
        data,
        file="plan.toml",
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


def the_prompt_line(conn: Connection, data: bytes) -> str:
    prompt = str(dry_run_result(the_dry_run(conn, data), units="lb", full=True)["prompt"])
    [line] = [line for line in prompt.splitlines() if line.startswith("  dead_bug ")]
    return line


def pushed(conn: Connection, hevy: FakeHevy, data: bytes) -> None:
    apply(
        conn,
        hevy,
        data,
        file="plan.toml",
        expect=the_dry_run(conn, data).write_plan_hash,
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


def the_dead_bug_on(hevy: FakeHevy) -> RoutineExercise:
    [routine] = hevy.routines()
    return next(e for e in routine.exercises if e.hevy_template_id == DEAD_BUG)


def prompt_lines_around_the_push(conn: Connection, hevy: FakeHevy, data: bytes) -> list[str]:
    fresh = the_prompt_line(conn, data)
    pushed(conn, hevy, data)
    return [fresh, the_prompt_line(conn, data)]


def test_a_52_day_layoff_on_a_shared_exercise_shows_the_weeks_rung_and_no_next_rung() -> None:
    conn = standing_after_a_layoff(3, FIFTY_TWO_DAYS_OFF)
    hevy = FakeHevy(FixedClock())

    prompts = prompt_lines_around_the_push(conn, hevy, a_plan_draft(conn, hevy=True))

    expected = "  dead_bug 2×8 · 3×8 @8 → 2×8 @≤7 · rung 1"
    assert prompts == [expected, expected]
    assert str(the_dead_bug_on(hevy).notes).splitlines() == [
        "Target: 2×8 @7, choose the load",
        "Cues: lower for 4 s",
        "This week: rung 1",
    ]


def test_a_one_rung_step_back_shows_the_rung_below_and_no_next_rung() -> None:
    conn = standing_after_a_layoff(3, EIGHTEEN_DAYS_OFF)
    hevy = FakeHevy(FixedClock())

    prompts = prompt_lines_around_the_push(conn, hevy, a_plan_draft(conn, hevy=True))

    expected = "  dead_bug 2×8 · 3×8 @8 → 2×8 @≤8 · rung 2"
    assert prompts == [expected, expected]
    assert str(the_dead_bug_on(hevy).notes).splitlines() == [
        "Target: 2×8 @8, choose the load",
        "Cues: lower for 6 s",
        "This week: rung 2",
    ]


def test_the_draft_step_names_both_rungs_with_its_cause() -> None:
    conn = standing_after_a_layoff(3, FIFTY_TWO_DAYS_OFF)

    draft = a_plan_draft(conn, hevy=True).decode()

    assert (
        'step = "cut"\nfrom = "rung 3"\nto = "rung 1"\ncause = "return 43+, 52 days off"\n'
    ) in draft


def test_the_week_page_step_table_names_both_rungs_with_its_cause() -> None:
    conn = standing_after_a_layoff(3, EIGHTEEN_DAYS_OFF)
    pushed(conn, FakeHevy(FixedClock()), a_plan_draft(conn, hevy=True))

    week_page = the_pages(conn)["pages/week.md"]
    assert "| cut | rung 3 | rung 2 | return 11–21, 18 days off |" in week_page


def test_a_week_with_no_step_back_keeps_its_next_rung_and_note() -> None:
    conn = standing_after_a_layoff(2, TRAINED_LAST_WEEK)
    hevy = FakeHevy(FixedClock())

    prompts = prompt_lines_around_the_push(conn, hevy, a_plan_draft(conn, hevy=True))

    expected = f"  dead_bug 3×8 · held · {RUNG_TWO} · Next: {RUNG_THREE}"
    assert prompts == [expected, expected]
    assert str(the_dead_bug_on(hevy).notes).splitlines() == [
        "Target: 3×8 @8, choose the load",
        "Cues: lower for 6 s",
        f"Next: {RUNG_THREE}",
    ]


def test_a_return_band_on_the_first_rung_steps_back_nothing_and_keeps_its_next_rung() -> None:
    conn = standing_after_a_layoff(1, FIFTY_TWO_DAYS_OFF)
    hevy = FakeHevy(FixedClock())

    prompts = prompt_lines_around_the_push(conn, hevy, a_plan_draft(conn, hevy=True))

    expected = f"  dead_bug 2×8 · 3×8 @8 → 2×8 @≤7 · {RUNG_ONE} · Next: {RUNG_TWO}"
    assert prompts == [expected, expected]
    assert f"Next: {RUNG_TWO}" in str(the_dead_bug_on(hevy).notes).splitlines()


@pytest.mark.parametrize(
    ("standing", "last_trained", "decided"),
    [(3, FIFTY_TWO_DAYS_OFF, 1), (3, FIFTY_TWO_DAYS_OFF, 4), (2, TRAINED_LAST_WEEK, 3)],
)
def test_a_decision_recorded_after_approval_leaves_the_note_alone(
    standing: int, last_trained: str, decided: int
) -> None:
    conn = standing_after_a_layoff(standing, last_trained)
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    pushed(conn, hevy, data)
    [routine] = hevy.routines()
    before = the_prompt_line(conn, data)

    record(conn, ladder_rung_decision(decided).encode(), file="d2.toml", clock=FixedClock())

    plan = week_plans.by_id(conn, "wp-2026-11-02")
    facts = session_facts(conn, plan)["lower"]
    assert routine_diff(projection(conn, plan, "lower", facts, "lb"), routine) == ()
    assert the_prompt_line(conn, data) == before


def test_the_card_still_measures_from_the_standing_rung_in_a_stepped_back_week() -> None:
    conn = standing_after_a_layoff(3, FIFTY_TWO_DAYS_OFF)
    pushed(conn, FakeHevy(FixedClock()), a_plan_draft(conn, hevy=True))

    [row] = cast(list[dict[str, object]], field_of(opened(conn), "ladders").facts["rows"])

    assert row["rung"] == 3
    assert row["next_label"] == "rung 4 · 3×8 @8 · lower for 10 s"
