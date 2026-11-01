"""The anchor exposure (docs/spec/prescription.md, "The anchor exposure")."""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.load import Load, LoadMode
from coach.core.rack import Rack, round_to_rack

SAME_SESSION_WINDOW_DAYS = 90
SAME_SESSION_WINDOW_DAYS_RN = None


@dataclass(frozen=True)
class AnchorExposure:
    exposure: Exposure
    step: Literal["same_session", "any_session"]

    @property
    def derived_from(self) -> str:
        return self.exposure.ref


@dataclass(frozen=True)
class StartLoad:
    """No exposure anywhere: the line's start load stands, `None` when it has none."""

    load: Load | None

    @property
    def derived_from(self) -> str:
        return "start_load"


def anchor(
    exposures: Iterable[Exposure],
    *,
    exercise_id: str,
    session_id: str,
    on: datetime.date,
    start_load: Load | None,
) -> AnchorExposure | StartLoad:
    candidates = sorted(
        (
            e
            for e in exposures
            if e.exercise_id == exercise_id and e.date < on and not _deload_log(e)
        ),
        key=lambda e: (e.date, e.workout_id),
        reverse=True,
    )
    window_start = on - datetime.timedelta(days=SAME_SESSION_WINDOW_DAYS)
    same = next(
        (e for e in candidates if e.session_id == session_id and e.date >= window_start), None
    )
    if same is not None:
        return AnchorExposure(same, "same_session")
    if candidates:
        return AnchorExposure(candidates[0], "any_session")
    return StartLoad(start_load)


def _deload_log(exposure: Exposure) -> bool:
    match = exposure.match
    return (
        match is not None
        and match.light_week
        and exposure.exercise_id not in match.return_band_lines
    )


def anchor_load(
    exposure: Exposure,
    rack: Rack,
    *,
    session_id: str,
    monday: datetime.date | None = None,
    mode: LoadMode | None = None,
) -> tuple[Load | None, Flag | None]:
    """The anchor's top working load, replaced by the rack row at or below it when it is not a
    row: a historical load never defines the grid. A bodyweight anchor carries no load. With
    `mode` the logged load is read in the line's load mode first."""
    logged = exposure.top_load
    if logged is None:
        return None, None
    if mode is not None:
        logged = logged.as_mode(mode)
    on_grid = round_to_rack(rack, logged, "hold").load
    if on_grid == logged:
        return logged, None
    flag = raise_flag(
        "offgrid_anchor_ignored",
        Scope("line", monday, session_id=session_id, exercise_id=exposure.exercise_id),
        {"exposure": exposure.ref, "logged_load": logged.amount, "anchor_used": on_grid.amount},
        f"the logged {logged.amount:g} is not a rack row; the anchor uses {on_grid.amount:g}",
    )
    return on_grid, flag
