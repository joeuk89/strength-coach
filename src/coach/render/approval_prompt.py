"""The approval prompt (ADR 0006, "Consequences"): a fixed layout of about 40 lines the athlete
says yes to. Each list past its cap ends with a count of the rest; `full` lifts the caps."""

import datetime
from collections.abc import Sequence

from coach.core.config import Units
from coach.core.flag import Flag
from coach.core.frozen_prescription import dose, frozen_groups
from coach.core.hevy_actions import HevyActions, RoutineAction
from coach.core.plan_check import CheckedPlan
from coach.core.prescription import LinePrescription, PlanOverride, SessionPrescription

LIST_CAP = 5
NAMES_CAP = 6
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def approval_prompt(
    checked: CheckedPlan,
    actions: HevyActions,
    write_plan_hash: str,
    *,
    units: Units,
    full: bool = False,
) -> str:
    draft = checked.draft
    span_end = draft.week + datetime.timedelta(days=6)
    header = f"Plan {draft.week} to {span_end}, rotation week {draft.position.week}"
    if draft.supersedes is not None:
        header += f", superseding {draft.supersedes}"
    lines = [header]
    for group in _by_session(draft.sessions):
        lines.extend(_session(group, units))
    left = [f for f in checked.flags if f.left is not None]
    standing = [f for f in checked.flags if f.left is None]
    lines += _section("Overrides", [_override(o) for o in draft.overrides], full)
    lines += _section("Left warnings", [_left(f) for f in left], full)
    lines += _section("Warnings not left", [f"  {f.key}: {f.message}" for f in standing], full)
    lines += _hevy(actions, full)
    lines.append(f"Write plan hash {write_plan_hash}")
    return "\n".join(lines)


def _by_session(
    sessions: Sequence[SessionPrescription],
) -> list[list[SessionPrescription]]:
    """A session planned on several days shows once, with its days."""
    grouped: dict[str, list[SessionPrescription]] = {}
    for prescribed in sessions:
        grouped.setdefault(prescribed.session.session_id, []).append(prescribed)
    return list(grouped.values())


def _session(group: list[SessionPrescription], units: Units) -> list[str]:
    first = group[0].session
    days = ", ".join(DAY_NAMES[p.session.date.weekday()] for p in group)
    head = f"{days} {first.date if len(group) == 1 else ''}".rstrip()
    return [
        f"{head} {first.session_id} ({first.location})",
        *(f"  {_line(line, units)}" for line in group[0].lines),
    ]


def _line(line: LinePrescription, units: Units) -> str:
    return f"{line.exercise_id} {dose(frozen_groups(line.groups, units), units)} · {line.change}"


def _override(override: PlanOverride) -> str:
    scope = "/".join(
        str(ref)
        for ref in (override.session_id, override.date, override.exercise_id)
        if ref is not None
    )
    where = f" {scope}" if scope else ""
    return f"  {override.kind}{where} ({override.because}): {override.text}"


def _left(flag: Flag) -> str:
    assert flag.left is not None
    return f"  {flag.key} ({flag.left.because}, {flag.left.source}): {flag.left.text}"


def _section(title: str, rows: list[str], full: bool) -> list[str]:
    if not rows:
        return []
    shown = rows if full else rows[:LIST_CAP]
    rest = len(rows) - len(shown)
    return [title, *shown, *([f"  … {rest} more (--full)"] if rest else [])]


def _hevy(actions: HevyActions, full: bool) -> list[str]:
    rows = [
        ("create folder", list(actions.folders)),
        ("update routine", [_routine(a) for a in actions.updates]),
        ("create routine", [a.session_id for a in actions.creates]),
        ("retire routine", [_routine(a) for a in actions.retires]),
        ("create exercise template", [t.title for t in actions.templates]),
    ]
    found = [f"  {verb}: {_names(names, full)}" for verb, names in rows if names]
    return ["Hevy actions", *found] if found else ["Hevy actions: none"]


def _routine(action: RoutineAction) -> str:
    return f"{action.session_id} ({action.routine_id})"


def _names(names: list[str], full: bool) -> str:
    shown = names if full else names[:NAMES_CAP]
    rest = len(names) - len(shown)
    return ", ".join(shown) + (f" and {rest} more" if rest else "")
