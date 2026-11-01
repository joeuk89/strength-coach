"""A line's past exposures, newest first: the anchor's session, deload logs never among them."""

import datetime
from collections.abc import Iterable

from coach.core.exposure import Exposure
from coach.core.load import Load, LoadMode
from coach.core.rack import Rack, round_to_rack


def line_history(
    exposures: Iterable[Exposure], anchor: Exposure, *, on: datetime.date
) -> tuple[Exposure, ...]:
    return tuple(
        sorted(
            (
                e
                for e in exposures
                if e.exercise_id == anchor.exercise_id
                and e.session_id == anchor.session_id
                and e.date < on
            ),
            key=lambda e: (e.date, e.workout_id),
            reverse=True,
        )
    )


def ordinary(history: Iterable[Exposure]) -> tuple[Exposure, ...]:
    """Light-week and return-week exposures skipped (docs/spec/prescription.md, "Stalls")."""
    return tuple(e for e in history if not _light_or_return(e))


def _light_or_return(exposure: Exposure) -> bool:
    match = exposure.match
    return match is not None and (
        match.light_week or exposure.exercise_id in match.return_band_lines
    )


def top_on_grid(exposure: Exposure, rack: Rack | None, mode: LoadMode) -> Load | None:
    """The exposure's top working load as the rack row at or below it."""
    top = exposure.top_load
    if top is None:
        return None
    top = top.as_mode(mode)
    return top if rack is None else round_to_rack(rack, top, "hold").load
