"""The `linear` reset (docs/spec/prescription.md, "Stalls"): the second consecutive miss at one
load resets to `reset_factor` × that load, rounded down to the rack."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from coach.core.exposure import Exposure
from coach.core.line_history import newest_first, ordinary, top_on_grid
from coach.core.load import Load, LoadMode
from coach.core.program.form import Line
from coach.core.progression import judge
from coach.core.rack import Rack, round_to_rack
from coach.core.scheme_params import number

PRECISION = 4


def misses_before_reset(line: Line) -> int:
    return int(number(line.scheme, "misses_before_reset"))


def missed(line: Line, exposure: Exposure, load: Load) -> bool:
    """Every authored set attempted and not every one made; a set never logged is not a miss."""
    verdict = judge(line, exposure, load)
    return not verdict.hit and not verdict.incomplete


def misses_at(line: Line, history: Sequence[Exposure], load: Load, rack: Rack | None) -> int:
    """Consecutive misses at `load`, newest first; an exposure at another load ends the count."""
    count = 0
    for exposure in history:
        if top_on_grid(exposure, rack, load.mode) != load or not missed(line, exposure, load):
            break
        count += 1
    return count


def reset_load(line: Line, load: Load, rack: Rack | None) -> Load:
    factor = number(line.scheme, "reset_factor")
    target = Load(round(load.amount * factor, PRECISION), load.mode)
    return target if rack is None else round_to_rack(rack, target, "cut").load


@dataclass(frozen=True)
class Reset:
    exposure: str
    from_: float
    to: float


def resets(
    line: Line, exposures: Iterable[Exposure], rack: Rack | None, mode: LoadMode
) -> tuple[Reset, ...]:
    """Every reset the line's ordinary history shows, oldest first: an exposure at a lighter load
    right after the misses that called for one."""
    history = ordinary(newest_first(exposures))
    found: list[Reset] = []
    for index, exposure in enumerate(history[:-1]):
        earlier = history[index + 1 :]
        previous = top_on_grid(earlier[0], rack, mode)
        now = top_on_grid(exposure, rack, mode)
        if previous is None or now is None or now.amount >= previous.amount:
            continue
        if misses_at(line, earlier, previous, rack) >= misses_before_reset(line):
            found.append(Reset(exposure.ref, previous.amount, now.amount))
    return tuple(reversed(found))
