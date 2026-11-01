"""Step 1 of the pipeline: each scheme's move from the anchor exposure, or its opening position
with no exposure anywhere (docs/spec/prescription.md, "The move, per scheme" and "Stalls")."""

import datetime
from dataclasses import dataclass

from coach.core.anchor import StartLoad, anchor_load
from coach.core.assistance_ladder import next_rung, rung_of, rungs
from coach.core.bounds import Proposal
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.line_history import line_history, ordinary
from coach.core.linear import misses_at, misses_before_reset, reset_load
from coach.core.load import Load, LoadMode
from coach.core.prescription import PrescribeRequest, Step
from coach.core.program.form import LOAD_BEARING_MODES, Line, SetGroup
from coach.core.progression import Verdict, judge
from coach.core.rack import Rack, Rounding, next_row_up


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
        if self.line.scheme.name == "assistance_ladder":
            first = Load(rungs(self.line)[0], "assisted")
            self.steps.append(Step("scheme", None, first.amount, "first_rung"))
            return self._held(first)
        return self._held(self._start_load(found))

    def move(self, exposure: Exposure, before: Load | None) -> Move:
        if self.line.scheme.name == "assistance_ladder":
            return self._climb(exposure, before)
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
