"""What the log cannot answer about a lift in a check-in window (docs/spec/check-in.md, "Views",
the Lifts row). A logged RPE is the athlete's answer: a lift is asked about only when a set the
scheme reads carries none, or its sets do not add up."""

import datetime
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from coach.core.closed_week.against import ROUNDING, LineAgainst
from coach.core.closed_week.sessions import SessionOutcome
from coach.core.e1rm import PRECISION, set_e1rm
from coach.core.exposure import Exposure
from coach.core.load import Load
from coach.core.program.form import Line
from coach.core.registries.schemes import SCHEMES, RpeOn
from coach.core.rpe_gap import RPE_GAP

type Reason = str

RPE_MISSING: Reason = "rpe_missing"
REPS_SHORT_AT_LOW_RPE: Reason = "reps_short_at_low_rpe"
EXPOSURES_DISAGREE: Reason = "exposures_disagree"
# Opinion: e1RMs from two exposures of a lift more than a fifth apart cannot both be right,
# beyond the day-to-day swing a rated RPE carries.
DISAGREE_SHARE = 0.2


@dataclass(frozen=True)
class LoggedLine:
    """One lift's sets in one session of the window beside the prescription, from the
    plan-against-log read. `rpe_on` is where the line's scheme reads RPE; a `capped` line took a
    return band, whose RPE cap sits under the prescribed RPE, so no RPE gap is read on it."""

    session_id: str | None
    date: datetime.date
    line: LineAgainst
    rpe_on: RpeOn
    capped: bool = False

    @property
    def exercise(self) -> str:
        return self.line.exercise

    @property
    def rpe_missing(self) -> bool:
        """A set the scheme reads has no RPE against a prescribed one that authored it."""
        if self.line.hold or self.rpe_on == "none":
            return False
        read = self.line.pairs[:1] if self.rpe_on == "top" else self.line.pairs
        return any(s.rpe is None and t.rpe is not None for s, t in read)

    @property
    def short_at_low_rpe(self) -> bool:
        """A set short of the range's bottom at an RPE well under the prescribed one."""
        return not self.capped and any(
            short and off is not None and _well_under(off)
            for short, off in zip(self.line.reps_short, self.line.rpe_off, strict=True)
        )

    @property
    def rpe_gap(self) -> float | None:
        """The mean of logged minus prescribed RPE over the sets that carry both."""
        if self.capped:
            return None
        offs = [off for off in self.line.rpe_off if off is not None]
        return round(sum(offs) / len(offs), PRECISION) if offs else None

    @property
    def under_authored(self) -> bool:
        gap = self.rpe_gap
        return gap is not None and _well_under(gap)

    @property
    def e1rm(self) -> Load | None:
        """The best e1RM among the sets that carry an RPE."""
        points = [p for s in self.line.logged if s.rpe is not None and (p := set_e1rm(s))]
        return max(points, key=lambda p: p.total, default=None)


@dataclass(frozen=True)
class LiftDoubt:
    exercise: str
    reason: Reason
    lines: tuple[LoggedLine, ...]


def logged_lines(outcome: SessionOutcome) -> tuple[LoggedLine, ...]:
    """Every line of a matched session that logged sets, dated by the first workout logging it."""
    session = outcome.session
    found: list[LoggedLine] = []
    for line in outcome.lines:
        if not line.logged:
            continue
        date = next(
            (
                w.date
                for w in outcome.workouts
                if any(e.exercise_id == line.exercise for e in w.exposures)
            ),
            session.date,
        )
        rpe_on = _rpe_on(session.lines, line.exercise)
        capped = line.exercise in outcome.work.returned
        found.append(LoggedLine(session.session_id, date, line, rpe_on, capped))
    return tuple(found)


def unmatched_line(exposure: Exposure) -> LoggedLine:
    """A lift logged in a workout no planned session in the window took: nothing prescribed."""
    line = LineAgainst(exposure.exercise_id, "not_prescribed", (), exposure.working)
    return LoggedLine(exposure.session_id, exposure.date, line, "none")


def lift_doubts(lines: Iterable[LoggedLine]) -> tuple[LiftDoubt, ...]:
    """One doubt per lift and reason, the lift's lines that raise it quoted, in lift order."""
    by_lift: dict[str, list[LoggedLine]] = {}
    for line in lines:
        by_lift.setdefault(line.exercise, []).append(line)
    found: list[LiftDoubt] = []
    for exercise, mine in sorted(by_lift.items()):
        unrated = tuple(line for line in mine if line.rpe_missing)
        if unrated:
            found.append(LiftDoubt(exercise, RPE_MISSING, unrated))
        short = tuple(line for line in mine if line.short_at_low_rpe)
        if short:
            found.append(LiftDoubt(exercise, REPS_SHORT_AT_LOW_RPE, short))
        apart = _far_apart(mine)
        if apart:
            found.append(LiftDoubt(exercise, EXPOSURES_DISAGREE, apart))
    return tuple(found)


def _far_apart(lines: Sequence[LoggedLine]) -> tuple[LoggedLine, ...]:
    """The lift's highest and lowest e1RM lines, in date order, when they are too far apart."""
    rated = [(line, e1rm) for line in lines if (e1rm := line.e1rm) is not None]
    if len(rated) < 2:
        return ()
    high = max(rated, key=lambda r: r[1].total)
    low = min(rated, key=lambda r: r[1].total)
    if low[1].total >= (1 - DISAGREE_SHARE) * high[1].total:
        return ()
    return tuple(sorted((high[0], low[0]), key=lambda line: line.date))


def _well_under(off: float) -> bool:
    return off <= -RPE_GAP + ROUNDING


def _rpe_on(lines: Sequence[Line], exercise: str) -> RpeOn:
    """A line swapped to another exercise froze under that exercise; its scheme is unknown here,
    so the prescription's own authored RPE says where it is read."""
    for line in lines:
        if exercise == line.exercise or exercise in line.rung_exercises:
            name = line.scheme.name
            return SCHEMES.get(name).rpe_on if name in SCHEMES else "every_working"
    return "every_working"
