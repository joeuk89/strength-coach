"""Step 1 of the pipeline: each scheme's move from the anchor exposure, or its opening position
with no exposure anywhere (docs/spec/prescription.md, "The move, per scheme" and "Stalls")."""

import datetime
from dataclasses import dataclass, replace

from coach.core.anchor import StartLoad, anchor_load
from coach.core.assistance_ladder import next_rung, rung_of, rungs
from coach.core.bounds import Proposal
from coach.core.e1rm import WINDOW_DAYS, e1rm
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.line_history import (
    line_history,
    loads_on_grid,
    ordinary,
    since_redesign,
    top_on_grid,
)
from coach.core.linear import misses_at, misses_before_reset, reset_load
from coach.core.load import Load, LoadMode
from coach.core.prescription import PrescribeRequest, Step
from coach.core.program.form import LOAD_BEARING_MODES, Line, SetGroup
from coach.core.progression import Verdict, judge
from coach.core.rack import Rack, Rounding, next_row_up
from coach.core.stall import stall_streak
from coach.core.top_backoff import top_set
from coach.core.wave_531 import (
    REP_OUTS,
    TrainingMax,
    find_training_max,
    rep_out,
    rep_out_target,
    rep_outs_due,
    wave_index,
    wave_of,
    wave_targets,
)


@dataclass(frozen=True)
class SchemeInput:
    """`line` is the version's, which the hit test reads; `sets` are the week's."""

    request: PrescribeRequest
    line: Line
    sets: tuple[SetGroup, ...]
    mode: LoadMode
    rack: Rack | None
    scope: Scope

    @property
    def loaded(self) -> bool:
        return self.mode in LOAD_BEARING_MODES

    @property
    def on(self) -> datetime.date:
        return self.request.planned.date


@dataclass(frozen=True)
class Move:
    """The proposal `bound()` takes, the rounding it asks for, the line's sets as the scheme
    shapes them, and the change where the scheme names one."""

    proposal: Proposal
    rounding: Rounding
    sets: tuple[SetGroup, ...]
    change: str | None = None


