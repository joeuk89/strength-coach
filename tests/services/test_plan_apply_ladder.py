import datetime

from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.ladders import CORE_LADDER, a_ladder_program, ladder_rung_decision
from support.plan_drafts import a_plan_draft
from support.plans import SQUAT_LINE, a_squat_program, squat_logged
from support.program_drafts import a_draft, a_ladder_line, a_line, a_rung, a_session, toml
from support.programs import a_config

from coach.cli.verbs.plan_apply import dry_run_result
from coach.core.mirror import RoutineExercise
from coach.services.plan_apply import ApplyResult, DryRun, apply, dry_run
from coach.services.program import adopt
from coach.services.record import record
from coach.store.connection import Connection

AB_WHEEL = "99D5F10E"
HANGING_LEG_RAISE = "F8356514"
DEAD_BUG = "D8911FC4"


def a_ladder_week(rung: int) -> Connection:
    conn = a_ladder_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
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


def pushed(conn: Connection, hevy: FakeHevy) -> ApplyResult:
    return pushed_draft(conn, hevy, a_plan_draft(conn, hevy=True))


def pushed_draft(conn: Connection, hevy: FakeHevy, data: bytes) -> ApplyResult:
    return apply(
        conn,
        hevy,
        data,
        file="plan.toml",
        expect=the_dry_run(conn, data).write_plan_hash,
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


def the_ladder_exercise(hevy: FakeHevy, template: str) -> RoutineExercise:
    [routine] = hevy.routines()
    return next(e for e in routine.exercises if e.hevy_template_id == template)


def test_the_dry_run_shows_the_standing_rungs_exercise_only() -> None:
    conn = a_ladder_week(2)

    dry = the_dry_run(conn, a_plan_draft(conn, hevy=True))

    [lower] = dry.summary.sessions
    assert [line.exercise_id for line in lower.lines] == ["bb_back_squat", "ab_wheel"]
    prompt = str(dry_run_result(dry, units="lb", full=True)["prompt"])
    assert "ab_wheel" in prompt
    assert "dead_bug" not in prompt and "hanging_leg_raise" not in prompt


def test_the_routine_carries_the_standing_rung_with_its_cues_and_names_the_next_rung() -> None:
    conn = a_ladder_week(2)
    hevy = FakeHevy(FixedClock())

    result = pushed(conn, hevy)

    exercise = the_ladder_exercise(hevy, AB_WHEEL)
    assert str(exercise.notes).splitlines()[1:] == [
        "Cues: ab_wheel cues",
        "Next: Hanging Leg Raise",
    ]
    assert exercise.rest_s == 60
    assert [(o.session_id, o.outcome) for o in result.routines] == [("lower", "verified")]


def test_on_the_last_rung_the_note_names_no_next_rung() -> None:
    conn = a_ladder_week(3)
    hevy = FakeHevy(FixedClock())

    result = pushed(conn, hevy)

    notes = str(the_ladder_exercise(hevy, HANGING_LEG_RAISE).notes).splitlines()
    assert notes[1:] == ["Cues: hanging_leg_raise cues"]
    assert [(o.session_id, o.outcome) for o in result.routines] == [("lower", "verified")]


def prompt_lines(dry: DryRun) -> list[str]:
    return str(dry_run_result(dry, units="lb", full=True)["prompt"]).splitlines()


def prompts_around_the_push(
    conn: Connection, hevy: FakeHevy, data: bytes
) -> tuple[list[str], list[str]]:
    """The fresh prompt, then the resumed one after the real push."""
    fresh = prompt_lines(the_dry_run(conn, data))
    pushed_draft(conn, hevy, data)
    return fresh, prompt_lines(the_dry_run(conn, data))


SQUAT_PROMPT_LINE = "  bb_back_squat 4×6–8 at 125 lb · 4×6–8 @8: 120 → 125"


def test_the_prompt_names_the_next_rung_on_a_line_below_the_top() -> None:
    conn = a_ladder_week(2)

    lines = prompt_lines(the_dry_run(conn, a_plan_draft(conn, hevy=True)))

    assert "  ab_wheel 3×8 · first prescription · Next: Hanging Leg Raise" in lines
    assert SQUAT_PROMPT_LINE in lines


def test_on_the_last_rung_the_prompt_shows_nothing_extra() -> None:
    conn = a_ladder_week(3)

    lines = prompt_lines(the_dry_run(conn, a_plan_draft(conn, hevy=True)))

    assert "  hanging_leg_raise 3×6 · first prescription" in lines
    assert SQUAT_PROMPT_LINE in lines


def test_a_resumed_prompt_names_the_next_rung_below_the_top() -> None:
    conn = a_ladder_week(2)
    data = a_plan_draft(conn, hevy=True)
    pushed_draft(conn, FakeHevy(FixedClock()), data)

    resumed = the_dry_run(conn, data)

    assert resumed.resumes == "wp-2026-11-02"
    lines = prompt_lines(resumed)
    assert "  ab_wheel 3×8 · first prescription · Next: Hanging Leg Raise" in lines
    assert SQUAT_PROMPT_LINE in lines


def test_a_resumed_prompt_on_the_last_rung_shows_nothing_extra() -> None:
    conn = a_ladder_week(3)
    data = a_plan_draft(conn, hevy=True)
    pushed_draft(conn, FakeHevy(FixedClock()), data)

    resumed = the_dry_run(conn, data)

    assert resumed.resumes == "wp-2026-11-02"
    lines = prompt_lines(resumed)
    assert "  hanging_leg_raise 3×6 · first prescription" in lines
    assert SQUAT_PROMPT_LINE in lines


def test_a_rung_exercise_on_a_plain_line_of_another_session_names_no_next_rung() -> None:
    conn = a_squat_program(
        a_session("lower", SQUAT_LINE, CORE_LADDER),
        a_session(
            "upper",
            a_line("ab_wheel", sets=[{"count": 3, "reps": 8, "rpe": 8}], start_load=None),
        ),
    )
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    record(conn, ladder_rung_decision(2).encode(), file="d.toml", clock=FixedClock())
    data = a_plan_draft(conn, hevy=True)

    for lines in prompts_around_the_push(conn, FakeHevy(FixedClock()), data):
        lower, upper = [n for n, line in enumerate(lines) if line.startswith("  ab_wheel")]
        assert lines[lower] == "  ab_wheel 3×8 · first prescription · Next: Hanging Leg Raise"
        assert lines[upper] == "  ab_wheel 3×8 · first prescription"


def the_note_next(hevy: FakeHevy, template: str) -> list[str]:
    notes = str(the_ladder_exercise(hevy, template).notes).splitlines()
    return [note for note in notes if note.startswith("Next: ")]


def the_prompt_next(lines: list[str], exercise: str) -> list[str]:
    [line] = [line for line in lines if line.startswith(f"  {exercise} ")]
    return [part for part in line.split(" · ") if part.startswith("Next: ")]


def test_the_prompt_names_the_rung_the_real_push_writes_on_the_note() -> None:
    conn = a_ladder_week(2)
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)

    fresh, resumed = prompts_around_the_push(conn, hevy, data)

    assert the_note_next(hevy, AB_WHEEL) == ["Next: Hanging Leg Raise"]
    assert the_prompt_next(fresh, "ab_wheel") == the_note_next(hevy, AB_WHEEL)
    assert the_prompt_next(resumed, "ab_wheel") == the_note_next(hevy, AB_WHEEL)


