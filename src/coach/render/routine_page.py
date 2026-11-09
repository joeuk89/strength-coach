from collections.abc import Mapping

from coach.core.config import Units
from coach.core.exercise_ladder import RungShape
from coach.core.pages import PageLine, RoutinePage
from coach.render.markdown import (
    MANUAL_CLIMB,
    bullets,
    group_text,
    marked_rung,
    number,
    page,
    section,
)
from coach.render.plate_pool import line_link, set_up_link


def routine_page(routine: RoutinePage, *, units: Units) -> str:
    facts = [f"Session `{routine.session_id}`"]
    if routine.location is not None:
        facts.append(f"at {routine.location}")
    if routine.week is not None:
        facts.append(f"as written for the week of {routine.week}")
    set_up = set_up_link(routine.kit) if routine.kit else None
    kit = (
        f"[Set up the {routine.kit.location} kit in plate-pool]({set_up})"
        if routine.kit and set_up
        else ""
    )
    return page(
        routine.title,
        " ".join(facts) + ".",
        kit,
        *(_line(line, routine, units) for line in routine.lines),
    )


def _line(line: PageLine, routine: RoutinePage, units: Units) -> str:
    body = bullets([group_text(g, units) for g in line.set_groups])
    link = line_link(line, routine.kit, units) if routine.kit else None
    if link is not None:
        body += f"\n\n[Load it in plate-pool]({link})"
    if line.ladder:
        body += "\n\nLadder:\n\n" + bullets([_rung(rung) for rung in line.ladder])
    return section(line.name, body)


def _rung(rung: RungShape) -> str:
    return f"{marked_rung(rung.label, standing=rung.standing)}. Climb {_climb(rung.criterion)}."


def _climb(criterion: Mapping[str, object]) -> str:
    if criterion.get("manual"):
        return MANUAL_CLIMB
    reps, duration, rpe = (criterion.get(k) for k in ("reps", "duration_s", "rpe_at_most"))
    head = [f"{reps} reps"] if reps is not None else []
    if duration is not None:
        head.append(f"{duration} s")
    if isinstance(rpe, int | float):
        head.append(f"RPE {number(rpe)} or under")
    exposures = f"{criterion.get('exposures')} exposures running"
    return "on " + (f"{' at '.join(head)}, {exposures}" if head else exposures)
