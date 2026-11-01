"""The derivation pipeline (ADR 0017, docs/spec/prescription.md, "The pipeline"): the scheme's
move from the anchor exposure, rack rounding, then the warm-ups. Each step that changed a load is
recorded as `(step, from, to, cause)`."""

import datetime
from dataclasses import dataclass, field
from typing import cast

from coach.core.anchor import AnchorExposure, StartLoad, anchor, anchor_load
from coach.core.assistance_ladder import next_rung, rung_of, rungs
from coach.core.conditioning import conditioning_dose
from coach.core.e1rm import e1rm
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.line_history import line_history, ordinary
from coach.core.linear import misses_at, misses_before_reset, reset_load
from coach.core.load import Load, LoadMode
from coach.core.planned_week import week_monday
from coach.core.prescription import (
    ConditioningDose,
    ExerciseFacts,
    LinePrescription,
    PrescribedGroup,
    PrescribeRequest,
    SessionPrescription,
    Step,
)
from coach.core.program.form import LOAD_BEARING_MODES, RACK_MODES, Line, SetGroup
from coach.core.progression import Verdict, judge
from coach.core.rack import Rack, Rounding, next_row_up, round_to_rack
from coach.core.stall import stall_streak
from coach.core.top_backoff import back_off_load, top_set
from coach.core.warm_up import warm_up_loads
from coach.core.wave_531 import (
    TrainingMax,
    rep_out,
    rep_out_target,
    rep_outs_due,
    training_max,
    wave_index,
    wave_of,
    wave_sets,
)


def prescribe(request: PrescribeRequest) -> SessionPrescription:
    planned = request.planned
    lines = tuple(_Derivation(request, line).derive() for line in planned.lines)
    return SessionPrescription(planned, lines, _session_dose(request))


def _session_dose(request: PrescribeRequest) -> ConditioningDose | None:
    session = request.version.form.session(request.planned.session_id)
    if session is None or session.scheme is None:
        return None
    activity = request.activities.get(session.id)
    return conditioning_dose(session.scheme, activity)


type Found = AnchorExposure | StartLoad


@dataclass(frozen=True)
class _Move:
    """Step 1's result: the line's working groups with their loads."""

    derived_from: str | None
    working: tuple[PrescribedGroup, ...]
    change: str


