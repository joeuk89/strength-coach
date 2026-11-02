"""The anchor exposure (docs/spec/prescription.md, "The anchor exposure")."""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.load import Load, LoadMode
from coach.core.program.form import RACK_MODES
from coach.core.rack import Rack, round_to_rack

SAME_SESSION_WINDOW_DAYS = 90
SAME_SESSION_WINDOW_DAYS_RN = None

type AnchorStep = Literal["same_session", "any_session"]


@dataclass(frozen=True)
class AnchorExposure:
    """`skipped` is the exposure the search would have picked had its load been usable."""

    exposure: Exposure
    step: AnchorStep
    skipped: Exposure | None = None

    @property
    def derived_from(self) -> str:
        return self.exposure.ref


@dataclass(frozen=True)
class StartLoad:
    """No usable exposure anywhere: the line's start load stands, `None` when it has none."""

    load: Load | None
    skipped: Exposure | None = None

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
    mode: LoadMode | None = None,
) -> AnchorExposure | StartLoad:
    """With `mode` a rack mode, an exposure with no working set at a positive load is skipped
    like a deload log; under assistance 0 is a real load."""
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
    newest = _search(candidates, session_id, window_start)
    if mode not in RACK_MODES or newest is None or _usable(newest[0]):
        return _found(newest, start_load, None)
    usable = [e for e in candidates if _usable(e)]
    return _found(_search(usable, session_id, window_start), start_load, newest[0])


def _search(
    candidates: list[Exposure], session_id: str, window_start: datetime.date
) -> tuple[Exposure, AnchorStep] | None:
    same = next(
        (e for e in candidates if e.session_id == session_id and e.date >= window_start), None
    )
    if same is not None:
        return same, "same_session"
    if candidates:
        return candidates[0], "any_session"
    return None


def _found(
    found: tuple[Exposure, AnchorStep] | None, start_load: Load | None, skipped: Exposure | None
) -> AnchorExposure | StartLoad:
    if found is None:
        return StartLoad(start_load, skipped)
    return AnchorExposure(*found, skipped)


def _usable(exposure: Exposure) -> bool:
    top = exposure.top_load
    return top is not None and top.amount > 0


def anchor_load_unusable(found: AnchorExposure | StartLoad, scope: Scope) -> Flag | None:
    skipped = found.skipped
    if skipped is None:
        return None
    top = skipped.top_load
    logged = None if top is None else top.amount
    return raise_flag(
        "anchor_load_unusable",
        scope,
        {"exposure": skipped.ref, "logged_load": logged, "anchor_used": found.derived_from},
        f"{skipped.ref} has no working set at a positive load; the anchor is {found.derived_from}",
    )


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
