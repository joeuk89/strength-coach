"""The scheme-switching table: what a version may do with a line that raised a cadence signal
(docs/spec/goals.md, "Response to a cadence signal"). A running agent reads the row from the
signal's params, never this table (ADR 0020)."""

from dataclasses import dataclass

from coach.core.registries.schemes import CadenceSignal


@dataclass(frozen=True)
class Switch:
    may_schemes: tuple[str, ...]
    may: str
    never: str
    rn: tuple[str, ...]

    def params(self) -> dict[str, object]:
        return {"may_schemes": list(self.may_schemes), "may": self.may, "never": self.never}


SWITCHING: dict[tuple[CadenceSignal, str], Switch] = {
    ("cadence_slow", "linear"): Switch(
        ("double_progression", "top_backoff"),
        "move the line to double_progression (hypertrophy line) or top_backoff (priority lift "
        "or strength line)",
        "keep resetting",
        ("rn:progression-methods §4", "rn:training-level §2"),
    ),
    ("cadence_slow", "double_progression"): Switch(
        (),
        "add sets early in the next block, plan the deload, swap the exercise or change the rep "
        "range at the boundary",
        "change the scheme: no source does",
        ("rn:progression-methods §4",),
    ),
    ("cadence_slow", "top_backoff"): Switch(
        ("wave_531",),
        "move the lift to wave_531, the training max set by the test set or a training_max "
        "Decision; or change back-off volume and add a variation first",
        "drop to a hypertrophy scheme to escape a strength stall",
        ("rn:progression-methods §4",),
    ),
    ("cadence_slow", "wave_531"): Switch(
        (),
        "lower the training max about 10 % by Decision and stay a cycle; the scheme stands",
        "raise the training max to chase the miss",
        ("rn:progression-methods §4",),
    ),
    ("cadence_slow", "assistance_ladder"): Switch(
        ("double_progression",),
        "hold the rung; at zero assistance move to double_progression on reps",
        "skip rungs",
        ("rn:progression-methods §4",),
    ),
    ("cadence_fast", "double_progression"): Switch(
        ("linear",),
        "propose linear on that lift while the rack has a next row; the signal is the "
        "evidence, no stored level is needed",
        "fill linear without a Decision",
        ("rn:progression-methods §4", "rn:training-level §2"),
    ),
    ("cadence_fast", "top_backoff"): Switch(
        ("linear",),
        "propose linear on that lift while the rack has a next row; the signal is the "
        "evidence, no stored level is needed",
        "fill linear without a Decision",
        ("rn:progression-methods §4", "rn:training-level §2"),
    ),
}


def switch_for(signal: CadenceSignal, scheme: str) -> Switch | None:
    return SWITCHING.get((signal, scheme))
