"""The weekly sheet: the plan in force with its frozen prescriptions and their derivation steps."""

from collections.abc import Callable

from coach.core.config import Units
from coach.core.pages import PageLine, PageNames, PlannedSessionPage, WeekPage
from coach.core.registries.program import MUSCLES
from coach.core.registries.registry import title_of
from coach.render.markdown import bullets, flag_text, group_text, page, section, table

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def week_page(week: WeekPage | None, *, names: PageNames, units: Units, pin: str) -> str:
    if week is None:
        return page("Week", "No WeekPlan is approved yet.")
    overrides = table(
        ["kind", "session", "exercise", "because", "text"],
        [
            [
                o.get("kind"),
                _named(o.get("session_id"), names.session),
                _named(o.get("exercise_id"), names.exercise),
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


def _named(id_: object, name: Callable[[str], str]) -> object:
    return name(id_) if isinstance(id_, str) else id_


NOT_DERIVED = "Not in the current derivation: frozen rows kept as approved."


def _session(session: PlannedSessionPage, units: Units, pin: str) -> str:
    day = DAY_NAMES[session.date.weekday()]
    parts = [f"## {day} {session.date.isoformat()}: {session.title}"]
    if not session.derived:
        parts.append(NOT_DERIVED)
    if not session.lines:
        parts.append(_lineless(session))
    parts.extend(_line(line, units, pin) for line in session.lines)
    return "\n\n".join(parts)


def _lineless(session: PlannedSessionPage) -> str:
    kind = session.kind.replace("_", "-").capitalize()
    if not session.estimated_sets:
        return kind
    sets = ", ".join(
        f"{title_of(MUSCLES, muscle)} {count}" for muscle, count in session.estimated_sets.items()
    )
    return f"{kind} · estimated sets: {sets}"


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
