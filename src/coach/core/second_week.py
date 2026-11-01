"""The rules that need the previous WeekPlan: `unexplained_drift` against its frozen lines,
`override_persisting` across consecutive plans and `frozen_load_off_rack` against the rack now
(docs/spec/validation.md; docs/spec/overrides.md, "Promotion"; ADR 0021). `prescribe` never reads
a plan; these run beside it."""

import datetime
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from coach.core.config import Units
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.frozen_prescription import dose, frozen_groups
from coach.core.load import Load, LoadMode
from coach.core.prescription import PlanOverride, SessionPrescription
from coach.core.rack import Rack, round_to_rack

PERSISTING_KINDS = frozenset({"swap_exercise", "restate_sets", "hold", "drop_line"})
PERSISTING_PLANS = 3
WEEK_SHAPES = frozenset({"light_week", "minimum_week", "one_off_week"})

type LineOverride = tuple[str, str, str]


@dataclass(frozen=True)
class FrozenLineFacts:
    """A line of the previous WeekPlan as frozen, with what the rack check needs."""

    session_id: str
    exercise_id: str
    derived_from: str
    set_groups: Sequence[Mapping[str, object]]
    location: str | None = None
    equipment_kind: str | None = None
    load_mode: LoadMode = "total"


@dataclass(frozen=True)
class PreviousPlan:
    plan_id: str
    week: datetime.date
    lines: tuple[FrozenLineFacts, ...]
    overrides: tuple[PlanOverride, ...]


@dataclass(frozen=True)
class PastPlan:
    """An earlier approved plan's line overrides, less those an override Decision covered."""

    plan_id: str
    counted: frozenset[LineOverride]


def unexplained_drift(
    sessions: Sequence[SessionPrescription],
    overrides: Sequence[PlanOverride],
    previous: PreviousPlan,
    *,
    monday: datetime.date,
    units: Units,
) -> tuple[Flag, ...]:
    """A line from the same anchor as last week's frozen line whose set groups moved with no
    override on either plan to explain it."""
    if _week_shaped(overrides) or _week_shaped(previous.overrides):
        return ()
    explained = _overridden(overrides) | _overridden(previous.overrides)
    whole = _sessions_overridden(overrides) | _sessions_overridden(previous.overrides)
    last = {(f.session_id, f.exercise_id): f for f in previous.lines}
    flags: dict[str, Flag] = {}
    for prescribed in sessions:
        session_id = prescribed.session.session_id
        for line in prescribed.lines:
            frozen = last.get((session_id, line.exercise_id))
            if frozen is None or session_id in whole or (session_id, line.exercise_id) in explained:
                continue
            groups = frozen_groups(line.groups, units)
            if frozen.derived_from != (line.derived_from or "start_load"):
                continue
            if list(frozen.set_groups) == groups:
                continue
            before, after = dose(frozen.set_groups, units), dose(groups, units)
            scope = Scope("line", monday, session_id=session_id, exercise_id=line.exercise_id)
            flag = raise_flag(
                "unexplained_drift",
                scope,
                {
                    "last_prescription": before,
                    "this_prescription": after,
                    "delta": f"{before} → {after}",
                },
                f"{line.exercise_id} moved from {before} to {after} with no new exposure and no "
                f"override since {previous.plan_id}",
            )
            flags.setdefault(flag.key, flag)
    return tuple(flags.values())


def override_persisting(
    overrides: Sequence[PlanOverride],
    past: Sequence[PastPlan],
    *,
    covered: Collection[LineOverride],
    monday: datetime.date,
) -> tuple[Flag, ...]:
    """The third consecutive approved plan with the same line override; `past` is newest first,
    `covered` this week's line overrides an override Decision already carries."""
    flags: list[Flag] = []
    for found in _line_overrides(overrides):
        if found in covered:
            continue
        run: list[str] = []
        for plan in past:
            if found not in plan.counted:
                break
            run.append(plan.plan_id)
        if len(run) + 1 < PERSISTING_PLANS:
            continue
        kind, session_id, exercise_id = found
        weeks = len(run) + 1
        flags.append(
            raise_flag(
                "override_persisting",
                Scope("line", monday, session_id=session_id, exercise_id=exercise_id),
                {"kind": kind, "weeks": weeks, "plan_ids": list(reversed(run))},
                f"{kind} on {session_id}/{exercise_id} is on its {weeks}th consecutive plan; "
                "promote it into the program, extend it by Decision, or leave it",
            )
        )
    return tuple(flags)


def counted_overrides(
    overrides: Sequence[PlanOverride], covered: Collection[LineOverride]
) -> frozenset[LineOverride]:
    return frozenset(o for o in _line_overrides(overrides) if o not in covered)


def frozen_load_off_rack(
    previous: PreviousPlan,
    racks: Mapping[str, Mapping[str, Rack]],
    *,
    monday: datetime.date,
) -> tuple[Flag, ...]:
    """Each working load the previous plan froze that the rack at its location no longer
    builds. The scope is the session, so the first such line of a session stands for it."""
    flags: dict[str, Flag] = {}
    for line in previous.lines:
        if line.location is None or line.equipment_kind is None:
            continue
        rack = racks.get(line.location, {}).get(line.equipment_kind)
        if rack is None:
            continue
        for group in line.set_groups:
            amount = group.get("load")
            if group.get("type") == "warm_up" or not isinstance(amount, int | float):
                continue
            frozen = Load(float(amount), line.load_mode)
            if round_to_rack(rack, frozen, "hold").load == frozen:
                continue
            flag = raise_flag(
                "frozen_load_off_rack",
                Scope("session", monday, session_id=line.session_id),
                {
                    "week": previous.week.isoformat(),
                    "line": line.exercise_id,
                    "frozen_load": frozen.amount,
                    "location": line.location,
                },
                f"{line.exercise_id} froze {frozen.amount:g} on {previous.plan_id}; the "
                f"{line.location} rack no longer builds it",
            )
            flags.setdefault(flag.key, flag)
            break
    return tuple(flags.values())


def _line_overrides(overrides: Sequence[PlanOverride]) -> list[LineOverride]:
    return [
        (o.kind, o.session_id, o.exercise_id)
        for o in overrides
        if o.kind in PERSISTING_KINDS and o.session_id and o.exercise_id
    ]


def _overridden(overrides: Sequence[PlanOverride]) -> set[tuple[str, str]]:
    return {(o.session_id, o.exercise_id) for o in overrides if o.session_id and o.exercise_id}


def _sessions_overridden(overrides: Sequence[PlanOverride]) -> set[str]:
    return {o.session_id for o in overrides if o.session_id and not o.exercise_id}


def _week_shaped(overrides: Sequence[PlanOverride]) -> bool:
    return any(o.kind in WEEK_SHAPES for o in overrides)