SWAP_THE_STANDING_RUNG_TO_DEAD_BUG = (
    '[[override]]\nkind = "swap_exercise"\nsession = "lower"\nexercise = "dead_bug"\n'
    'to = "dead_bug"\nbecause = "kit"\ntext = "No wheel this week."\n'
)


def test_a_rung_swapped_by_an_override_shows_the_notes_next_rung_in_the_prompt() -> None:
    conn = a_ladder_week(2)
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True, overrides=SWAP_THE_STANDING_RUNG_TO_DEAD_BUG)

    fresh, resumed = prompts_around_the_push(conn, hevy, data)

    assert the_note_next(hevy, DEAD_BUG) == ["Next: Hanging Leg Raise"]
    assert the_prompt_next(fresh, "dead_bug") == ["Next: Hanging Leg Raise"]
    assert the_prompt_next(resumed, "dead_bug") == ["Next: Hanging Leg Raise"]


def test_the_last_rung_swapped_by_an_override_names_no_next_rung_anywhere() -> None:
    conn = a_ladder_week(3)
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True, overrides=SWAP_THE_STANDING_RUNG_TO_DEAD_BUG)

    fresh, resumed = prompts_around_the_push(conn, hevy, data)

    assert the_note_next(hevy, DEAD_BUG) == []
    assert the_prompt_next(fresh, "dead_bug") == []
    assert the_prompt_next(resumed, "dead_bug") == []


def test_a_program_adopted_after_approval_leaves_the_resumed_prompts_rung_alone() -> None:
    conn = a_ladder_week(2)
    data = a_plan_draft(conn, hevy=True)
    pushed_draft(conn, FakeHevy(FixedClock()), data)
    another_ladder = a_ladder_line(
        "dead_bug",
        a_rung(sets=[{"count": 3, "reps": 10, "rpe": 8}]),
        a_rung("ab_wheel", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
        a_rung("plank", sets=[{"count": 3, "duration_s": 30, "rpe": 8}]),
    )
    adopt(
        conn,
        toml(a_draft(a_session("lower", SQUAT_LINE, another_ladder))),
        file="next.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(datetime.datetime(2026, 10, 31, 12, tzinfo=datetime.UTC)),
    )

    resumed = the_dry_run(conn, data)

    assert resumed.resumes == "wp-2026-11-02"
    assert "  ab_wheel 3×8 · first prescription · Next: Hanging Leg Raise" in prompt_lines(resumed)


def test_a_ladder_on_one_exercise_pushes_the_standing_rungs_sets_and_verifies() -> None:
    climbing = a_ladder_line(
        "dead_bug",
        a_rung(sets=[{"count": 3, "reps": 10, "rpe": 8}]),
        a_rung("dead_bug", sets=[{"count": 3, "reps": 12, "rpe": 8}]),
    )
    conn = a_ladder_program(climbing)
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    record(conn, ladder_rung_decision(2).encode(), file="d.toml", clock=FixedClock())
    hevy = FakeHevy(FixedClock())

    result = pushed(conn, hevy)

    exercise = the_ladder_exercise(hevy, DEAD_BUG)
    assert [s.reps for s in exercise.sets] == [12, 12, 12]
    assert [(o.session_id, o.outcome) for o in result.routines] == [("lower", "verified")]
