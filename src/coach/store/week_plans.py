import datetime

from coach.store.connection import Connection


def light_weeks(conn: Connection) -> tuple[tuple[datetime.date, datetime.date], ...]:
    """(Monday, Sunday) of each plan in force carrying a `light_week` override."""
    found = conn.execute(
        "SELECT p.week, p.week_end FROM plan_in_force p WHERE EXISTS "
        "(SELECT 1 FROM override o WHERE o.plan_id = p.id AND o.kind = 'light_week') "
        "ORDER BY p.week"
    ).fetchall()
    return tuple(
        (datetime.date.fromisoformat(start), datetime.date.fromisoformat(end))
        for start, end in found
    )