@dataclass
class _Derivation:
    request: PrescribeRequest
    line: Line
    steps: list[Step] = field(default_factory=list[Step])
    flags: list[Flag] = field(default_factory=list[Flag])

    @property
    def scope(self) -> Scope:
        planned = self.request.planned
        return Scope(
            "line",
            week_monday(planned.date),
            session_id=planned.session_id,
            exercise_id=self.line.exercise,
        )

    @property
    def on(self) -> datetime.date:
        return self.request.planned.date

    def derive(self) -> LinePrescription:
        exercise = self.request.version.exercises[self.line.exercise]
        mode = cast(LoadMode, self.line.load_mode or exercise.load_mode)
        if not _convertible(exercise.load_mode, mode):
            self._raise(
                "load_mode_mismatch",
                {"exercise_load_mode": exercise.load_mode, "line_load_mode": mode},
                f"the line's load mode {mode} cannot be read from the exercise's "
                f"{exercise.load_mode}",
            )
            return self._prescription(_Move(None, self._uniform(None), "held"), None)
        rack = self._rack(exercise, mode)
        start = None if self.line.start_load is None else Load(self.line.start_load, mode)
        found = anchor(
            self.request.exposures,
            exercise_id=self.line.exercise,
            session_id=self.request.planned.session_id,
            on=self.on,
            start_load=start,
        )
        if isinstance(found, AnchorExposure) and self._scheme_name != "hold":
            self._stall(found.exposure)
        return self._prescription(self._scheme(found, rack, mode), rack)

    @property
    def _scheme_name(self) -> str:
        """A conditioning session's lines run `hold`, whatever scheme they name."""
        if self.request.planned.kind == "conditioning":
            return "hold"
        return self.line.scheme.name

    def _scheme(self, found: Found, rack: Rack | None, mode: LoadMode) -> _Move:
        match self._scheme_name:
            case "assistance_ladder":
                return self._ladder(found)
            case "top_backoff":
                return self._top_backoff(found, rack, mode)
            case "wave_531":
                return self._wave(found, rack, mode)
            case _:
                return self._load_step(found, rack, mode)

    def _load_step(self, found: Found, rack: Rack | None, mode: LoadMode) -> _Move:
        """One load for every working group: `double_progression`, `linear` and `hold`."""
        loaded = mode in LOAD_BEARING_MODES
        if isinstance(found, StartLoad):
            working = self._round(rack, self._opening(found, loaded), "hold")
            return _Move(found.derived_from, self._uniform(working), "first prescription")
        before = self._anchor_load(found.exposure, rack, mode) if loaded else None
        if self._scheme_name == "hold":
            rounded = self._round(rack, before, "hold")
            return _Move(found.derived_from, self._uniform(rounded), "held")
        if self._scheme_name == "linear" and before is not None:
            reset = self._reset(found.exposure, before, rack)
            if reset is not None:
                change = f"reset {_n(before)} → {_n(reset)}"
                return _Move(found.derived_from, self._uniform(reset), change)
        working = self._move(found.exposure, before, rack)
        rounded = self._round(rack, working, "step_up" if working != before else "hold")
        return _Move(found.derived_from, self._uniform(rounded), self._change(before, rounded))

    def _ladder(self, found: Found) -> _Move:
        ladder = rungs(self.line)
        if isinstance(found, StartLoad):
            first = Load(ladder[0], "assisted")
            return _Move(found.derived_from, self._uniform(first), "first prescription")
        logged = found.exposure.top_load
        if logged is None or logged.mode != "assisted":
            return _Move(found.derived_from, self._uniform(None), "held")
        rung = Load(rung_of(logged.amount, ladder), "assisted")
        if rung != logged:
            self._raise(
                "offgrid_anchor_ignored",
                {
                    "exposure": found.exposure.ref,
                    "logged_load": logged.amount,
                    "anchor_used": rung.amount,
                },
                f"the logged {logged.amount:g} is not a rung; the anchor uses {rung.amount:g}",
            )
        held = _Move(found.derived_from, self._uniform(rung), "held")
        if not self._judge(found.exposure, rung).hit:
            return held
        up = next_rung(rung.amount, ladder)
        if up is None:
            self.steps.append(Step("scheme", rung.amount, rung.amount, "last_rung"))
            return held
        self.steps.append(Step("scheme", rung.amount, up, "hit"))
        change = f"{_working(self.line)}: rung {_n(rung)} → {up:g}"
        return _Move(found.derived_from, self._uniform(Load(up, "assisted")), change)

    def _top_backoff(self, found: Found, rack: Rack | None, mode: LoadMode) -> _Move:
        if isinstance(found, StartLoad):
            top = self._round(rack, self._opening(found, loaded=True), "hold")
            return _Move(
                found.derived_from, self._top_then_backoffs(top, rack), "first prescription"
            )
        before = self._anchor_load(found.exposure, rack, mode)
        top = before
        estimate = e1rm(self.request.exposures, self.line.exercise, self.on)
        if estimate is None:
            self._raise(
                "no_e1rm",
                {"exercise_id": self.line.exercise, "scheme": self.line.scheme.name},
                f"no e1RM for {self.line.exercise} in the window, so the top set holds",
            )
        elif before is not None and rack is not None:
            moved = top_set(estimate.load.as_mode(mode), self.line, before, rack)
            self.steps.append(Step("scheme", before.amount, moved.load.amount, moved.cause))
            top = self._round(rack, moved.load, "hold")
        working = self._top_then_backoffs(top, rack)
        return _Move(found.derived_from, working, self._change(before, top))

    def _wave(self, found: Found, rack: Rack | None, mode: LoadMode) -> _Move:
        tm = training_max(self.request.decisions, self.line, mode)
        if tm is None:
            self._start_load_missing()
            return _Move(found.derived_from, self._uniform(None), "held")
        (group,) = self.line.working_groups()
        index = wave_index(self.request.hard_week_count)
        sets = wave_sets(tm.load, index, group.count, rack)
        loads = tuple(s.load.amount for s in sets)
        self.steps.append(Step("scheme", tm.load.amount, loads, f"wave_{index + 1}"))
        if isinstance(found, AnchorExposure):
            self._read_rep_outs(found.exposure, tm, group.count, rack)
        working = tuple(PrescribedGroup("working", 1, s.load, s.reps) for s in sets)
        change = f"wave {index + 1} of training max {_n(tm.load)}"
        return _Move(found.derived_from, working, change)

    def _read_rep_outs(
        self, exposure: Exposure, tm: TrainingMax, count: int, rack: Rack | None
    ) -> None:
        index = wave_of(exposure, tm.load, count, rack)
        if index is not None and rep_out(exposure) < rep_out_target(index):
            target = rep_out_target(index)
            self._raise(
                "rep_range_missed",
                {
                    "set_index": len(exposure.working),
                    "reps": rep_out(exposure),
                    "range": [target, target],
                    "logged_rpe": exposure.working[-1].rpe,
                    "authored_rpe": None,
                },
                f"the rep-out logged {rep_out(exposure)} reps, short of wave {index + 1}'s "
                f"{target}",
            )
        history = ordinary(line_history(self.request.exposures, exposure, on=self.on))
        rep_outs = rep_outs_due(history, tm.load, count, rack)
        if rep_outs is not None:
            self._raise(
                "training_max_due",
                {"training_max": tm.load.amount, "source": tm.source, "rep_outs": list(rep_outs)},
                f"all three waves logged at training max {_n(tm.load)}: rep-outs "
                f"{', '.join(map(str, rep_outs))}",
            )

    def _top_then_backoffs(
        self, top: Load | None, rack: Rack | None
    ) -> tuple[PrescribedGroup, ...]:
        first, *rest = self.line.working_groups()
        back_off = None if top is None else back_off_load(top, self.line, rack)
        return (_group(first, top), *(_group(group, back_off) for group in rest))

    def _uniform(self, load: Load | None) -> tuple[PrescribedGroup, ...]:
        return tuple(_group(group, load) for group in self.line.working_groups())

    def _change(self, before: Load | None, after: Load | None) -> str:
        if before is None or after is None or before == after:
            return "held"
        return f"{_working(self.line)}: {_n(before)} → {_n(after)}"

    def _reset(self, exposure: Exposure, before: Load, rack: Rack | None) -> Load | None:
        history = ordinary(line_history(self.request.exposures, exposure, on=self.on))
        misses = misses_at(self.line, history, before, rack)
        if misses < misses_before_reset(self.line):
            return None
        reset = reset_load(self.line, before, rack)
        self.steps.append(Step("scheme", before.amount, reset.amount, f"reset, misses {misses}"))
        return self._round(rack, reset, "cut")

    def _stall(self, anchor_exposure: Exposure) -> None:
        history = ordinary(line_history(self.request.exposures, anchor_exposure, on=self.on))
        streak = stall_streak(self.line, history)
        if streak:
            self._raise(
                "stall_streak",
                {"streak": len(streak), "exposures": [e.ref for e in streak]},
                f"{len(streak)} exposures in a row with no gain on the "
                f"{self.line.scheme.name} metric",
            )

    def _rack(self, exercise: ExerciseFacts, mode: LoadMode) -> Rack | None:
        if mode not in RACK_MODES:
            return None
        racks = self.request.racks.get(self.request.planned.location, {})
        return racks.get(exercise.equipment_kind)

    def _opening(self, found: StartLoad, loaded: bool) -> Load | None:
        """No exposure anywhere: the start load at the scheme's opening position."""
        if not loaded:
            return None
        if found.load is None:
            self._start_load_missing()
            return None
        self.steps.append(Step("scheme", None, found.load.amount, "start_load"))
        return found.load

    def _start_load_missing(self) -> None:
        self._raise(
            "start_load_missing",
            {"exercise_id": self.line.exercise},
            f"{self.line.exercise} has no Exposure yet and the line has no start_load",
        )

    def _anchor_load(self, exposure: Exposure, rack: Rack | None, mode: LoadMode) -> Load | None:
        if rack is None:
            top = exposure.top_load
            return None if top is None else top.as_mode(mode)
        load, offgrid = anchor_load(
            exposure,
            rack,
            session_id=self.request.planned.session_id,
            monday=self.scope.monday,
            mode=mode,
        )
        if offgrid is not None:
            self.flags.append(offgrid)
        return load

    def _move(self, exposure: Exposure, before: Load | None, rack: Rack | None) -> Load | None:
        verdict = self._judge(exposure, before)
        if not verdict.hit or before is None or rack is None:
            return before
        moved = next_row_up(rack, before)
        cause = "hit" if moved.cause == "row" else "rack_top"
        self.steps.append(Step("scheme", before.amount, moved.load.amount, cause))
        return moved.load

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

    def _round(self, rack: Rack | None, load: Load | None, rounding: Rounding) -> Load | None:
        if rack is None or load is None:
            return load
        rounded = round_to_rack(rack, load, rounding)
        self.steps.append(Step("rack", load.amount, rounded.load.amount, rounded.cause))
        return rounded.load

    def _prescription(self, move: _Move, rack: Rack | None) -> LinePrescription:
        return LinePrescription(
            exercise_id=self.line.exercise,
            scheme=self.line.scheme.name,
            groups=self._groups(move.working, rack),
            derived_from=move.derived_from,
            steps=tuple(self.steps),
            flags=tuple(self.flags),
            change=move.change,
        )

    def _groups(
        self, working: tuple[PrescribedGroup, ...], rack: Rack | None
    ) -> tuple[PrescribedGroup, ...]:
        """The authored groups in order, the scheme's working groups standing in for the
        authored ones, the warm-ups ramped off the first working load."""
        count = sum(group.count for group in self.line.sets if group.type == "warm_up")
        first = working[0].load if working else None
        warm_ups: list[Load | None] = [None] * count
        if first is not None and count:
            targets, loads = warm_up_loads(first, count, rack)
            self.steps.append(
                Step("warm_up", targets, tuple(load.amount for load in loads), "ladder")
            )
            warm_ups = list(loads)
        groups: list[PrescribedGroup] = []
        placed = False
        for group in self.line.sets:
            if group.type == "warm_up":
                groups.extend(_group(group, warm_ups.pop(0), count=1) for _ in range(group.count))
            elif not group.working:
                groups.append(_group(group, None))
            elif not placed:
                groups.extend(working)
                placed = True
        return tuple(groups)

    def _raise(self, code: str, params: dict[str, object], message: str) -> None:
        self.flags.append(raise_flag(code, self.scope, params, message))


def _convertible(exercise_mode: LoadMode, line_mode: LoadMode) -> bool:
    """The Load type converts between the rack modes through the total; nothing else converts."""
    return exercise_mode == line_mode or {exercise_mode, line_mode} <= set(RACK_MODES)


def _group(group: SetGroup, load: Load | None, *, count: int | None = None) -> PrescribedGroup:
    return PrescribedGroup(
        group.type,
        group.count if count is None else count,
        load,
        group.reps,
        group.duration_s,
        group.rpe,
    )


def _working(line: Line) -> str:
    """The working groups as `4×6–8 @8`."""
    return " + ".join(_describe(group) for group in line.working_groups())


def _describe(group: SetGroup) -> str:
    reps = group.reps
    if isinstance(reps, tuple):
        dose = f"{reps[0]}–{reps[1]}"
    elif reps is not None:
        dose = str(reps)
    else:
        dose = f"{group.duration_s} s"
    rpe = "" if group.rpe is None else f" @{group.rpe:g}"
    return f"{group.count}×{dose}{rpe}"


def _n(load: Load | None) -> str:
    assert load is not None
    return f"{load.amount:g}"
