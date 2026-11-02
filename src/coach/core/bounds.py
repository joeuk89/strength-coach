"""Steps 4 to 7 of the pipeline on the load step 1 proposed: the one cut, the niggle
constraints, the RPE ceilings, the safety ceiling and the rack (ADR 0017, docs/spec/
prescription.md, "The pipeline"). No step raises a load an earlier step lowered."""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import cast

from coach.core.ceilings import (
    ILLNESS_RPE_CAP,
    constraints_on,
    easier,
    fewest_reps,
    harder,
    ill_since,
    niggle_load_caps,
    reps_within_model,
    safety_ceiling,
)
from coach.core.cut import (
    Band,
    close_rep_outs,
    cut_each_working_group,
    light_shape,
    one_working_set_fewer,
    return_band,
    rungs_back,
    working_set_count,
)
from coach.core.days_off import line_days_off
from coach.core.e1rm import E1rm, model_load
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.load import Load, LoadMode
from coach.core.prescription import (
    ExerciseFacts,
    NiggleConstraint,
    PlanOverride,
    PrescribeRequest,
    Step,
    StepValue,
)
from coach.core.program.form import Line, Number, SetGroup
from coach.core.rack import Rack, Rounding, on_rack, round_to_rack, rows_beside

TEST_SCHEMES = ("top_backoff", "wave_531")
TEST_RPE = 9

type Proposal = Load | tuple[Load, ...] | None


@dataclass(frozen=True)
class LineContext:
    request: PrescribeRequest
    line: Line
    exercise: ExerciseFacts
    mode: LoadMode
    rack: Rack | None
    scope: Scope
    anchor: Exposure | None = None
    anchor_top: Load | None = None
    scheme_load: Load | None = None
    pin: Load | None = None
    e1rm: E1rm | None = None


@dataclass(frozen=True)
class Bounded:
    """`load` is the first working set's; `set_loads` holds one load per working set when the
    line carries a load per set."""

    sets: tuple[SetGroup, ...]
    load: Load | None
    rpe_cap: Number | None = None
    test: Load | None = None
    dropped: bool = False
    set_loads: tuple[Load, ...] = ()


def bound(
    context: LineContext,
    proposal: Proposal,
    rounding: Rounding,
    steps: list[Step],
    flags: list[Flag],
) -> Bounded:
    """One load for every working set, or a tuple of one load per working set of a line whose
    single working group carries a load per set (`wave_531`). Every step maps over the loads.
    `steps` and `flags` are the line's, appended to in pipeline order."""
    per_set = isinstance(proposal, tuple)
    loads = proposal if isinstance(proposal, tuple) else () if proposal is None else (proposal,)
    sets = context.line.sets
    return _Bounding(context, loads, per_set, rounding, steps, flags, sets).run()


