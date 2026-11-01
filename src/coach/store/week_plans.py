"""WeekPlans as rows, read only: `plan apply` writes them (schema.md, "Week")."""

from coach.store.connection import Connection
from coach.store.rows import Row, select

READ = "SELECT id, week, position, approved_at, write_plan_hash FROM week_plan"


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
