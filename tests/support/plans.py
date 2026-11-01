"""Scenario builders for plan draft: an adopted version, squat history and approved plans.
Each writes only through `store` functions or the services that own the record."""

import json

from coach.core.units import KG_PER_LB
from coach.services.program import adopt
from coach.store import exercises, notes, rows
from coach.store.connection import Connection
from support.clock import FixedClock
from support.history import a_logged_workout
from support.kit_fixtures import kit_files
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config, the_worked_store

SQUAT_TEMPLATE = "SQ-0001"
SQUAT_LINE = a_line(
    "bb_back_squat",
    sets=[
        {"count": 1, "type": "warm_up", "reps": 5},
        {"count": 1, "type": "warm_up", "reps": 3},
        {"count": 4, "reps": [6, 8], "rpe": 8},
    ],
    start_load=100,
)


def a_squat_program(*sessions: dict[str, object], **draft: object) -> Connection:
    """The worked store with a one-week version adopted on 30 Oct 2026: `lower` on Monday."""
    conn = the_worked_store()
    with conn:
        exercises.update(conn, "bb_back_squat", {"hevy_template_id": SQUAT_TEMPLATE})
    sessions = sessions or (a_session("lower", SQUAT_LINE),)
    adopt(
        conn,
        toml(a_draft(*sessions, **draft)),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )
    return conn


def squat_logged(
    conn: Connection, id_: str, on: str, *sets: tuple[float, int, float | None]
) -> None:
    """Sets of (lb, reps, rpe) logged in Hevy, which stores kilograms."""
    kg = tuple((lb * KG_PER_LB, reps, rpe) for lb, reps, rpe in sets)
    a_logged_workout(conn, id_, on, (SQUAT_TEMPLATE, kg))


def an_approved_plan(
    conn: Connection, week: str, position: str = "A", *, approved_at: str | None = None
) -> str:
    plan_id = f"wp-{week}"
    with conn:
        rows.insert(
            conn,
            "week_plan",
            {
                "id": plan_id,
                "week": week,
                "position": position,
                "status": "approved",
                "approved_at": approved_at or f"{week}T08:00:00+00:00",
                "write_plan_hash": "sha256:w",
                "draft_hash": "sha256:d",
                "recorded_at": approved_at or f"{week}T08:00:00+00:00",
            },
        )
    return plan_id


def a_note(
    conn: Connection, id_: str, on: str, text: str, *, about: str | None = None, at: str
) -> None:
    with conn:
        notes.insert(
            conn,
            {
                "id": id_,
                "date": on,
                "text": text,
                "about": about,
                "check_in": None,
                "draft_hash": "h",
                "recorded_at": at,
            },
        )


def a_plan_override(
    conn: Connection,
    plan_id: str,
    kind: str,
    session: str,
    exercise: str,
    **params: object,
) -> None:
    """An override row on an approved WeekPlan, as `plan apply` freezes it."""
    with conn:
        count = conn.execute("SELECT COUNT(*) FROM override").fetchone()[0]
        rows.insert(
            conn,
            "override",
            {
                "id": f"o-{count + 1:04d}",
                "plan_id": plan_id,
                "kind": kind,
                "session_id": session,
                "exercise_id": exercise,
                "date": None,
                "params": json.dumps(params),
                "because": "pain",
                "text": "Knee niggle.",
                "evidence": None,
            },
        )
