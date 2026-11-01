"""WeekPlans as rows: `plan apply` writes them born approved (schema.md, "Week")."""

import json
from collections.abc import Mapping, Sequence

from coach.store.connection import Connection
from coach.store.ids import next_ids
from coach.store.rows import Row, insert, select

READ = "SELECT id, week, position, approved_at, write_plan_hash, draft_hash FROM week_plan"


def in_force(conn: Connection, week: str) -> Row | None:
    """The approved WeekPlan of the week that starts on Monday `week`."""
    found = select(conn, f"{READ} WHERE week = ? AND status = 'approved'", (week,))
    return found[0] if found else None


def approved_weeks(conn: Connection) -> frozenset[str]:
    found = conn.execute("SELECT week FROM week_plan WHERE status = 'approved'")
    return frozenset(week for (week,) in found)


def last_before(conn: Connection, week: str, *, since: str | None) -> Row | None:
    """The approved WeekPlan of the latest week before `week`, from the week of `since` on."""
    found = select(
        conn,
        f"{READ} WHERE status = 'approved' AND week < ? AND week >= ? ORDER BY week DESC LIMIT 1",
        (week, since or ""),
    )
    return found[0] if found else None


def last_approved(conn: Connection) -> Row | None:
    """The WeekPlan approved most recently, whatever its status now."""
    found = select(conn, f"{READ} ORDER BY approved_at DESC LIMIT 1")
    return found[0] if found else None


def overrides(conn: Connection, plan_id: str) -> list[Row]:
    """The plan's override rows, params and evidence decoded, in the order they were written."""
    found = select(conn, "SELECT * FROM override WHERE plan_id = ? ORDER BY id", (plan_id,))
    for row in found:
        row["params"] = json.loads(str(row["params"]))
        row["evidence"] = json.loads(str(row["evidence"])) if row["evidence"] else []
    return found


def prescriptions(conn: Connection, plan_id: str) -> list[Row]:
    """The plan's frozen prescription rows, set groups, steps and flags decoded, in date order."""
    found = select(
        conn,
        "SELECT * FROM prescription WHERE plan_id = ? ORDER BY date, session_id, exercise_id",
        (plan_id,),
    )
    for row in found:
        row["set_groups"] = json.loads(str(row["set_groups"]))
        row["steps"] = json.loads(str(row["steps"]))
        row["flags"] = json.loads(str(row["flags"]))
    return found


def next_id(conn: Connection, week: str) -> str:
    """`wp-<monday>`, and `-2`, `-3` for each plan that supersedes it in the same week."""
    (count,) = conn.execute("SELECT count(*) FROM week_plan WHERE week = ?", (week,)).fetchone()
    return f"wp-{week}" if count == 0 else f"wp-{week}-{count + 1}"


def with_draft(conn: Connection, week: str, draft_hash: str) -> Row | None:
    """The approved WeekPlan of the week written from this exact Draft: a re-run resumes it."""
    found = select(
        conn,
        f"{READ} WHERE week = ? AND status = 'approved' AND draft_hash = ?",
        (week, draft_hash),
    )
    return found[0] if found else None


def approved_before(conn: Connection, week: str) -> list[Row]:
    """The approved WeekPlans of the weeks before `week`, newest week first."""
    return select(
        conn, f"{READ} WHERE status = 'approved' AND week < ? ORDER BY week DESC", (week,)
    )


def approve(
    conn: Connection,
    plan: Mapping[str, object],
    *,
    supersedes: str | None,
    overrides: Sequence[Mapping[str, object]],
    prescriptions: Sequence[Mapping[str, object]],
    acknowledgements: Sequence[Mapping[str, object]],
) -> None:
    """Write the WeekPlan born approved with its frozen rows. A superseded plan is flipped first
    so the one-approved-plan-per-week index admits the new row, then pointed at it."""
    if supersedes is not None:
        conn.execute("UPDATE week_plan SET status = 'superseded' WHERE id = ?", (supersedes,))
    insert(conn, "week_plan", {**plan, "status": "approved"})
    if supersedes is not None:
        conn.execute(
            "UPDATE week_plan SET superseded_by = ? WHERE id = ?", (plan["id"], supersedes)
        )
    plan_id = plan["id"]
    for id_, row in zip(next_ids(conn, "override", "ov-", len(overrides)), overrides, strict=True):
        insert(conn, "override", {"id": id_, "plan_id": plan_id, **row})
    for row in prescriptions:
        insert(conn, "prescription", {"plan_id": plan_id, **row})
    ids = next_ids(conn, "acknowledgement", "ak-", len(acknowledgements))
    for id_, row in zip(ids, acknowledgements, strict=True):
        insert(conn, "acknowledgement", {"id": id_, "plan_id": plan_id, **row})


def by_id(conn: Connection, plan_id: str) -> Row:
    return select(conn, f"{READ} WHERE id = ?", (plan_id,))[0]


def every_of_week(conn: Connection, week: str) -> list[Row]:
    """Every WeekPlan of the week, superseded ones included, oldest first."""
    return select(
        conn,
        "SELECT id, status, superseded_by, approved_at FROM week_plan WHERE week = ? "
        "ORDER BY recorded_at, id",
        (week,),
    )


def acknowledgements(conn: Connection, plan_id: str) -> list[tuple[str, str, str]]:
    """The plan's frozen acknowledgements as (key, params hash, because)."""
    return conn.execute(
        "SELECT key, params_hash, because FROM acknowledgement WHERE plan_id = ? ORDER BY id",
        (plan_id,),
    ).fetchall()
