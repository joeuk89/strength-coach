from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.ladders import a_ladder_program, ladder_rung_decision
from support.plan_drafts import a_plan_draft
from support.plans import squat_logged
from support.programs import a_config

from coach.cli.verbs.plan_apply import dry_run_result
from coach.core.mirror import RoutineExercise
from coach.services.plan_apply import ApplyResult, DryRun, apply, dry_run
from coach.services.record import record
from coach.store.connection import Connection

AB_WHEEL = "99D5F10E"
HANGING_LEG_RAISE = "F8356514"


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
    data = a_plan_draft(conn, hevy=True)
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
