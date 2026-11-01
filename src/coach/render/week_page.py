"""The weekly sheet: the plan in force with its frozen prescriptions and their derivation steps."""

from coach.core.config import Units
from coach.core.pages import PageLine, PlannedSessionPage, WeekPage
from coach.render.markdown import bullets, flag_text, group_text, page, section, table

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def week_page(week: WeekPage | None, *, units: Units, pin: str) -> str:
    if week is None:
        return page("Week", "No WeekPlan is approved yet.")
    overrides = table(
        ["kind", "session", "exercise", "because", "text"],
        [
            [
                o.get("kind"),
                o.get("session_id"),
                o.get("exercise_id"),
                o.get("because"),
                o.get("text"),
            ]
            for o in week.overrides
        ],
    )
    return page(
        f"Week of {week.week}",
        f"Plan `{week.plan_id}`, rotation week {week.position}, approved {week.approved_at}.",
        *(_session(s, units, pin) for s in week.sessions),
        section("Overrides", overrides),
    )


def _session(session: PlannedSessionPage, units: Units, pin: str) -> str:
    day = DAY_NAMES[session.date.weekday()]
    heading = f"## {day} {session.date.isoformat()}: {session.title}"
    return "\n\n".join([heading, *(_line(line, units, pin) for line in session.lines)])


def _line(line: PageLine, units: Units, pin: str) -> str:
    parts = [
        f"### {line.name}",
        bullets([group_text(g, units) for g in line.set_groups]),
        f"Change: {line.change}. From `{line.derived_from}`.",
    ]
    steps = table(
        ["step", "from", "to", "cause"],
        [[s.get("step"), s.get("from"), s.get("to"), s.get("cause")] for s in line.steps],
    )
    if steps:
        parts.append(steps)
    if line.flags:
        parts.append(bullets([flag_text(f, pin) for f in line.flags]))
    return "\n\n".join(parts)