@dataclass
class SchemeMoves:
    """`steps` and `flags` are the line's, appended to in pipeline order."""

    given: SchemeInput
    steps: list[Step]
    flags: list[Flag]

    @property
    def line(self) -> Line:
        return self.given.line

    def anchor_top(self, exposure: Exposure) -> Load | None:
        """The anchor's top working load on the grid the scheme moves over."""
        if not self.given.loaded:
            return None
        if self.line.scheme.name == "assistance_ladder":
            return self._rung(exposure)
        rack = self.given.rack
        if rack is None:
            top = exposure.top_load
            return None if top is None else top.as_mode(self.given.mode)
        load, offgrid = anchor_load(
            exposure,
            rack,
            session_id=self.given.request.planned.session_id,
            monday=self.given.scope.monday,
            mode=self.given.mode,
        )
        if offgrid is not None:
            self.flags.append(offgrid)
        return load

    def opening(self, found: StartLoad) -> Move:
        """No exposure anywhere: the start load at the scheme's opening position."""
        ladder = rungs(self.line)
        if self.line.scheme.name == "assistance_ladder" and ladder:
            first = Load(ladder[0], "assisted")
            self.steps.append(Step("scheme", None, first.amount, "first_rung"))
            return self._held(first)
        if self.line.scheme.name == "wave_531":
            return self._wave(None)
        return self._held(self._start_load(found))

    def stall(self, exposure: Exposure) -> None:
        history = since_redesign(
            ordinary(line_history(self.given.request.exposures, exposure, on=self.given.on)),
            self.given.request.redesigned,
        )
        streak = stall_streak(self.line, history)
        if streak:
            self._raise(
                "stall_streak",
                {"streak": len(streak), "exposures": [e.ref for e in streak]},
                f"{len(streak)} exposures in a row with no gain on the "
                f"{self.line.scheme.name} metric",
            )

    def held(self, exposure: Exposure, before: Load | None) -> Move:
        """A `hold` override: the anchor's dose repeated with no scheme step."""
        if self.line.scheme.name == "wave_531":
            repeated = self._wave_repeated(exposure)
            if repeated is not None:
                return repeated
        return self._held(before)

    def move(self, exposure: Exposure, before: Load | None) -> Move:
        if self.line.scheme.name == "assistance_ladder":
            return self._climb(exposure, before)
        if self.line.scheme.name == "top_backoff":
            return self._top(exposure, before)
        if self.line.scheme.name == "wave_531":
            return self._wave(exposure)
        verdict = self._judge(exposure, before)
        rack = self.given.rack
        if verdict.hit and before is not None and rack is not None:
            moved = next_row_up(rack, before)
            cause = "hit" if moved.cause == "row" else "rack_top"
            self.steps.append(Step("scheme", before.amount, moved.load.amount, cause))
            return Move(moved.load, "step_up" if moved.load != before else "hold", self.given.sets)
        if self.line.scheme.name == "linear" and before is not None and not verdict.incomplete:
            reset = self._reset(exposure, before)
            if reset is not None:
                return reset
        return self._held(before)

    def _rung(self, exposure: Exposure) -> Load | None:
        logged = exposure.top_load
        if logged is None or logged.mode != "assisted":
            return None
        rung = Load(rung_of(logged.amount, rungs(self.line)), "assisted")
        if rung != logged:
            self._raise(
                "offgrid_anchor_ignored",
                {
                    "exposure": exposure.ref,
                    "logged_load": logged.amount,
                    "anchor_used": rung.amount,
                },
                f"the logged {logged.amount:g} is not a rung; the anchor uses {rung.amount:g}",
            )
        return rung

    def _climb(self, exposure: Exposure, rung: Load | None) -> Move:
        if rung is None or not self._judge(exposure, rung).hit:
            return self._held(rung)
        up = next_rung(rung.amount, rungs(self.line))
        if up is None:
            self.steps.append(Step("scheme", rung.amount, rung.amount, "rack_top"))
            return self._held(rung)
        self.steps.append(Step("scheme", rung.amount, up, "hit"))
        return Move(Load(up, "assisted"), "step_up", self.given.sets)

    def _top(self, exposure: Exposure, before: Load | None) -> Move:
        found = e1rm(self.given.request.exposures, self.line.exercise, self.given.on)
        if found is None:
            self._raise(
                "no_e1rm",
                {"exercise_id": self.line.exercise, "scheme": self.line.scheme.name},
                f"no e1RM for {self.line.exercise} in the window, so the top set holds",
            )
            return self._held(before)
        if before is None:
            return self._held(before)
        floor = self._heaviest_top(exposure, before)
        top = top_set(found.load.as_mode(self.given.mode), self.line, floor, self.given.rack)
        if top.load != before:
            self.steps.append(Step("scheme", before.amount, top.load.amount, top.cause))
        return Move(top.load, "hold", self.given.sets)

    def _heaviest_top(self, exposure: Exposure, anchor_top: Load) -> Load:
        """The one-row cap counts from the line's heaviest top in the e1RM window, so a lighter
        bad day as the anchor never lowers the top set, and another session never lifts it."""
        start = self.given.on - datetime.timedelta(days=WINDOW_DAYS)
        history = ordinary(line_history(self.given.request.exposures, exposure, on=self.given.on))
        tops = (
            top_on_grid(e, self.given.rack, self.given.mode) for e in history if e.date >= start
        )
        return max((anchor_top, *(t for t in tops if t is not None)), key=lambda t: t.amount)

    def _wave(self, exposure: Exposure | None) -> Move:
        training_max = find_training_max(
            self.given.request.decisions, self.line.exercise, self.line.start_load, self.given.mode
        )
        if training_max is None:
            self._start_load(StartLoad(None))
            return self._held(None)
        index = wave_index(self.given.request.hard_week_count)
        count = sum(group.count for group in self.given.sets if group.working)
        # Unrounded, so a cut multiplies the training max and the rack step rounds once.
        targets = wave_targets(training_max.load, index, count, rack=None)
        wave = f"wave {index + 1}"
        self.steps.append(
            Step("scheme", training_max.load.amount, tuple(t.amount for t in targets), wave)
        )
        if exposure is not None:
            self._read_rep_outs(exposure, training_max)
        return Move(
            targets,
            "cut",
            self._wave_sets(index),
            f"{wave}: training max {training_max.load.amount:g}",
        )

    def _wave_repeated(self, exposure: Exposure) -> Move | None:
        """The anchor's wave of the training max; off the waves, its logged loads at this
        week's reps. The training max stays put."""
        training_max = find_training_max(
            self.given.request.decisions, self.line.exercise, self.line.start_load, self.given.mode
        )
        if training_max is None:
            return None
        rack = self.given.rack
        count = sum(group.count for group in self.given.sets if group.working)
        index = wave_of(exposure, training_max.load, rack)
        if index is not None:
            loads = wave_targets(training_max.load, index, count, rack)
        else:
            index = wave_index(self.given.request.hard_week_count)
            loads = loads_on_grid(exposure, count, rack, self.given.mode)
        if not loads:
            return None
        return Move(loads, "hold", self._wave_sets(index), "held")

    def _wave_sets(self, index: int) -> tuple[SetGroup, ...]:
        return tuple(
            replace(group, reps=REP_OUTS[index]) if group.working else group
            for group in self.given.sets
        )

    def _read_rep_outs(self, exposure: Exposure, training_max: TrainingMax) -> None:
        rack = self.given.rack
        index = wave_of(exposure, training_max.load, rack)
        if index is not None and (reps := rep_out(exposure)) < (target := rep_out_target(index)):
            self._raise(
                "rep_range_missed",
                {
                    "set_index": len(exposure.working),
                    "reps": reps,
                    "range": [target, target],
                    "logged_rpe": exposure.working[-1].rpe,
                    "authored_rpe": None,
                },
                f"the rep-out logged {reps} reps, short of wave {index + 1}'s {target}",
            )
        history = ordinary(line_history(self.given.request.exposures, exposure, on=self.given.on))
        rep_outs = rep_outs_due(history, training_max.load, rack)
        if rep_outs:
            self._raise(
                "training_max_due",
                {
                    "training_max": training_max.load.amount,
                    "source": training_max.source,
                    "rep_outs": list(rep_outs),
                },
                f"all three waves logged at training max {training_max.load.amount:g}: rep-outs "
                f"{', '.join(map(str, rep_outs))}",
            )

    def _reset(self, exposure: Exposure, before: Load) -> Move | None:
        history = ordinary(line_history(self.given.request.exposures, exposure, on=self.given.on))
        misses = misses_at(self.line, history, before, self.given.rack)
        if misses < misses_before_reset(self.line):
            return None
        reset = reset_load(self.line, before, self.given.rack)
        self.steps.append(Step("scheme", before.amount, reset.amount, f"reset, misses {misses}"))
        return Move(reset, "cut", self.given.sets, f"reset {before.amount:g} → {reset.amount:g}")

    def _start_load(self, found: StartLoad) -> Load | None:
        if not self.given.loaded:
            return None
        if found.load is None:
            self._raise(
                "start_load_missing",
                {"exercise_id": self.line.exercise},
                f"{self.line.exercise} has no Exposure yet and the line has no start_load",
            )
            return None
        self.steps.append(Step("scheme", None, found.load.amount, "start_load"))
        return found.load

    def _held(self, load: Load | None) -> Move:
        return Move(load, "hold", self.given.sets)

    def _judge(self, exposure: Exposure, load: Load | None) -> Verdict:
        verdict = judge(self.line, exposure, load)
        if verdict.missed is not None:
            missed = verdict.missed
            self._raise(
                "rep_range_missed",
                {
                    "set_index": missed.set_index,
                    "reps": missed.reps,
                    "range": list(missed.range),
                    "logged_rpe": missed.logged_rpe,
                    "authored_rpe": missed.authored_rpe,
                },
                f"working set {missed.set_index} logged {missed.reps} reps at RPE "
                f"{missed.logged_rpe}: over the line, so the load holds",
            )
        return verdict

    def _raise(self, code: str, params: dict[str, object], message: str) -> None:
        self.flags.append(raise_flag(code, self.given.scope, params, message))
