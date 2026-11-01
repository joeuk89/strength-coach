"""The Phase read at every check-in: the 14-day Weigh-in average, the observed rate and the two
codes it raises (docs/spec/goals.md, "What the Phase changes" and "Phase")."""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass

from coach.core.config import Units
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.goal import Until
from coach.core.registries.phase import PHASE
from coach.core.units import from_kg

AVERAGE_DAYS = 14
TREND_DAYS = 28
WEEKS_IN_TREND = TREND_DAYS / 7
RATE_PRECISION = 2
WEIGHT_PRECISION = 1

type WeighIns = Mapping[datetime.date, float]


@dataclass(frozen=True)
class PhaseInForce:
    id: str
    kind: str
    rate_pct_bw_per_week: float
    until: Until
    opened: datetime.date


def fourteen_day_average(weigh_ins: WeighIns, on: datetime.date) -> float | None:
    """Kilograms, over the weigh-ins of the 14 days ending on `on`."""
    start = on - datetime.timedelta(days=AVERAGE_DAYS - 1)
    found = [kg for day, kg in weigh_ins.items() if start <= day <= on]
    return sum(found) / len(found) if found else None


def observed_rate(weigh_ins: WeighIns, on: datetime.date) -> float | None:
    """% bodyweight per week between the 14-day average 28 days earlier and the current one."""
    now = fourteen_day_average(weigh_ins, on)
    then = fourteen_day_average(weigh_ins, on - datetime.timedelta(days=TREND_DAYS))
    if now is None or then is None:
        return None
    return round((now - then) / then * 100 / WEEKS_IN_TREND, RATE_PRECISION)


def phase_trend_off(phase: PhaseInForce, weigh_ins: WeighIns, on: datetime.date) -> Flag | None:
    since = on - datetime.timedelta(days=TREND_DAYS)
    in_phase = [day for day in weigh_ins if phase.opened <= day <= on]
    if not in_phase or min(in_phase) > since:
        return None
    rate = observed_rate(weigh_ins, on)
    if rate is None:
        return None
    band = PHASE.get(phase.kind).trend_band
    target = phase.rate_pct_bw_per_week
    half_width = (
        abs(target) * band.half_width / 100 if band.unit == "pct_of_rate" else band.half_width
    )
    if abs(rate - target) <= half_width:
        return None
    return raise_flag(
        "phase_trend_off",
        Scope("instance"),
        {
            "phase_id": phase.id,
            "target_rate": target,
            "observed_rate": rate,
            "window": [since.isoformat(), on.isoformat()],
        },
        f"bodyweight moved {rate:+g} % a week over the last {TREND_DAYS} days against the "
        f"{phase.kind} target of {target:+g} %",
    )


def phase_condition_met(
    phase: PhaseInForce, weigh_ins: WeighIns, on: datetime.date, *, units: Units
) -> Flag | None:
    """A reached `until` never closes the Phase; the coach does, at a check-in."""
    until = phase.until
    value: object
    if until.kind == "date" and isinstance(until.value, datetime.date):
        if on < until.value:
            return None
        value = until.value.isoformat()
    elif until.kind in ("bodyweight_at_or_below", "bodyweight_at_or_above"):
        kg = fourteen_day_average(weigh_ins, on)
        if kg is None or not isinstance(until.value, int | float):
            return None
        average = round(from_kg(kg, units), WEIGHT_PRECISION)
        below = until.kind == "bodyweight_at_or_below"
        if (average > until.value) if below else (average < until.value):
            return None
        value = average
    else:
        return None
    return raise_flag(
        "phase_condition_met",
        Scope("instance"),
        {"phase_id": phase.id, "condition": until.kind, "value": value},
        f"Phase {phase.id}'s until condition ({until.kind}) is met; close it at a check-in",
    )
