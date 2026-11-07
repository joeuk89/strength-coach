"""Scenario builders for an `exercise_ladder` line: a three-rung core ladder in `lower` beside the
back squat, and its rung exercises logged in Hevy."""

from coach.store.connection import Connection
from support.history import a_logged_workout
from support.plans import SQUAT_LINE, a_squat_program
from support.program_drafts import a_ladder_line, a_rung, a_session

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


def ladder_rung_decision(rung: int, *, line: str = "dead_bug") -> str:
    return (
        f'[[decision]]\nkind = "ladder_rung"\nsession = "lower"\nexercise = "{line}"\n'
        f'rung = {rung}\nbecause = "progress"\ntext = "Rung met; the athlete said yes."\n'
    )
