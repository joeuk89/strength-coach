"""The approval prompt (ADR 0006, "Consequences"): a fixed layout of about 40 lines the athlete
says yes to. Each list past its cap ends with a count of the rest; `full` lifts the caps."""

import datetime
from collections.abc import Sequence

from coach.core.config import Units
from coach.core.flag import Flag
from coach.core.frozen_prescription import dose
from coach.core.hevy_actions import HevyActions, RoutineAction
from coach.core.plan_summary import PlanSummary, SummaryLine, SummarySession
from coach.core.prescription import PlanOverride

LIST_CAP = 5
NAMES_CAP = 6
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def approval_prompt(
    summary: PlanSummary,
    actions: HevyActions,
    write_plan_hash: str,
    *,
    units: Units,
    full: bool = False,
    resumes: str | None = None,
    moved_routines: Sequence[str] = (),
) -> str:
    span_end = summary.week + datetime.timedelta(days=6)
    header = f"Plan {summary.week} to {span_end}, rotation week {summary.position.week}"
    if resumes is not None:
        header += f", resuming {resumes}"
    elif summary.supersedes is not None:
        header += f", superseding {summary.supersedes}"
    lines = [header]
    if moved_routines:
        lines.append(f"Changed in Hevy since approval: {', '.join(moved_routines)}")
    for group in _by_session(summary.sessions):
        lines.extend(_session(group, units))
    left = [f for f in summary.flags if f.left is not None]
    standing = [f for f in summary.flags if f.left is None]
    lines += _section("Overrides", [_override(o) for o in summary.overrides], full)
    lines += _section("Left warnings", [_left(f) for f in left], full)
    lines += _section("Warnings not left", [f"  {f.key}: {f.message}" for f in standing], full)
    lines += _hevy(actions, full)
    lines.append(f"Write plan hash {write_plan_hash}")
    return "\n".join(lines)


def _by_session(sessions: Sequence[SummarySession]) -> list[list[SummarySession]]:
    """A session planned on several days shows once, with its days."""
    grouped: dict[str, list[SummarySession]] = {}
    for session in sessions:
        grouped.setdefault(session.session_id, []).append(session)
    return list(grouped.values())


def _session(group: list[SummarySession], units: Units) -> list[str]:
    first = group[0]
    days = ", ".join(DAY_NAMES[s.date.weekday()] for s in group)
    head = f"{days} {first.date if len(group) == 1 else ''}".rstrip()
    return [
        f"{head} {first.session_id} ({first.location})",
        *(f"  {_line(line, units)}" for line in group[0].lines),
    ]


def _line(line: SummaryLine, units: Units) -> str:
    shown = f"{line.exercise_id} {dose(line.set_groups, units)} · {line.change}"
    labels = line.rung_labels
    if labels is None:
        return shown
    return f"{shown} · {labels.own}" + ("" if labels.next is None else f" · Next: {labels.next}")


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
