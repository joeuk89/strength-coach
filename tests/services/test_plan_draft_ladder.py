import datetime

from support.clock import FixedClock
from support.history import a_logged_workout
from support.kit_fixtures import kit_files
from support.plans import SQUAT_LINE, a_squat_program
from support.program_drafts import a_ladder_line, a_rung, a_session
from support.programs import a_config

from coach.core.prescription import LinePrescription
from coach.services.plan_draft import plan_draft
from coach.services.record import record
from coach.store.connection import Connection

NEXT_MONDAY = datetime.date(2026, 11, 2)
TEMPLATES = {"dead_bug": "D8911FC4", "ab_wheel": "99D5F10E"}
CORE_LADDER = a_ladder_line(
    "dead_bug",
    a_rung(sets=[{"count": 3, "reps": 10, "rpe": 8}]),
    a_rung("ab_wheel", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
    a_rung("hanging_leg_raise", sets=[{"count": 3, "reps": 6, "rpe": 8}]),
)


def a_ladder_program() -> Connection:
    """Adopted on 30 Oct 2026, the opening rung's start."""
    return a_squat_program(a_session("lower", SQUAT_LINE, CORE_LADDER))


def ladder_rung(conn: Connection, rung: int) -> None:
    """Recorded at noon on 30 Oct 2026, the rung's start."""
    record(
        conn,
        (
            '[[decision]]\nkind = "ladder_rung"\nsession = "lower"\nexercise = "dead_bug"\n'
            f'rung = {rung}\nbecause = "progress"\ntext = "Clean sets; the athlete said yes."\n'
        ).encode(),
        file="d.toml",
        clock=FixedClock(),
    )


def logged(conn: Connection, exercise: str, on: str, reps: int) -> None:
    a_logged_workout(conn, f"h-{exercise}-{on}", on, (TEMPLATES[exercise], ((None, reps, 8),) * 3))


def ladder_line(conn: Connection) -> LinePrescription:
    draft = plan_draft(
        conn, config=a_config(), kits=(kit_files(),), clock=FixedClock(), week=NEXT_MONDAY
    ).draft
    [_, line] = draft.sessions[0].lines
    return line


def climb_codes(line: LinePrescription) -> list[str]:
    return [f.code for f in line.flags if f.code in ("rung_met", "ladder_top")]


def test_the_draft_prescribes_rung_1_with_no_decision_and_rung_3_once_one_names_it() -> None:
    conn = a_ladder_program()
    before = ladder_line(conn)

    ladder_rung(conn, 3)

    after = ladder_line(conn)
    assert (before.exercise_id, [(g.count, g.reps) for g in before.groups]) == (
        "dead_bug",
        [(3, 10)],
    )
    assert (after.exercise_id, [(g.count, g.reps) for g in after.groups]) == (
        "hanging_leg_raise",
        [(3, 6)],
    )


def test_the_opening_rungs_criterion_reads_exposures_from_the_versions_adoption() -> None:
    before_adoption = a_ladder_program()
    logged(before_adoption, "dead_bug", "2026-10-28", 10)
    logged(before_adoption, "dead_bug", "2026-10-31", 10)
    since_adoption = a_ladder_program()
    logged(since_adoption, "dead_bug", "2026-10-30", 10)
    logged(since_adoption, "dead_bug", "2026-10-31", 10)

    assert climb_codes(ladder_line(before_adoption)) == []
    assert climb_codes(ladder_line(since_adoption)) == ["rung_met"]


def test_a_recorded_rungs_criterion_counts_exposures_from_the_day_after_the_decision() -> None:
    before_decision = a_ladder_program()
    ladder_rung(before_decision, 2)
    logged(before_decision, "ab_wheel", "2026-10-29", 8)
    logged(before_decision, "ab_wheel", "2026-10-31", 8)
    on_decision = a_ladder_program()
    ladder_rung(on_decision, 2)
    logged(on_decision, "ab_wheel", "2026-10-30", 8)
    logged(on_decision, "ab_wheel", "2026-10-31", 8)
    after_decision = a_ladder_program()
    ladder_rung(after_decision, 2)
    logged(after_decision, "ab_wheel", "2026-10-31", 8)
    logged(after_decision, "ab_wheel", "2026-11-01", 8)

    assert climb_codes(ladder_line(before_decision)) == []
    assert climb_codes(ladder_line(on_decision)) == []
    assert climb_codes(ladder_line(after_decision)) == ["rung_met"]
