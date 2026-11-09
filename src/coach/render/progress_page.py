"""`coach progress` as a page (docs/spec/goals.md, "`coach progress`")."""

from coach.core.config import Units
from coach.core.pages import PageNames
from coach.core.progress import Progress
from coach.render.markdown import MANUAL_CLIMB, bullets, cell, flag_text, page, section, table


def progress_page(
    report: Progress, *, names: PageNames, units: Units, bodyweight_units: Units, pin: str
) -> str:
    block = report.block
    intro = (
        f"Closed Block `{block.id}`, {block.start.isoformat()} to {block.end.isoformat()}."
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
                        lift.exercise_id,
                        lift.scheme,
                        lift.e1rm_now,
                        lift.change_over_block,
                        lift.change_over_three,
                        None
                        if lift.best is None
                        else f"{cell(lift.best.load)} × {lift.best.reps} on {lift.best.date}",
                        lift.stall_streak,
                        lift.resets,
                        lift.signal,
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
                        m.milestone.exercise,
                        m.milestone.target.describe(),
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
                ["line", "standing rung", "exposures toward the criterion", "met", "held"],
                [
                    [
                        f"{names.session(r.line.session_id)}: {names.exercise(r.line.line_key)}",
                        f"{r.rung} of {r.rungs}, {names.exercise(r.exercise)}",
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
                        [[w.monday.isoformat(), w.kind, w.muscles, w.lifts] for w in report.dose],
                    ),
                    f"Target: {cell(report.dose_target)}." if report.dose_target else "",
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
        section("Signals", bullets([flag_text(s.to_json(), pin) for s in report.signals])),
    )
