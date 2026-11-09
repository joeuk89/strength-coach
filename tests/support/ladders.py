"""Scenario builders for an `exercise_ladder` line: a three-rung core ladder in `lower` beside the
back squat, and its rung exercises logged in Hevy."""

from coach.core.flag import Flag, FlagKey
from coach.services.plan_apply import dry_run
from coach.services.record import record
from coach.store.connection import Connection
from support.clock import FixedClock
from support.history import a_logged_workout
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import SQUAT_LINE, a_squat_program, squat_logged
from support.program_drafts import a_ladder_line, a_rung, a_session
from support.programs import a_config

TEMPLATES = {"dead_bug": "D8911FC4", "ab_wheel": "99D5F10E", "hanging_leg_raise": "F8356514"}
CORE_LADDER = a_ladder_line(
    "dead_bug",
    a_rung(sets=[{"count": 3, "reps": 10, "rpe": 8}]),
    a_rung("ab_wheel", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
    a_rung("hanging_leg_raise", sets=[{"count": 3, "reps": 6, "rpe": 8}]),
)


def a_ladder_program(ladder: dict[str, object] = CORE_LADDER) -> Connection:
    """Adopted on 30 Oct 2026, the opening rung's start."""
    return a_squat_program(a_session("lower", SQUAT_LINE, ladder))


def logged(conn: Connection, exercise: str, on: str, reps: int) -> None:
    """Three sets of `reps` at RPE 8."""
    a_logged_workout(conn, f"h-{exercise}-{on}", on, (TEMPLATES[exercise], ((None, reps, 8),) * 3))


def ladder_rung_decision(rung: int, *, line: str = "dead_bug", session: str = "lower") -> str:
    return (
        f'[[decision]]\nkind = "ladder_rung"\nsession = "{session}"\nexercise = "{line}"\n'
        f'rung = {rung}\nbecause = "progress"\ntext = "Rung met; the athlete said yes."\n'
    )


def a_met_rung() -> Connection:
    """`dead_bug` met before the first planned week, so the plan raises what the card reads."""
    conn = a_ladder_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    logged(conn, "dead_bug", "2026-10-30", 10)
    logged(conn, "dead_bug", "2026-10-31", 10)
    return conn


def the_prompts_flag(conn: Connection, code: str = "rung_met") -> Flag:
    checked = dry_run(
        conn,
        a_plan_draft(conn),
        file="plan.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    ).checked
    assert checked is not None
    [flag] = [f for f in checked.flags if f.code == code]
    return flag


def leave_warning(conn: Connection, flag: Flag, *, until: str = "2026-12-31") -> None:
    key = str(FlagKey.parse(flag.key).calendar_free())
    record(
        conn,
        (
            f'[[decision]]\nkind = "leave_warning"\nflag = "{key}"\n'
            f'params_hash = "{flag.params_hash}"\nuntil = {until}\n'
            'because = "coach_judgement"\ntext = "Hold the rung through the holiday."\n'
        ).encode(),
        file="d.toml",
        clock=FixedClock(),
    )
