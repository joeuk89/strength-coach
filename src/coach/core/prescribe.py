"""The derivation pipeline (ADR 0017, docs/spec/prescription.md, "The pipeline"): the scheme's
move from the anchor exposure, rack rounding, then the warm-ups. Each step that changed a load is
recorded as `(step, from, to, cause)`."""

import datetime
from dataclasses import dataclass, field
from typing import cast

from coach.core.anchor import StartLoad, anchor, anchor_load
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.load import Load, LoadMode
from coach.core.prescription import (
    ExerciseFacts,
    LinePrescription,
    PrescribedGroup,
    PrescribeRequest,
    SessionPrescription,
    Step,
)
from coach.core.program.form import LOAD_BEARING_MODES, RACK_MODES, Line, SetGroup
from coach.core.progression import judge
from coach.core.rack import Rack, Rounding, next_row_up, round_to_rack
from coach.core.warm_up import warm_up_loads


def prescribe(request: PrescribeRequest) -> SessionPrescription:
    planned = request.planned
    return SessionPrescription(
        planned, tuple(_Derivation(request, line).derive() for line in planned.lines)
    )


@dataclass
class _Derivation:
    request: PrescribeRequest
    line: Line
    steps: list[Step] = field(default_factory=list[Step])
    flags: list[Flag] = field(default_factory=list[Flag])

    @property
    def scope(self) -> Scope:
        planned = self.request.planned
        monday = planned.date - datetime.timedelta(days=planned.date.weekday())
        return Scope("line", monday, session_id=planned.session_id, exercise_id=self.line.exercise)

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
            return self._prescription(None, None, None, "held")
        rack = self._rack(exercise, mode)
        start = None if self.line.start_load is None else Load(self.line.start_load, mode)
        found = anchor(
            self.request.exposures,
            exercise_id=self.line.exercise,
            session_id=self.request.planned.session_id,
            on=self.request.planned.date,
            start_load=start,
        )
        loaded = mode in LOAD_BEARING_MODES
        if isinstance(found, StartLoad):
            working = self._round(rack, self._opening(found, loaded), "hold")
            return self._prescription(found.derived_from, rack, working, "first prescription")
        before = self._anchor_load(found.exposure, rack, mode) if loaded else None
        working = self._move(found.exposure, before, rack)
        rounded = self._round(rack, working, "step_up" if working != before else "hold")
        changed = before is not None and rounded is not None and rounded != before
        change = f"{_working(self.line)}: {_n(before)} → {_n(rounded)}" if changed else "held"
        return self._prescription(found.derived_from, rack, rounded, change)

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
            self._raise(
                "start_load_missing",
                {"exercise_id": self.line.exercise},
                f"{self.line.exercise} has no Exposure yet and the line has no start_load",
            )
            return None
        self.steps.append(Step("scheme", None, found.load.amount, "start_load"))
        return found.load

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
        verdict = judge(self.line, exposure)
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
        if not verdict.hit or before is None or rack is None:
            return before
        moved = next_row_up(rack, before)
        cause = "hit" if moved.cause == "row" else "rack_top"
        self.steps.append(Step("scheme", before.amount, moved.load.amount, cause))
        return moved.load

    def _round(self, rack: Rack | None, load: Load | None, rounding: Rounding) -> Load | None:
        if rack is None or load is None:
            return load
        rounded = round_to_rack(rack, load, rounding)
        self.steps.append(Step("rack", load.amount, rounded.load.amount, rounded.cause))
        return rounded.load

    def _prescription(
        self, derived_from: str | None, rack: Rack | None, working: Load | None, change: str
    ) -> LinePrescription:
        return LinePrescription(
            exercise_id=self.line.exercise,
            scheme=self.line.scheme.name,
            groups=self._groups(rack, working),
            derived_from=derived_from,
            steps=tuple(self.steps),
            flags=tuple(self.flags),
            change=change,
        )

    def _groups(self, rack: Rack | None, working: Load | None) -> tuple[PrescribedGroup, ...]:
        count = sum(group.count for group in self.line.sets if group.type == "warm_up")
        warm_ups: list[Load | None] = [None] * count
        if working is not None and count:
            targets, loads = warm_up_loads(working, count, rack)
            self.steps.append(
                Step("warm_up", targets, tuple(load.amount for load in loads), "ladder")
            )
            warm_ups = list(loads)
        groups: list[PrescribedGroup] = []
        for group in self.line.sets:
            if group.type == "warm_up":
                groups.extend(_group(group, warm_ups.pop(0), count=1) for _ in range(group.count))
            else:
                groups.append(_group(group, working if group.working else None))
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
