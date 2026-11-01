"""`assistance_ladder` (docs/spec/prescription.md, "The move, per scheme"): rungs of assisted
load, most assistance first; a full hit climbs one rung, the last rung holds."""

from collections.abc import Sequence

from coach.core.program.form import Line


def rungs(line: Line) -> tuple[float, ...]:
    authored = line.scheme.params.get("rungs", ())
    assert isinstance(authored, Sequence)
    return tuple(sorted((float(r) for r in authored), reverse=True))  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


def rung_of(load: float, ladder: Sequence[float]) -> float:
    """The rung a logged load stands on: the nearest at or above it, so never less assistance
    than was logged."""
    at_or_above = [rung for rung in ladder if rung >= load]
    return min(at_or_above) if at_or_above else ladder[0]


def next_rung(rung: float, ladder: Sequence[float]) -> float | None:
    lighter = [r for r in ladder if r < rung]
    return max(lighter) if lighter else None
