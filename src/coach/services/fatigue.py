"""The light-week proposal as a view of the store (docs/spec/week.md, "Fatigue triggers and the
light-week proposal"). Nothing is stored: the proposal at each recorded check-in is derived
again the way `checkin open` derived it, from its window, the readiness on the row before it
and the Block count its window closes."""

import datetime
from dataclasses import dataclass
from typing import cast

from coach.core.check_in import Window
from coach.core.closed_week.block import Block
from coach.core.fatigue import (
    DriftExposure,
    NiggleHistory,
    Proposal,
    niggle_trigger,
    propose,
    readiness_trigger,
    rpe_drift,
    short_sleep_week,
)
from coach.core.planned_week import week_monday
from coach.core.program.form import Deload
from coach.services.closed_weeks import WeekLog, WindowList
from coach.store import check_ins, decisions, exercises, niggles, programs, readings, week_plans
from coach.store.connection import Connection
from coach.store.rows import Row

# A compound lift is multi-joint: the patterns RPE drift reads (rn:autoregulation.4).
COMPOUND_PATTERNS = frozenset(
    {
        "squat",
        "hinge",
        "lunge",
        "horizontal_push",
        "vertical_push",
        "horizontal_pull",
        "vertical_pull",
    }
)
# Light and return work are not judged for drift.
UNJUDGED_WEEKS = ("light", "return")


@dataclass(frozen=True)
class Standing:
    proposal: Proposal
    check_in: str


@dataclass(frozen=True)
class Opened:
    """A window's proposal and the Block its weeks leave open."""

    proposal: Proposal
    block: Block | None


class Fatigue:
    """What the triggers read, loaded once."""

    def __init__(self, conn: Connection, log: WeekLog) -> None:
        self.log = log
        version = programs.latest(conn)
        self.deload: Deload | None = version.form.deload if version else None
        self.patterns = {str(r["id"]): r["pattern"] for r in exercises.every(conn)}
        self.niggles = tuple(
            NiggleHistory(
                str(n["id"]),
                tuple(
                    (datetime.date.fromisoformat(str(e["date"])), str(e["status"]))
                    for e in cast(list[Row], n["events"])
                ),
            )
            for n in niggles.every(conn)
        )
        self.nights = {
            datetime.date.fromisoformat(str(r["night"])): float(str(r["hours"]))
            for r in readings.live(conn, "sleep_night")
        }
        self.check_ins = check_ins.current(conn)
        cleared = [
            *week_plans.light_week_approvals(conn),
            *(
                datetime.date.fromisoformat(str(d["recorded_at"])[:10])
                for d in decisions.every(conn)
                if d["kind"] == "decline_ceiling"
            ),
        ]
        self.cleared_on = max(cleared, default=None)

    def opened(self, window: Window, readiness: str | None, windows: WindowList) -> Opened:
        """`windows` are the check-in windows closed so far, this one included."""
        block = self.log.closed_by(windows).open_block
        triggers = (
            readiness_trigger(readiness),
            rpe_drift(self._drift_exposures(window.end), window),
            niggle_trigger(self.niggles, window),
            short_sleep_week(self.nights, window.end),
        )
        proposal = propose(
            [t for t in triggers if t is not None],
            hard_weeks=block.hard_weeks if block else 0,
            deload=self.deload,
        )
        return Opened(proposal, block)

    def standing(self, before: datetime.date | None = None) -> Standing | None:
        """The newest proposal from a recorded check-in that no light-week plan or
        `decline_ceiling` Decision has answered since."""
        rows = [r for r in self.check_ins if before is None or r.date < before]
        windows = [(r.window.start, r.window.end) for r in rows]
        for i in reversed(range(len(rows))):
            row = rows[i]
            if self.cleared_on is not None and self.cleared_on >= row.date:
                return None
            readiness = rows[i - 1].readiness if i else None
            proposal = self.opened(row.window, readiness, windows[: i + 1]).proposal
            if proposal.state == "propose":
                return Standing(proposal, row.id)
        return None

    def _drift_exposures(self, through: datetime.date) -> list[DriftExposure]:
        if not self.log.redesigns:
            return []
        found: list[DriftExposure] = []
        monday = week_monday(self.log.redesigns[0])
        while monday <= through:
            week = self.log.week(monday)
            monday += datetime.timedelta(weeks=1)
            if week.kind in UNJUDGED_WEEKS:
                continue
            for outcome in week.sessions:
                if outcome.workout_id is None:
                    continue
                work = outcome.work
                for exposure in self.log.workout(outcome.workout_id).exposures:
                    targets = work.targets.get(exposure.exercise_id)
                    if (
                        not targets
                        or exposure.date > through
                        or exposure.exercise_id in work.returned
                        or self.patterns.get(exposure.exercise_id) not in COMPOUND_PATTERNS
                    ):
                        continue
                    found.append(
                        DriftExposure(
                            exposure.exercise_id,
                            exposure.date,
                            exposure.ref,
                            tuple(zip(exposure.working, targets, strict=False)),
                            extra=len(exposure.working) > len(targets),
                        )
                    )
        return found


def standing_proposal(conn: Connection, log: WeekLog) -> Standing | None:
    return Fatigue(conn, log).standing()
