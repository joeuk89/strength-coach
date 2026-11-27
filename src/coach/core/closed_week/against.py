"""Each line of a planned session beside the working sets logged for it: the
against-the-prescription read (docs/spec/week.md, "The session gate"; docs/spec/verbs.md,
"Read views")."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from coach.core.closed_week.match import WeekWorkout
from coach.core.exposure import ExposureSet

type LineState = Literal["logged", "not_logged", "not_prescribed"]

# rn:deloads.11: a logged RPE this far from the authored one counts as effort off.
EFFORT_OFF_RPE = 1.5
# The tolerance a difference of tenths carries.
ROUNDING = 1e-9


@dataclass(frozen=True)
class TargetSet:
    """One prescribed working set: the bottom of its reps, its RPE, the top of its reps, its
    load in athlete units and its seconds."""

    reps: int | None = None
    rpe: float | None = None
    top: int | None = None
    load: float | None = None
    seconds: int | None = None


@dataclass(frozen=True)
class LineAgainst:
    """One line of a planned session, or one exercise logged in its workout and not prescribed,
    with the working sets logged for it. Logged sets pair with prescribed sets in order."""

    exercise: str
    state: LineState
    targets: tuple[TargetSet, ...] = ()
    logged: tuple[ExposureSet, ...] = ()
    hold: bool = False

    @property
    def pairs(self) -> tuple[tuple[ExposureSet, TargetSet], ...]:
        return tuple(zip(self.logged, self.targets, strict=False))

    @property
    def reps_short(self) -> tuple[int | None, ...]:
        """Per logged set, the reps under the bottom of the range; `None` when unpaired or
        either set has no reps."""
        return tuple(_reps_short(s, t) for s, t in self._paired_or_none())

    @property
    def rpe_off(self) -> tuple[float | None, ...]:
        """Per logged set, the logged RPE minus the authored one; `None` when either is
        missing or the set is unpaired."""
        return tuple(
            None if t is None or s.rpe is None or t.rpe is None else round(s.rpe - t.rpe, 1)
            for s, t in self._paired_or_none()
        )

    @property
    def sets_missing(self) -> int:
        return max(len(self.targets) - len(self.logged), 0) if self.state == "logged" else 0

    @property
    def rpe_missing(self) -> int:
        return sum(1 for s, _ in self.pairs if s.rpe is None)

    @property
    def reps_missed(self) -> int:
        return sum(1 for short in self.reps_short if short)

    @property
    def effort_off(self) -> int:
        return sum(
            1 for off in self.rpe_off if off is not None and abs(off) >= EFFORT_OFF_RPE - ROUNDING
        )

    @property
    def off(self) -> bool:
        return (
            self.state != "logged"
            or self.sets_missing > 0
            or self.reps_missed > 0
            or self.rpe_missing > 0
            or self.effort_off > 0
        )

    def _paired_or_none(self) -> Iterable[tuple[ExposureSet, TargetSet | None]]:
        targets: list[TargetSet | None] = list(self.targets)
        return ((s, targets[i] if i < len(targets) else None) for i, s in enumerate(self.logged))


def _reps_short(logged: ExposureSet, target: TargetSet | None) -> int | None:
    if target is None or target.reps is None or logged.reps is None:
        return None
    return max(target.reps - logged.reps, 0)


def lines_against(
    targets: Mapping[str, tuple[TargetSet, ...]],
    held: frozenset[str],
    workout: WeekWorkout | None,
) -> tuple[LineAgainst, ...]:
    """Every prescribed line in plan order, `hold` lines among them, then every exercise the
    workout logged that no line prescribes."""
    logged = {} if workout is None else {e.exercise_id: e.working for e in workout.exposures}
    prescribed = tuple(
        LineAgainst(
            exercise,
            "logged" if exercise in logged else "not_logged",
            sets,
            logged.get(exercise, ()),
            exercise in held,
        )
        for exercise, sets in targets.items()
    )
    unprescribed = tuple(
        LineAgainst(exercise, "not_prescribed", (), sets)
        for exercise, sets in logged.items()
        if exercise not in targets
    )
    return prescribed + unprescribed


@dataclass(frozen=True)
class AgainstPrescription:
    reps_missed: int = 0
    effort_off: int = 0
    rpe_missing: int = 0


def against(lines: Iterable[LineAgainst]) -> AgainstPrescription:
    """The session's counts: every prescribed line logged, a `hold` line left out."""
    counted = [line for line in lines if line.state == "logged" and not line.hold]
    return AgainstPrescription(
        reps_missed=sum(line.reps_missed for line in counted),
        effort_off=sum(line.effort_off for line in counted),
        rpe_missing=sum(line.rpe_missing for line in counted),
    )