@dataclass
class _Bounding:
    context: LineContext
    loads: tuple[Load, ...]
    per_set: bool
    rounding: Rounding
    steps: list[Step]
    flags: list[Flag]
    sets: tuple[SetGroup, ...]
    rpe_caps: list[tuple[Number, str]] = field(default_factory=list[tuple[Number, str]])
    load_ceilings: list[Load] = field(default_factory=list[Load])
    unchecked_cap: Number | None = None

    def run(self) -> Bounded:
        self._cut()
        constraints = constraints_on(
            self.context.request.niggle_constraints,
            self.context.line.exercise,
            self.context.exercise.pattern,
        )
        avoided = next((c for c in constraints if c.kind == "avoid"), None)
        if avoided is not None:
            self.steps.append(Step("niggle", None, None, f"avoid niggle:{avoided.niggle_id}"))
            return Bounded((), None, dropped=True)
        self._niggle_loads(constraints)
        cap = self._rpe_ceiling(constraints)
        self._rack()
        self._unchecked()
        first = self.loads[0] if self.loads else None
        set_loads = self.loads if self.per_set else ()
        return Bounded(self.sets, first, cap, self._test(), set_loads=set_loads)

    @property
    def load(self) -> Load | None:
        """The single load of a line that carries one."""
        return self.loads[0] if self.loads and not self.per_set else None

    def _cut(self) -> None:
        request = self.context.request
        days = line_days_off(
            request.exposures,
            request.trained,
            exercise_id=self.context.line.exercise,
            session_id=request.planned.session_id,
            on=request.planned.date,
        )
        band = return_band(days.days)
        if band is not None:
            self._return_band(band, days.days)
            return
        light_week = self._override("light_week")
        if light_week is not None:
            self._light_cut(light_week)

    def _return_band(self, band: Band, days: int) -> None:
        cause = f"return {band.label}, {days} days off"
        if self.per_set:
            self._lower("cut", tuple(self._band_load(band, load) for load in self.loads), cause)
        else:
            self._return_band_load(band, days, cause)
        self._set_count(one_working_set_fewer(self.sets))
        if self.context.line.scheme.name == "wave_531":
            self.sets = close_rep_outs(self.sets)
        self.rpe_caps.append((band.rpe_cap, "return_band"))

    def _return_band_load(self, band: Band, days: int, cause: str) -> None:
        base = self.context.scheme_load
        if base is not None and self.context.anchor_top is not None:
            base = easier(base, self.context.anchor_top)
        if base is not None:
            target = self._band_load(band, base)
            pin = self._pin()
            if pin is not None and not harder(pin, target):
                target = pin
            if target != self.load:
                self._lower("cut", (target,), cause)
            if pin is not None and harder(pin, target):
                self._raise(
                    "return_band_disagrees",
                    {
                        "days_off": days,
                        "band": band.label,
                        "load": target.amount,
                        "set_delta": -band.set_delta,
                        "rpe_cap": band.rpe_cap,
                    },
                    f"the pinned {pin.amount:g} is over the return band's {target.amount:g}; "
                    "no override waives the band",
                )

    def _band_load(self, band: Band, base: Load) -> Load:
        if self.context.line.scheme.name == "assistance_ladder":
            rungs = cast(Sequence[float], self.context.line.scheme.params.get("rungs", ()))
            if rungs:
                return rungs_back(rungs, base, band.rungs_back)
        if base.mode == "assisted":
            return base
        return replace(base, amount=round(base.amount * band.load_factor, 4))

    def _light_cut(self, light_week: PlanOverride) -> None:
        shape = light_shape(self.context.request.version.form.deload, light_week.params)
        if self.loads and shape.load_cut_pct and self.loads[0].mode != "assisted":
            factor = 1 - shape.load_cut_pct / 100
            cut = tuple(replace(load, amount=round(load.amount * factor, 4)) for load in self.loads)
            self._lower("cut", cut, "light")
        self._set_count(cut_each_working_group(self.sets, shape.set_cut_pct))
        self.sets = close_rep_outs(self.sets)
        if shape.rpe_cap is not None:
            self.rpe_caps.append((shape.rpe_cap, "light_week"))

    def _set_count(self, cut: tuple[SetGroup, ...]) -> None:
        before, after = working_set_count(self.sets), working_set_count(cut)
        if after != before:
            self.steps.append(Step("cut", before, after, "sets"))
        self.sets = cut
        if self.per_set:
            self.loads = self.loads[:after]

    def _niggle_loads(self, constraints: tuple[NiggleConstraint, ...]) -> None:
        caps = niggle_load_caps(
            constraints, mode=self.context.mode, anchor_top=self.context.anchor_top
        )
        if not caps:
            return
        strictest, by = caps[0]
        for cap, constraint in caps[1:]:
            if harder(strictest, cap):
                strictest, by = cap, constraint
        self.load_ceilings.append(strictest)
        pin = self._pin()
        if pin is not None and harder(pin, strictest):
            self._raise(
                "recovery_ceiling_exceeded",
                {
                    "ceiling_kind": "niggle",
                    "ceiling": strictest.amount,
                    "prescribed": pin.amount,
                    "ref": f"niggle:{by.niggle_id}",
                },
                f"the pinned {pin.amount:g} is over niggle {by.niggle_id}'s "
                f"{by.kind} of {strictest.amount:g}",
            )
        if not self.loads:
            return
        if not self._limit("niggle", strictest, f"{by.kind} niggle:{by.niggle_id}"):
            self.steps.append(Step("niggle", strictest.amount, self._amounts(), "not_binding"))

    def _rpe_ceiling(self, constraints: tuple[NiggleConstraint, ...]) -> Number | None:
        self.rpe_caps += [
            (c.value, f"niggle:{c.niggle_id}")
            for c in constraints
            if c.kind == "rpe_cap" and c.value is not None
        ]
        request = self.context.request
        anchor = self.context.anchor
        if anchor is not None and ill_since(
            request.status_spans,
            request.exposures,
            exercise_id=self.context.line.exercise,
            anchor_date=anchor.date,
            on=request.planned.date,
        ):
            self.rpe_caps.append((ILLNESS_RPE_CAP, "illness"))
        if not self.rpe_caps:
            return None
        cap, cause = min(self.rpe_caps, key=lambda c: c[0])
        authored = [g.rpe for g in self.sets if g.working and g.rpe is not None]
        self.steps.append(Step("rpe_ceiling", max(authored) if authored else None, cap, cause))
        for other, other_cause in self.rpe_caps:
            if other_cause != cause:
                self.steps.append(Step("rpe_ceiling", other, cap, "not_binding"))
        self.sets = tuple(
            replace(g, rpe=cap if g.rpe is None else min(g.rpe, cap)) if g.working else g
            for g in self.sets
        )
        self._limit_load(cap)
        return cap

    def _limit_load(self, cap: Number) -> None:
        if not self.loads:
            return
        found = self.context.e1rm
        if found is None or self.loads[0].mode == "assisted":
            self._clip_to_anchor(cap)
            return
        self.sets = reps_within_model(self.sets, cap)
        reps = self._limiting_reps()
        if reps is None:
            return
        limit = model_load(found.load, reps, cap).as_mode(self.loads[0].mode)
        self._limit("rpe_ceiling", limit, "e1rm")

    def _limiting_reps(self) -> int | None:
        """Every working group carries the line's load, so the group with the most reps limits
        it; under `top_backoff` the back-offs follow the top, so the top limits it."""
        working = [g for g in self.sets if g.working]
        if self.context.line.scheme.name == "top_backoff":
            working = working[:1]
        reps = [r for g in working if (r := fewest_reps(g.reps)) is not None]
        return max(reps, default=None)

    def _clip_to_anchor(self, cap: Number) -> None:
        top = self.context.anchor_top
        if top is not None:
            self._limit("rpe_ceiling", top, "anchor")
        self.unchecked_cap = cap

    def _unchecked(self) -> None:
        """Raised after the rack step, so the load it quotes is the one the line prescribes."""
        cap = self.unchecked_cap
        if cap is None:
            return
        anchor = self.context.anchor
        clipped = self._amounts()
        self._raise(
            "rpe_ceiling_unchecked",
            {
                "cap": cap,
                "clipped_load": list(clipped) if isinstance(clipped, tuple) else clipped,
                "anchor_exposure": None if anchor is None else anchor.ref,
            },
            f"no usable e1RM to check RPE {cap:g}; the load is held at {_describe(clipped)}",
        )

    def _rack(self) -> None:
        rack = self.context.rack
        if self.loads and rack is not None:
            rounded = tuple(round_to_rack(rack, load, self.rounding) for load in self.loads)
            before = self._amounts()
            self.loads = tuple(r.load for r in rounded)
            cause = "rack_top" if any(r.cause == "rack_top" for r in rounded) else "row"
            self.steps.append(Step("rack", before, self._amounts(), cause))
        pin = self._pin()
        ceiling = safety_ceiling(self.context.request.decisions, self.context.line.exercise)
        if ceiling is None or not self.loads:
            self._pin_on_rack(pin, rack)
            return
        limit = Load(ceiling, self.loads[0].mode)
        if rack is not None:
            limit = round_to_rack(rack, limit, "cut").load
        self.load_ceilings.append(limit)
        if pin is not None and harder(pin, limit):
            self._off_grid(
                pin,
                [limit.amount],
                f"the pinned {pin.amount:g} is over the safety ceiling of {ceiling:g}",
            )
        else:
            self._pin_on_rack(pin, rack)
        if not self._limit("rack", limit, "safety_ceiling", lowers_rounding=False):
            self.steps.append(Step("rack", ceiling, self._amounts(), "not_binding"))

    def _pin_on_rack(self, pin: Load | None, rack: Rack | None) -> None:
        if pin is None or rack is None or on_rack(rack, pin.amount):
            return
        nearest = list(rows_beside(rack, pin.amount))
        implement = self.context.exercise.equipment_kind
        location = self.context.request.planned.location
        self._off_grid(
            pin,
            nearest,
            f"the pinned {pin.amount:g} is not a row of the {implement} rack at {location}; "
            f"nearest {', '.join(f'{load:g}' for load in nearest)}",
        )

    def _off_grid(self, pin: Load, nearest: list[float], message: str) -> None:
        self._raise(
            "load_off_grid",
            {
                "load": pin.amount,
                "implement": self.context.exercise.equipment_kind,
                "location": self.context.request.planned.location,
                "nearest_grid_loads": nearest,
            },
            message,
        )

    def _test(self) -> Load | None:
        request = self.context.request
        form = request.version.form
        deload = form.deload
        priority = form.dose is not None and self.context.line.exercise in form.dose.lift
        light_week = self._override("light_week") is not None
        if not (light_week and deload is not None and deload.test_priority_lifts and priority):
            return None
        if self.context.line.scheme.name not in TEST_SCHEMES:
            return None
        other_caps = [(cap, cause) for cap, cause in self.rpe_caps if cause != "light_week"]
        if other_caps:
            _, cause = min(other_caps, key=lambda c: c[0])
            self.steps.append(Step("test", None, None, cause))
            return None
        found = self.context.e1rm
        if found is None:
            return None
        single = model_load(found.load, 1, TEST_RPE).as_mode(self.context.mode)
        for ceiling in self.load_ceilings:
            single = easier(single, ceiling)
        rack = self.context.rack
        return single if rack is None else round_to_rack(rack, single, "cut").load

    def _limit(self, step: str, ceiling: Load, cause: str, *, lowers_rounding: bool = True) -> bool:
        """Every load over `ceiling` lowered to it; whether any was."""
        if not any(harder(load, ceiling) for load in self.loads):
            return False
        limited = tuple(easier(load, ceiling) for load in self.loads)
        if lowers_rounding:
            self._lower(step, limited, cause)
        else:
            self.steps.append(Step(step, self._amounts(), _amounts(limited, self.per_set), cause))
            self.loads = limited
        return True

    def _lower(self, step: str, to: tuple[Load, ...], cause: str) -> None:
        self.steps.append(Step(step, self._amounts(), _amounts(to, self.per_set), cause))
        self.loads = to
        self.rounding = "cut"

    def _amounts(self) -> StepValue:
        return _amounts(self.loads, self.per_set)

    def _override(self, kind: str) -> PlanOverride | None:
        planned = self.context.request.planned
        return next(
            (
                o
                for o in self.context.request.overrides
                if o.kind == kind
                and o.session_id in (None, planned.session_id)
                and o.exercise_id in (None, self.context.line.exercise)
            ),
            None,
        )

    def _pin(self) -> Load | None:
        return self.context.pin

    def _raise(self, code: str, params: dict[str, object], message: str) -> None:
        self.flags.append(raise_flag(code, self.context.scope, params, message))


def _amounts(loads: tuple[Load, ...], per_set: bool) -> StepValue:
    """A step's value: one amount for a single load, a tuple for per-set loads."""
    if per_set:
        return tuple(load.amount for load in loads)
    return loads[0].amount if loads else None


def _describe(amounts: StepValue) -> str:
    if isinstance(amounts, tuple):
        return ", ".join(f"{amount:g}" for amount in amounts)
    return "" if amounts is None else f"{amounts:g}"
