"""Scenario builders for plan draft: an adopted version, squat history and approved plans.
Each writes only through `store` functions or the services that own the record."""

import json
from collections.abc import Mapping, Sequence

from coach.core.mirror import ENGINE_FOLDER_TITLES, FolderRole, MirroredFolder, MirroredRoutine
from coach.core.units import KG_PER_LB
from coach.services.program import adopt
from coach.store import exercises, mirrors, notes, rows, sessions
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
    session: str | None,
    exercise: str | None,
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


def an_acknowledgement(conn: Connection, plan_id: str, key: str, params_hash: str) -> None:
    """An acknowledgement frozen on an approved WeekPlan, as `plan apply` freezes it."""
    with conn:
        rows.insert(
            conn,
            "acknowledgement",
            {
                "id": f"ack-{plan_id}-{key}",
                "plan_id": plan_id,
                "version_id": None,
                "key": key,
                "params_hash": params_hash,
                "because": "kit",
                "text": "Left on the plan in force.",
                "evidence": None,
            },
        )


def a_mapped_routine(
    conn: Connection, session: str, routine: str, *, updated_at: str, mapped: bool = True
) -> None:
    """A routine in the mirror as import stores it and, with `mapped`, its Routine map row."""
    with conn:
        mirrors.upsert_routine(
            conn, MirroredRoutine(routine, updated_at, session, None, "{}"), updated_at
        )
        if not sessions.exists(conn, session):
            sessions.insert(conn, session, "pv-1")
        if mapped:
            rows.insert(
                conn,
                "routine_map",
                {
                    "session_id": session,
                    "routine_id": routine,
                    "status": "active",
                    "last_verified": updated_at,
                    "plan_id": None,
                    "written_at": updated_at,
                },
            )


def a_folder(conn: Connection, role: FolderRole, hevy_id: str) -> None:
    with conn:
        mirrors.upsert_folder(conn, MirroredFolder(role, hevy_id, ENGINE_FOLDER_TITLES[role]))


def a_frozen_prescription(
    conn: Connection,
    plan_id: str,
    session: str,
    on: str,
    exercise: str,
    *,
    set_groups: Sequence[Mapping[str, object]],
    change: str,
    flags: Sequence[Mapping[str, object]] = (),
    derived_from: str = "start_load",
    steps: Sequence[Mapping[str, object]] = (),
) -> None:
    """A prescription row as `plan apply` freezes it on an approved WeekPlan."""
    with conn:
        if not sessions.exists(conn, session):
            sessions.insert(conn, session, "pv-1")
        rows.insert(
            conn,
            "prescription",
            {
                "plan_id": plan_id,
                "session_id": session,
                "date": on,
                "exercise_id": exercise,
                "position": _next_position(conn, plan_id),
                "set_groups": json.dumps(list(set_groups)),
                "derived_from": derived_from,
                "steps": json.dumps(list(steps)),
                "flags": json.dumps(list(flags)),
                "change": change,
            },
        )


def _next_position(conn: Connection, plan_id: str) -> int:
    (count,) = conn.execute(
        "SELECT count(*) FROM prescription WHERE plan_id = ?", (plan_id,)
    ).fetchone()
    return count + 1
