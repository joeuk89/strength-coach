"""`coach progress` as a page (docs/spec/goals.md, "`coach progress`")."""

import re
from collections.abc import Mapping

from coach.core.config import Units
from coach.core.flag import Flag
from coach.core.goal import Target
from coach.core.pages import PageNames
from coach.core.progress import Progress
from coach.core.registries.ledger import MILESTONE_TARGET_KINDS
from coach.core.registries.program import MUSCLES
from coach.core.registries.registry import title_of
from coach.core.registries.schemes import CADENCE_SIGNALS, SCHEMES
from coach.render.markdown import (
    MANUAL_CLIMB,
    bullets,
    cell,
    marked_rung,
    page,
    rn_link,
    section,
    table,
)

PER_MUSCLE = "per_muscle"
SCHEME_CODE = re.compile(r"\b(?:" + "|".join(SCHEMES.names()) + r")\b")


def progress_page(
    report: Progress, *, names: PageNames, units: Units, bodyweight_units: Units, pin: str
) -> str:
    block = report.block
    intro = (
        f"The closed Block ran from {block.start.isoformat()} to {block.end.isoformat()}."
        if block
        else "No Block has closed yet."
    )
    return page(
        "Progress",
        intro,
        section(
            f"Priority lifts ({units})",
            table(
                [
                    "lift",
                    "scheme",
                    "e1RM now",
                    "change over the block",
                    "change over three",
                    "best set",
                    "stall streak",
                    "resets",
                    "signal",
                ],
                [
                    [
                        names.exercise(lift.exercise_id),
                        None if lift.scheme is None else title_of(SCHEMES, lift.scheme),
                        lift.e1rm_now,
                        lift.change_over_block,
                        lift.change_over_three,
                        None
                        if lift.best is None
                        else f"{cell(lift.best.load)} × {lift.best.reps} on {lift.best.date}",
                        lift.stall_streak,
                        lift.resets,
                        None if lift.signal is None else title_of(CADENCE_SIGNALS, lift.signal),
                    ]
                    for lift in report.lifts
                ],
            ),
        ),
        section(
            "Milestones",
            table(
                ["lift", "target", "reached", "to go"],
                [
                    [
                        names.exercise(m.milestone.exercise),
                        _target(m.milestone.target),
                        m.reached.isoformat() if m.reached else None,
                        m.to_go if m.computable else "not computable",
                    ]
                    for m in report.milestones
                ],
            ),
        ),
        section(
            "Ladders",
            table(
                [
                    "line",
                    "standing exercise",
                    "rungs",
                    "exposures toward the criterion",
                    "met",
                    "held",
                ],
                [
                    [
                        f"{names.session(r.line.session_id)}: {names.exercise(r.line.line_key)}",
                        names.exercise(r.exercise),
                        "<br>".join(
                            marked_rung(label, standing=index == r.rung)
                            for index, label in enumerate(r.labels, start=1)
                        ),
                        MANUAL_CLIMB if r.needed is None else f"{r.exposures} of {r.needed}",
                        r.met,
                        r.held,
                    ]
                    for r in report.ladders
                ],
            ),
        ),
        section(
            "Dose",
            "\n\n".join(
                part
                for part in (
                    table(
                        ["week", "kind", "muscles", "priority lifts"],
                        [
                            [
                                w.monday.isoformat(),
                                w.kind,
                                _muscles(w.muscles),
                                _named(w.lifts, names),
                            ]
                            for w in report.dose
                        ],
                    ),
                    _dose_target(report.dose_target, names),
                )
                if part
            ),
        ),
        section(
            "Adherence",
            ""
            if report.adherence is None
            else bullets(
                [
                    f"core sessions trained: {report.adherence.core_trained} of "
                    f"{report.adherence.core_planned}",
                    f"optional sessions trained: {report.adherence.optional_trained}",
                    f"misses by tag: {cell(report.adherence.misses) or 'none'}",
                ]
            ),
        ),
        section(
            "Phase",
            ""
            if report.phase is None
            else bullets(
                [
                    f"kind: {report.phase.kind}",
                    f"target rate: {cell(report.phase.target_rate)} % of bodyweight a week",
                    f"14-day trend: {cell(report.phase.observed_rate)} % of bodyweight a week",
                    f"until: {cell(report.phase.until)} ({bodyweight_units})",
                    f"met: {cell(report.phase.met)}",
                ]
            ),
        ),
        section(
            "Goal",
            ""
            if report.goal is None
            else f"{report.goal.kind}, adopted {report.goal.adopted}.\n\n{report.goal.why}",
        ),
        section("Signals", bullets([_signal(s, names, pin) for s in report.signals])),
    )


def _named(by_exercise: Mapping[str, int], names: PageNames) -> str:
    """Pairs, not a renamed mapping: two exercises can share a name and each keeps its figure."""
    return ", ".join(f"{names.exercise(id_)} {cell(n)}" for id_, n in by_exercise.items())


def _muscles(by_muscle: Mapping[str, float]) -> str:
    return ", ".join(f"{title_of(MUSCLES, m)} {cell(n)}" for m, n in by_muscle.items())


def _dose_target(target: Mapping[str, int], names: PageNames) -> str:
    """The muscle target sits under `per_muscle` beside the priority lifts' targets."""
    if not target:
        return ""
    lifts = {key: n for key, n in target.items() if key != PER_MUSCLE}
    parts = [f"per muscle {cell(target[PER_MUSCLE])}"] if PER_MUSCLE in target else []
    if lifts:
        parts.append(_named(lifts, names))
    return f"Target: {', '.join(parts)}."


def _target(target: Target) -> str:
    title = title_of(MILESTONE_TARGET_KINDS, target.kind)
    if target.kind == "load_x_reps":
        return f"{title}: {cell(target.load)} × {cell(target.reps)}"
    return f"{title}: {cell(target.value)}"


def _signal(flag: Flag, names: PageNames, pin: str) -> str:
    """A cadence signal's message opens with the exercise its scope names and names schemes by
    their codes."""
    exercise = str(flag.scope.exercise_id)
    message = SCHEME_CODE.sub(
        lambda found: title_of(SCHEMES, found[0]),
        flag.message.replace(exercise, names.exercise(exercise), 1),
    )
    text = f"{flag.severity}, {title_of(CADENCE_SIGNALS, flag.code)}: {message}"
    return f"{text} ({rn_link(flag.rn, pin)})" if flag.rn else text
