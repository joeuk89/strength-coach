"""The bands `program adopt` warns against (docs/spec/goals.md, "Defaults per emphasis")."""

import math
from dataclasses import dataclass

from coach.core.program.defaults import DELOADS, MAINTENANCE_SHARE
from coach.core.program.form import Deload, Emphasis, Line, Reps
from coach.core.registries.phase import PHASE

HYPERTROPHY_SCHEMES = ("double_progression", "assistance_ladder", "hold")
PRIORITY_SCHEMES = ("top_backoff", "wave_531", "linear", "assistance_ladder")
PRIORITY_REPS = (3, 6)
PRIORITY_DOUBLE_PROGRESSION = "double_progression in 3-6 reps"


def scheme_band(priority: bool) -> tuple[str, ...]:
    """A priority lift takes the priority column under every emphasis; every other line the
    hypertrophy column, as a strength version's accessories do."""
    return (*PRIORITY_SCHEMES, PRIORITY_DOUBLE_PROGRESSION) if priority else HYPERTROPHY_SCHEMES


def scheme_fits(line: Line, priority: bool) -> bool:
    name = line.scheme.name
    if not priority:
        return name in HYPERTROPHY_SCHEMES
    if name in PRIORITY_SCHEMES:
        return True
    return name == "double_progression" and all(
        _inside(group.reps, PRIORITY_REPS) for group in line.working_groups()
    )


def _inside(reps: Reps | None, band: tuple[int, int]) -> bool:
    low, high = band
    if isinstance(reps, int):
        return low <= reps <= high
    if isinstance(reps, tuple):
        return low <= reps[0] and reps[1] <= high
    return False


@dataclass(frozen=True)
class DoseBands:
    per_muscle: tuple[int, int]
    per_lift: tuple[int, int]


FULL_BANDS = DoseBands(per_muscle=(10, 20), per_lift=(5, 15))
UPPER_HALF_BANDS = DoseBands(per_muscle=(15, 20), per_lift=(10, 15))


def dose_bands(emphasis: Emphasis, phase: str | None) -> DoseBands:
    if emphasis == "maintenance":
        return DoseBands(_third(FULL_BANDS.per_muscle), _third(FULL_BANDS.per_lift))
    if phase is not None and PHASE.get(phase).dose_default == "upper_half_of_band":
        return UPPER_HALF_BANDS
    return FULL_BANDS


def _third(band: tuple[int, int]) -> tuple[int, int]:
    return (math.ceil(band[0] / MAINTENANCE_SHARE), math.ceil(band[1] / MAINTENANCE_SHARE))


def deload_shape(deload: Deload) -> dict[str, object]:
    """The light cut a deload policy prescribes; the hard-week ceiling is the Block's, not the
    shape's."""
    return {
        "set_cut_pct": deload.set_cut_pct,
        "load_cut_pct": deload.load_cut_pct,
        "rpe_cap": deload.rpe_cap,
        "test_priority_lifts": deload.test_priority_lifts,
    }


def expected_deload_shape(emphasis: Emphasis) -> dict[str, object]:
    return deload_shape(DELOADS[emphasis])
