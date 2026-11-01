"""The derivation pipeline (ADR 0017, docs/spec/prescription.md, "The pipeline"): the scheme's
move from the anchor exposure, the plan's line overrides and the override Decisions in force,
the cut, the ceilings and the rack (`bounds`), then the warm-ups. Each step that changed
something is recorded as `(step, from, to, cause)`."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import cast

from coach.core.anchor import StartLoad, anchor
from coach.core.bounds import TEST_RPE, Bounded, LineContext, Proposal, bound
from coach.core.conditioning import conditioning_dose
from coach.core.cut import close_rep_outs
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.load import Load, LoadMode
from coach.core.overrides import line_override
from coach.core.planned_week import week_monday
from coach.core.prescription import (
    ConditioningDose,
    ExerciseFacts,
    LinePrescription,
    PlanOverride,
    PrescribedGroup,
    PrescribeRequest,
    SessionPrescription,
    Step,
)
from coach.core.program.form import (
    LOAD_BEARING_MODES,
    RACK_MODES,
    Line,
    Number,
    Reps,
    SchemeRef,
    SetGroup,
)
from coach.core.rack import Rack, next_row_up
from coach.core.scheme_moves import Move, SchemeInput, SchemeMoves
from coach.core.top_backoff import back_off_load
from coach.core.warm_up import warm_up_loads


def prescribe(request: PrescribeRequest) -> SessionPrescription:
    planned = request.planned
    lines = planned.lines
    if planned.kind == "conditioning":
        lines = tuple(replace(line, scheme=SchemeRef("hold", {})) for line in lines)
    derived = (_Derivation(request, line).derive() for line in lines)
    kept = tuple(line for line in derived if line is not None)
    return SessionPrescription(planned, kept, _session_dose(request))


def _session_dose(request: PrescribeRequest) -> ConditioningDose | None:
    session = request.version.form.session(request.planned.session_id)
    if session is None or session.scheme is None:
        return None
    return conditioning_dose(session.scheme, request.activities.get(session.id))


type Applied = tuple[str, PlanOverride]


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

    def derive(self) -> LinePrescription | None:
        overrides = self._overrides()
        if "drop_line" in overrides:
            return None
        authored = self.line
        if "swap_exercise" in overrides:
            authored = self._swap(*overrides["swap_exercise"])
        exercise = self.request.version.exercises.get(authored.exercise)
        if exercise is None:
            self._raise(
                "unknown_exercise",
                {"exercise_id": authored.exercise},
                f"{authored.exercise} is not in the library",
            )
            unknown = Bounded(authored.sets, None)
            return self._prescription(authored, None, self._groups(authored, None, unknown), "held")
        sets = authored.sets
        if "restate_sets" in overrides:
            sets = self._restate(authored, *overrides["restate_sets"])
        mode = cast(LoadMode, authored.load_mode or exercise.load_mode)
        if not _convertible(exercise.load_mode, mode):
            self._raise(
                "load_mode_mismatch",
                {"exercise_load_mode": exercise.load_mode, "line_load_mode": mode},
                f"the line's load mode {mode} cannot be read from the exercise's "
                f"{exercise.load_mode}",
            )
            unloaded = Bounded(sets, None)
            return self._prescription(
                authored, None, self._groups(authored, None, unloaded), "held"
            )
        rack = self._rack(exercise, mode)
        start = None if authored.start_load is None else Load(authored.start_load, mode)
        found = anchor(
            self.request.exposures,
            exercise_id=authored.exercise,
            session_id=self.request.planned.session_id,
            on=self.request.planned.date,
            start_load=start,
        )
        line = replace(authored, sets=sets)
        schemes = SchemeMoves(
            SchemeInput(self.request, authored, sets, mode, rack, self.scope),
            self.steps,
            self.flags,
        )
        pin = overrides.get("pin_load")
        if isinstance(found, StartLoad):
            pinned_only = pin is not None and found.load is None and line.scheme.name != "wave_531"
            move = Move(None, "hold", line.sets) if pinned_only else schemes.opening(found)
            line = replace(line, sets=move.sets)
            context = LineContext(self.request, line, exercise, mode, rack, self.scope)
            opening = _first(move.proposal)
            loaded = mode in LOAD_BEARING_MODES
            pinned = self._pin(opening, mode, *pin) if pin is not None and loaded else None
            context = replace(context, scheme_load=opening, pin=pinned)
            proposal = move.proposal if pinned is None else _pinned(move.proposal, pinned)
            bounded = bound(context, proposal, move.rounding, self.steps, self.flags)
            change = "first prescription"
            return self._bounded(line, found.derived_from, rack, bounded, change)
        before = schemes.anchor_top(found.exposure)
        move = self._move_or_hold(schemes, found.exposure, before, overrides)
        schemes.stall(found.exposure)
        line = replace(line, sets=move.sets)
        moved = _first(move.proposal)
        pinned = None if pin is None or moved is None else self._pin(moved, moved.mode, *pin)
        context = LineContext(
            self.request,
            line,
            exercise,
            mode,
            rack,
            self.scope,
            anchor=found.exposure,
            anchor_top=before,
            scheme_load=moved,
            pin=pinned,
        )
        if pinned is not None:
            bounded = bound(context, _pinned(move.proposal, pinned), "hold", self.steps, self.flags)
        else:
            bounded = bound(context, move.proposal, move.rounding, self.steps, self.flags)
        if pin is not None:
            self._check_increment(found.exposure, rack, before, bounded.load)
        change = _change(line, before, bounded, move.change, moved)
        return self._bounded(line, found.derived_from, rack, bounded, change)

    def _bounded(
        self, line: Line, derived_from: str, rack: Rack | None, bounded: Bounded, change: str
    ) -> LinePrescription:
        if bounded.dropped:
            return self._prescription(line, derived_from, (), "dropped")
        return self._prescription(line, derived_from, self._groups(line, rack, bounded), change)

    def _move_or_hold(
        self,
        schemes: SchemeMoves,
        exposure: Exposure,
        before: Load | None,
        overrides: Mapping[str, Applied],
    ) -> Move:
        if "hold" not in overrides:
            return schemes.move(exposure, before)
        step, _ = overrides["hold"]
        self.steps.append(Step(step, None, _amount(before), "hold"))
        return Move(before, "hold", schemes.given.sets)

    def _overrides(self) -> dict[str, Applied]:
        """The line's override Decisions in force, then the plan's own: the plan wins on the same
        kind (docs/spec/overrides.md, "Precedence and conflicts")."""
        session_id = self.request.planned.session_id
        found: dict[str, Applied] = {}
        for decision in self.request.decisions:
            if (decision.kind, decision.session_id, decision.exercise_id) == (
                "override",
                session_id,
                self.line.exercise,
            ):
                params = cast(Mapping[str, object], decision.params["override"])
                override = line_override(params, where=f"decision {decision.id}")
                found[override.kind] = ("decision", override)
        for override in self.request.overrides:
            if (override.session_id, override.exercise_id) == (session_id, self.line.exercise):
                found[override.kind] = ("override", override)
        return found

    def _swap(self, step: str, swap: PlanOverride) -> Line:
        """The other exercise under the line's scheme and sets, with the swap's own start load
        and load mode: nothing of the swapped-out exercise carries."""
        to = str(swap.params["to"])
        self.steps.append(Step(step, self.line.exercise, to, "swap_exercise"))
        start = cast(float | None, swap.params.get("start_load"))
        return replace(
            self.line,
            exercise=to,
            load_mode=cast(str | None, swap.params.get("load_mode")),
            start_load=start,
        )

    def _restate(self, authored: Line, step: str, restate: PlanOverride) -> tuple[SetGroup, ...]:
        sets = cast(tuple[SetGroup, ...], restate.params["sets"])
        before = sum(group.count for group in authored.working_groups())
        after = sum(group.count for group in sets if group.working)
        self.steps.append(Step(step, before, after, "restate_sets"))
        return sets

    def _pin(self, working: Load | None, mode: LoadMode, step: str, pin: PlanOverride) -> Load:
        pinned = Load(cast(float, pin.params["load"]), mode)
        self.steps.append(Step(step, _amount(working), pinned.amount, "pin_load"))
        return pinned

    def _check_increment(
        self, exposure: Exposure, rack: Rack | None, before: Load | None, pinned: Load | None
    ) -> None:
        """Every scheme steps at most one rack row, so only a pin can step further."""
        if rack is None or before is None or pinned is None:
            return
        one_row = next_row_up(rack, before).load
        if pinned.amount <= one_row.amount:
            return
        self._raise(
            "increment_over_step",
            {
                "increment": pinned.amount - before.amount,
                "scheme_step": one_row.amount - before.amount,
                "from_exposure": exposure.ref,
            },
            f"the pinned {pinned.amount:g} is more than one rack row above the anchor's "
            f"{before.amount:g}",
        )

    def _rack(self, exercise: ExerciseFacts, mode: LoadMode) -> Rack | None:
        if mode not in RACK_MODES:
            return None
        racks = self.request.racks.get(self.request.planned.location, {})
        return racks.get(exercise.equipment_kind)

    def _prescription(
        self,
        authored: Line,
        derived_from: str | None,
        groups: tuple[PrescribedGroup, ...],
        change: str,
    ) -> LinePrescription:
        return LinePrescription(
            exercise_id=authored.exercise,
            scheme=authored.scheme.name,
            groups=groups,
            derived_from=derived_from,
            steps=tuple(self.steps),
            flags=tuple(self.flags),
            change=change,
        )

    def _groups(
        self, line: Line, rack: Rack | None, bounded: Bounded
    ) -> tuple[PrescribedGroup, ...]:
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
        top = True
        for group in bounded.sets:
            if group.type == "warm_up":
                groups.extend(_group(group, warm_ups.pop(0), count=1) for _ in range(group.count))
                continue
            if group.working and test is not None:
                groups.append(PrescribedGroup("test", 1, test, 1, None, TEST_RPE))
                test = None
            if not group.working:
                groups.append(_group(group, None))
                continue
            if bounded.set_loads:
                groups.extend(_per_set(group, bounded))
                continue
            load = working if top else self._back_off(line, rack, working)
            top = False
            groups.append(_group(group, load, rpe_cap=bounded.rpe_cap))
        return tuple(groups)

    def _back_off(self, line: Line, rack: Rack | None, top: Load | None) -> Load | None:
        """Under `top_backoff` every working group after the first follows the bounded top."""
        if top is None or line.scheme.name != "top_backoff":
            return top
        return back_off_load(top, line, rack)

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
    reps: Reps | None = None,
) -> PrescribedGroup:
    return PrescribedGroup(
        group.type,
        group.count if count is None else count,
        load,
        group.reps if reps is None else reps,
        group.duration_s,
        group.rpe,
        rpe_cap,
    )


def _per_set(group: SetGroup, bounded: Bounded) -> tuple[PrescribedGroup, ...]:
    """The group as one set per load; every set but the last at the closed reps."""
    last = len(bounded.set_loads) - 1
    closed = close_rep_outs((group,))[0].reps
    return tuple(
        _group(
            group, load, count=1, rpe_cap=bounded.rpe_cap, reps=group.reps if i == last else closed
        )
        for i, load in enumerate(bounded.set_loads)
    )


def _change(
    line: Line, before: Load | None, bounded: Bounded, named: str | None, proposed: Load | None
) -> str:
    """`4×6–8 @8: 120 → 125`; with the shape changed, `4×8 @8 rung 40 → 3×8 @≤8 rung 60`; the
    scheme's own change (`reset 120 → 107.5`) when the later steps left its load and shape alone."""
    after = bounded.load
    authored = _shape(line.sets, None)
    shaped = _shape(bounded.sets, bounded.rpe_cap)
    if shaped == authored and named is not None and after == proposed:
        return named
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


def _first(proposal: Proposal) -> Load | None:
    if isinstance(proposal, tuple):
        return proposal[0] if proposal else None
    return proposal


def _pinned(proposal: Proposal, pinned: Load) -> Proposal:
    """A pin keeps a per-set proposal per set, so only the last set stays open."""
    if isinstance(proposal, tuple):
        return tuple(pinned for _ in proposal)
    return pinned


def _amount(load: Load | None) -> float | None:
    return None if load is None else load.amount
