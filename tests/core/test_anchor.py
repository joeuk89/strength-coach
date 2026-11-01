import datetime

from support.exposures import an_exposure

from coach.core.anchor import AnchorExposure, StartLoad, anchor, anchor_load
from coach.core.config import RackImplement
from coach.core.exposure import Exposure
from coach.core.flag import Scope, raise_flag
from coach.core.load import Load
from coach.core.rack import grid_rack

PLANNED = datetime.date(2026, 11, 2)
START = Load(60, "total")


def anchored(*exposures: Exposure, session_id: str = "push_a") -> AnchorExposure | StartLoad:
    return anchor(
        exposures,
        exercise_id="bb_bench_press",
        session_id=session_id,
        on=PLANNED,
        start_load=START,
    )


def test_the_anchor_is_the_newest_exposure_in_the_same_session() -> None:
    same = an_exposure("2026-10-19", (100, 5, 8), session_id="push_a")
    other = an_exposure("2026-10-26", (102.5, 5, 8), session_id="push_b")
    older_same = an_exposure("2026-10-12", (97.5, 5, 8), session_id="push_a")

    assert anchored(older_same, same, other) == AnchorExposure(same, "same_session")


def test_with_none_in_the_session_in_90_days_it_is_the_newest_in_any_session() -> None:
    stale = an_exposure("2026-07-01", (100, 5, 8), session_id="push_a")
    other = an_exposure("2026-10-26", (102.5, 5, 8), session_id="push_b")
    unmatched = an_exposure("2026-10-20", (95, 5, 8))

    assert anchored(stale, other, unmatched) == AnchorExposure(other, "any_session")


def test_an_exposure_90_days_back_is_still_in_the_window() -> None:
    edge = an_exposure("2026-08-04", (100, 5, 8), session_id="push_a")
    other = an_exposure("2026-10-26", (102.5, 5, 8), session_id="push_b")

    assert anchored(edge, other) == AnchorExposure(edge, "same_session")


def test_with_no_exposure_at_all_it_is_the_start_load() -> None:
    squat = an_exposure("2026-10-26", (140, 5, 8), exercise_id="bb_back_squat")

    found = anchored(squat)

    assert found == StartLoad(START)
    assert found.derived_from == "start_load"


def test_an_exposure_on_the_planned_date_or_later_is_not_an_anchor() -> None:
    assert anchored(an_exposure("2026-11-02", (100, 5, 8), session_id="push_a")) == StartLoad(START)


def test_a_light_week_exposure_is_never_an_anchor() -> None:
    before = an_exposure("2026-10-19", (100, 5, 8), session_id="push_a")
    deload = an_exposure("2026-10-26", (80, 3, 6), session_id="push_a", light_week=True)

    found = anchored(before, deload)

    assert found == AnchorExposure(before, "same_session")
    assert found.derived_from == "exposure:w-2026-10-19/bb_bench_press"


def test_a_light_week_exposure_is_skipped_in_any_session_too() -> None:
    deload = an_exposure("2026-10-26", (80, 3, 6), session_id="push_b", light_week=True)

    assert anchored(deload) == StartLoad(START)


def test_a_light_week_exposure_whose_line_took_the_return_band_is_the_anchor() -> None:
    before = an_exposure("2026-10-12", (100, 5, 8), session_id="push_a")
    returned = an_exposure(
        "2026-10-19",
        (85, 5, 7),
        session_id="push_a",
        light_week=True,
        return_band_lines=frozenset({"bb_bench_press"}),
    )
    deload = an_exposure("2026-10-26", (80, 3, 6), session_id="push_a", light_week=True)

    assert anchored(before, returned, deload) == AnchorExposure(returned, "same_session")


def test_another_line_taking_the_return_band_keeps_no_light_week_exposure() -> None:
    deload = an_exposure(
        "2026-10-26",
        (80, 3, 6),
        session_id="push_a",
        light_week=True,
        return_band_lines=frozenset({"bb_back_squat"}),
    )

    assert anchored(deload) == StartLoad(START)


RACK = grid_rack(RackImplement(rack=(95, 100, 102.5, 105)))


def test_the_anchor_load_is_its_top_working_load() -> None:
    exposure = an_exposure("2026-10-26", (100, 5, 8), (102.5, 3, 9), (95, 8, 8))

    assert anchor_load(exposure, RACK, session_id="push_a") == (Load(102.5, "total"), None)


def test_an_off_grid_anchor_load_takes_the_row_at_or_below_and_warns() -> None:
    exposure = an_exposure("2026-10-26", (104, 5, 8))

    load, flag = anchor_load(exposure, RACK, session_id="push_a")

    assert load == Load(102.5, "total")
    assert flag == raise_flag(
        "offgrid_anchor_ignored",
        Scope("line", session_id="push_a", exercise_id="bb_bench_press"),
        {
            "exposure": "exposure:w-2026-10-26/bb_bench_press",
            "logged_load": 104,
            "anchor_used": 102.5,
        },
        "the logged 104 is not a rack row; the anchor uses 102.5",
    )


def test_a_bodyweight_anchor_carries_no_load() -> None:
    hang = an_exposure("2026-10-26", (None, 8, 8), mode="bodyweight")

    assert anchor_load(hang, RACK, session_id="push_a") == (None, None)
