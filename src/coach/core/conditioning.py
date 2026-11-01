"""Session schemes (docs/spec/prescription.md, "The move, per scheme", notes; ADR 0010): a
conditioning session's dose from its last matched Activity, the params as authored with none."""

from collections.abc import Mapping
from typing import cast

from coach.core.prescription import ConditioningDose, MatchedActivity
from coach.core.program.form import SchemeRef

SESSION_SCHEMES = ("emom_density", "circuit_rounds")


def conditioning_dose(
    scheme: SchemeRef, activity: MatchedActivity | None
) -> ConditioningDose | None:
    if scheme.name not in SESSION_SCHEMES:
        return None
    params = scheme.params
    authored = _per_exercise(params.get("reps"))
    volume_key = _volume_key(scheme)
    if activity is None:
        return _dose(scheme, _int(params, volume_key), authored, "params", "as authored")
    volume = activity.rounds if scheme.name == "circuit_rounds" else activity.minutes
    volume = _int(params, volume_key) if volume is None else volume
    reps = {**authored, **activity.reps}
    derived_from = f"activity:{activity.date.isoformat()}"
    over = activity.rpe is not None and activity.rpe > float(cast(float, params["rpe_target"]))
    if over:
        return _dose(scheme, volume, reps, derived_from, "held")
    cap = _int(params, f"{volume_key}_cap")
    if volume < cap:
        step = _int(params, "minutes_step") if scheme.name == "emom_density" else 1
        stepped = min(volume + step, cap)
        unit = "min" if scheme.name == "emom_density" else "rounds"
        return _dose(scheme, stepped, reps, derived_from, f"{volume} → {stepped} {unit}")
    caps = _reps_caps(params.get("reps_cap"), reps)
    stepped_reps = {exercise: min(n + 1, caps.get(exercise, n + 1)) for exercise, n in reps.items()}
    change = "held" if stepped_reps == reps else "reps +1"
    return _dose(scheme, volume, stepped_reps, derived_from, change)


def _volume_key(scheme: SchemeRef) -> str:
    return "rounds" if scheme.name == "circuit_rounds" else "minutes"


def _dose(
    scheme: SchemeRef, volume: int, reps: Mapping[str, int], derived_from: str, change: str
) -> ConditioningDose:
    if scheme.name == "circuit_rounds":
        minutes = _int(scheme.params, "time_cap_minutes")
        return ConditioningDose(scheme.name, minutes, volume, reps, derived_from, change)
    return ConditioningDose(scheme.name, volume, None, reps, derived_from, change)


def _int(params: Mapping[str, object], name: str) -> int:
    value = params[name]
    assert isinstance(value, int)
    return value


def _per_exercise(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): int(v) for k, v in cast(Mapping[object, int], value).items()}


def _reps_caps(value: object, reps: Mapping[str, int]) -> dict[str, int]:
    """`reps_cap` is one number for every exercise or one per exercise; none leaves reps
    uncapped."""
    if isinstance(value, int | float):
        return {exercise: int(value) for exercise in reps}
    return _per_exercise(value)
