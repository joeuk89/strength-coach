"""The derivation pipeline (ADR 0017, docs/spec/prescription.md, "The pipeline"): the scheme's
move from the anchor exposure, the cut, the ceilings and the rack (`bounds`), then the warm-ups.
Each step that changed something is recorded as `(step, from, to, cause)`."""

from dataclasses import dataclass, field, replace
from typing import cast

from coach.core.anchor import StartLoad, anchor, anchor_load
from coach.core.bounds import TEST_RPE, Bounded, LineContext, bound
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.load import Load, LoadMode
from coach.core.planned_week import week_monday
from coach.core.prescription import (
    ExerciseFacts,
    LinePrescription,
    PrescribedGroup,
    PrescribeRequest,
    SessionPrescription,
    Step,
)
from coach.core.program.form import LOAD_BEARING_MODES, RACK_MODES, Line, Number, SetGroup
from coach.core.progression import judge
from coach.core.rack import Rack, next_row_up
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
        return Scope(
            "line",
            week_monday(planned.date),
            session_id=planned.session_id,
            exercise_id=self.line.exercise,
        )

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
            unloaded = Bounded(self.line.sets, None)
            return self._prescription(None, self._groups(None, unloaded), "held")
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
        context = LineContext(self.request, self.line, exercise, mode, rack, self.scope)
        if isinstance(found, StartLoad):
            opening = self._opening(found, loaded)
            bounded = bound(context, opening, "hold", self.steps, self.flags)
            return self._bounded(found.derived_from, rack, bounded, "first prescription")
        before = self._anchor_load(found.exposure, rack, mode) if loaded else None
        moved = self._move(found.exposure, before, rack)
        context = replace(context, anchor=found.exposure, anchor_top=before)
        rounding = "step_up" if moved != before else "hold"
        bounded = bound(context, moved, rounding, self.steps, self.flags)
        return self._bounded(found.derived_from, rack, bounded, _change(self.line, before, bounded))

    def _bounded(
        self, derived_from: str, rack: Rack | None, bounded: Bounded, change: str
    ) -> LinePrescription:
        if bounded.dropped:
            return self._prescription(derived_from, (), "dropped")
        return self._prescription(derived_from, self._groups(rack, bounded), change)

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
        verdict = judge(self.line, exposure, before)
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

    def _prescription(
        self, derived_from: str | None, groups: tuple[PrescribedGroup, ...], change: str
    ) -> LinePrescription:
        return LinePrescription(
            exercise_id=self.line.exercise,
            scheme=self.line.scheme.name,
            groups=groups,
            derived_from=derived_from,
            steps=tuple(self.steps),
            flags=tuple(self.flags),
            change=change,
        )

    def _groups(self, rack: Rack | None, bounded: Bounded) -> tuple[PrescribedGroup, ...]:
        working = bounded.load
        count = sum(group.count for group in bounded.sets if group.type == "warm_up")
        warm_ups: list[Load | None] = [None] * count
        if working is not None and count:
            targets, loads = warm_up_loads(working, count, rack)
            self.steps.append(
                Step("warm_up", targets, tuple(load.amount for load in loads), "ladder")
            )
            warm_ups = list(loads)
        groups: list[PrescribedGroup] = []
        test = bounded.test
        for group in bounded.sets:
            if group.type == "warm_up":
                groups.extend(_group(group, warm_ups.pop(0), count=1) for _ in range(group.count))
                continue
            if group.working and test is not None:
                groups.append(PrescribedGroup("test", 1, test, 1, None, TEST_RPE))
                test = None
            cap = bounded.rpe_cap if group.working else None
            groups.append(_group(group, working if group.working else None, rpe_cap=cap))
        return tuple(groups)

    def _raise(self, code: str, params: dict[str, object], message: str) -> None:
        self.flags.append(raise_flag(code, self.scope, params, message))


def _convertible(exercise_mode: LoadMode, line_mode: LoadMode) -> bool:
    """The Load type converts between the rack modes through the total; nothing else converts."""
    return exercise_mode == line_mode or {exercise_mode, line_mode} <= set(RACK_MODES)


def _group(
    group: SetGroup,
    load: Load | None,
    *,
    count: int | None = None,
    rpe_cap: Number | None = None,
) -> PrescribedGroup:
    return PrescribedGroup(
        group.type,
        group.count if count is None else count,
        load,
        group.reps,
        group.duration_s,
        group.rpe,
        rpe_cap,
    )


def _change(line: Line, before: Load | None, bounded: Bounded) -> str:
    """`4×6–8 @8: 120 → 125`; with the shape changed, `4×8 @8 rung 40 → 3×8 @≤8 rung 60`."""
    after = bounded.load
    authored = _shape(line.sets, None)
    shaped = _shape(bounded.sets, bounded.rpe_cap)
    if shaped == authored:
        if before is None or after is None or after == before:
            return "held"
        return f"{authored}: {before.amount:g} → {after.amount:g}"
    if before is None or after is None:
        return f"{authored} → {shaped}"
    sep = " rung " if line.scheme.name == "assistance_ladder" else ": "
    return f"{authored}{sep}{before.amount:g} → {shaped}{sep}{after.amount:g}"


def _shape(sets: tuple[SetGroup, ...], rpe_cap: Number | None) -> str:
    """The working groups as `4×6–8 @8`, a capped RPE as `@≤8`."""
    return " + ".join(_describe(group, rpe_cap) for group in sets if group.working)


def _describe(group: SetGroup, rpe_cap: Number | None) -> str:
    reps = group.reps
    if isinstance(reps, tuple):
        dose = f"{reps[0]}–{reps[1]}"
    elif reps is not None:
        dose = str(reps)
    else:
        dose = f"{group.duration_s} s"
    if rpe_cap is not None:
        rpe = f" @≤{rpe_cap:g}"
    else:
        rpe = "" if group.rpe is None else f" @{group.rpe:g}"
    return f"{group.count}×{dose}{rpe}"
