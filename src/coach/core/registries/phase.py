from dataclasses import dataclass
from typing import Literal

from coach.core.registries.registry import Registry, Row

TRAINING_LEVEL_4 = "rn:training-level §4"


@dataclass(frozen=True)
class TrendBand:
    """The band `phase_trend_off` reads: a share of the target rate, or a fixed width in % BW
    per week where the target rate is zero."""

    half_width: float
    unit: Literal["pct_of_rate", "pct_bw_per_week"]

    def describe(self) -> Row:
        return {"half_width": self.half_width, "unit": self.unit}


@dataclass(frozen=True)
class PhaseKind:
    name: str
    dose_default: Literal["held", "emphasis_default", "upper_half_of_band"]
    default_rate_pct_bw_per_week: float
    trend_band: TrendBand
    rn: str

    def describe(self) -> Row:
        return {
            "name": self.name,
            "dose_default": self.dose_default,
            "default_rate_pct_bw_per_week": self.default_rate_pct_bw_per_week,
            "trend_band": self.trend_band.describe(),
            "rn": self.rn,
        }


# docs/spec/goals.md, "What the Phase changes": the rates are cited, the band widths are opinion
# under the same citation.
PHASE = Registry(
    "phase",
    (
        PhaseKind("deficit", "held", -0.5, TrendBand(50, "pct_of_rate"), TRAINING_LEVEL_4),
        PhaseKind(
            "maintenance",
            "emphasis_default",
            0,
            TrendBand(0.25, "pct_bw_per_week"),
            TRAINING_LEVEL_4,
        ),
        PhaseKind(
            "surplus", "upper_half_of_band", 0.25, TrendBand(50, "pct_of_rate"), TRAINING_LEVEL_4
        ),
    ),
)
