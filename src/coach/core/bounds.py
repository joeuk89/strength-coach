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
from coach.core.e1rm import e1rm as best_e1rm
from coach.core.e1rm import model_load
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.load import Load, LoadMode
from coach.core.prescription import (
    ExerciseFacts,
    NiggleConstraint,
    PlanOverride,
    PrescribeRequest,
    Step,
)
from coach.core.program.form import Line, Number, SetGroup
from coach.core.rack import Rack, Rounding, round_to_rack

TEST_SCHEMES = ("top_backoff", "wave_531")
TEST_RPE = 9


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


@dataclass(frozen=True)
class Bounded:
    sets: tuple[SetGroup, ...]
    load: Load | None
    rpe_cap: Number | None = None
    test: Load | None = None
    dropped: bool = False


def bound(
    context: LineContext,
    proposal: Load | None,
    rounding: Rounding,
    steps: list[Step],
    flags: list[Flag],
) -> Bounded:
    """`steps` and `flags` are the line's, appended to in pipeline order."""
    return _Bounding(context, proposal, rounding, steps, flags, context.line.sets).run()


@dataclass
class _Bounding:
    context: LineContext
    load: Load | None
    rounding: Rounding
    steps: list[Step]
    flags: list[Flag]
    sets: tuple[SetGroup, ...]
    rpe_caps: list[tuple[Number, str]] = field(default_factory=list[tuple[Number, str]])
    light: bool = False
    load_ceilings: list[Load] = field(default_factory=list[Load])

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
        return Bounded(self.sets, self.load, cap, self._test())

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
        base = self.context.scheme_load
        if base is not None and self.context.anchor_top is not None:
            base = easier(base, self.context.anchor_top)
        if base is not None:
            target = self._band_load(band, base)
            pin = self._pin()
            if pin is not None and not harder(pin, target):
                target = pin
            if target != self.load:
                self._lower("cut", target, cause)
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
        self._set_count(one_working_set_fewer(self.sets))
        if self.context.line.scheme.name == "wave_531":
            self.sets = close_rep_outs(self.sets)
        self.rpe_caps.append((band.rpe_cap, "return_band"))

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
        self.light = True
        if self.load is not None and shape.load_cut_pct and self.load.mode != "assisted":
            factor = 1 - shape.load_cut_pct / 100
            self._lower(
                "cut", replace(self.load, amount=round(self.load.amount * factor, 4)), "light"
            )
        self._set_count(cut_each_working_group(self.sets, shape.set_cut_pct))
        self.sets = close_rep_outs(self.sets)
        if shape.rpe_cap is not None:
            self.rpe_caps.append((shape.rpe_cap, "light_week"))

    def _set_count(self, cut: tuple[SetGroup, ...]) -> None:
        before, after = working_set_count(self.sets), working_set_count(cut)
        if after != before:
            self.steps.append(Step("cut", before, after, "sets"))
        self.sets = cut

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
        if self.load is None:
            return
        if harder(self.load, strictest):
            self._lower("niggle", strictest, f"{by.kind} niggle:{by.niggle_id}")
        else:
            self.steps.append(Step("niggle", strictest.amount, self.load.amount, "not_binding"))

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
        if self.load is None:
            return
        found = best_e1rm(
            self.context.request.exposures,
            self.context.line.exercise,
            self.context.request.planned.date,
        )
        if found is None or self.load.mode == "assisted":
            self._unchecked(cap)
            return
        self.sets = reps_within_model(self.sets, cap)
        reps = self._limiting_reps()
        if reps is None:
            return
        limit = model_load(found.load, reps, cap).as_mode(self.load.mode)
        if harder(self.load, limit):
            self._lower("rpe_ceiling", limit, "e1rm")

    def _limiting_reps(self) -> int | None:
        """Every working group carries the line's load, so the group with the most reps limits
        it; under `top_backoff` the back-offs follow the top, so the top limits it."""
        working = [g for g in self.sets if g.working]
        if self.context.line.scheme.name == "top_backoff":
            working = working[:1]
        reps = [r for g in working if (r := fewest_reps(g.reps)) is not None]
        return max(reps, default=None)

    def _unchecked(self, cap: Number) -> None:
        assert self.load is not None
        top = self.context.anchor_top
        if top is not None and harder(self.load, top):
            self._lower("rpe_ceiling", top, "anchor")
        anchor = self.context.anchor
        self._raise(
            "rpe_ceiling_unchecked",
            {
                "cap": cap,
                "clipped_load": self.load.amount,
                "anchor_exposure": None if anchor is None else anchor.ref,
            },
            f"no usable e1RM to check RPE {cap:g}; the load is held at {self.load.amount:g}",
        )

    def _rack(self) -> None:
        rack = self.context.rack
        if self.load is not None and rack is not None:
            rounded = round_to_rack(rack, self.load, self.rounding)
            self.steps.append(Step("rack", self.load.amount, rounded.load.amount, rounded.cause))
            self.load = rounded.load
        ceiling = safety_ceiling(self.context.request.decisions, self.context.line.exercise)
        if ceiling is None or self.load is None:
            return
        limit = Load(ceiling, self.load.mode)
        if rack is not None:
            limit = round_to_rack(rack, limit, "cut").load
        self.load_ceilings.append(limit)
        pin = self._pin()
        if pin is not None and harder(pin, limit):
            self._raise(
                "load_off_grid",
                {
                    "load": pin.amount,
                    "implement": self.context.exercise.equipment_kind,
                    "location": self.context.request.planned.location,
                    "nearest_grid_loads": [limit.amount],
                },
                f"the pinned {pin.amount:g} is over the safety ceiling of {ceiling:g}",
            )
        if harder(self.load, limit):
            self.steps.append(Step("rack", self.load.amount, limit.amount, "safety_ceiling"))
            self.load = limit
        else:
            self.steps.append(Step("rack", ceiling, self.load.amount, "not_binding"))

    def _test(self) -> Load | None:
        request = self.context.request
        form = request.version.form
        deload = form.deload
        priority = form.dose is not None and self.context.line.exercise in form.dose.lift
        if not (self.light and deload is not None and deload.test_priority_lifts and priority):
            return None
        if self.context.line.scheme.name not in TEST_SCHEMES:
            return None
        if any(cause != "light_week" for _, cause in self.rpe_caps):
            return None
        found = best_e1rm(request.exposures, self.context.line.exercise, request.planned.date)
        if found is None:
            return None
        single = model_load(found.load, 1, TEST_RPE).as_mode(self.context.mode)
        for ceiling in self.load_ceilings:
            single = easier(single, ceiling)
        rack = self.context.rack
        return single if rack is None else round_to_rack(rack, single, "cut").load

    def _lower(self, step: str, to: Load, cause: str) -> None:
        assert self.load is not None
        self.steps.append(Step(step, self.load.amount, to.amount, cause))
        self.load = to
        self.rounding = "cut"

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
