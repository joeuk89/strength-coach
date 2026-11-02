import datetime

import pytest
from support.exposures import an_exposure

from coach.core.carried_e1rm import carried_e1rm, e1rm_read
from coach.core.days_off import SessionTrained
from coach.core.e1rm import E1rm
from coach.core.exposure import Exposure
from coach.core.load import Load


def bench(on: str, load: float = 100, reps: int = 5, rpe: float = 8) -> Exposure:
    return an_exposure(on, (load, reps, rpe), session_id="lower")


def carried(*exposures: Exposure, on: str, trained: tuple[SessionTrained, ...] = ()):
    return carried_e1rm(
        exposures,
        trained,
        exercise_id="bb_bench_press",
        session_id="lower",
        on=datetime.date.fromisoformat(on),
    )


def test_the_pre_layoff_point_is_read_from_the_42_days_ending_on_the_last_exposure() -> None:
    # 100 × (1 + 7/30) = 123.33 on 2026-08-01 is outside the slid window from 2026-08-07
    old_best = bench("2026-08-01", load=120)
    in_window = bench("2026-09-10", load=100)
    last = bench("2026-09-17", load=90, reps=3, rpe=6)
    returned = bench("2026-10-26", load=80)

    found = carried(old_best, in_window, last, returned, on="2026-11-02")

    assert found is not None
    assert found.pre_layoff == E1rm(Load(123.33, "total"), False, in_window.ref)
    assert found.expires == datetime.date(2026, 12, 7)


@pytest.mark.parametrize(
    ("last", "factor", "load"),
    [("2026-10-12", 0.95, 117.16), ("2026-09-30", 0.90, 111.0), ("2026-09-10", 0.85, 104.83)],
)
def test_the_factor_is_the_band_the_return_exposures_days_off_gave(
    last: str, factor: float, load: float
) -> None:
    found = carried(bench(last), bench("2026-10-26", load=80), on="2026-11-02")

    assert found is not None
    assert (found.factor, found.load) == (factor, Load(load, "total"))


def test_a_return_with_no_qualifying_pre_layoff_point_carries_nothing() -> None:
    too_easy = bench("2026-09-10", load=60, reps=15, rpe=6)

    assert carried(too_easy, bench("2026-10-26", load=80), on="2026-11-02") is None


def test_the_return_week_itself_carries_nothing() -> None:
    assert carried(bench("2026-09-10"), on="2026-10-26") is None


def test_the_carried_e1rm_lives_42_days_after_the_return_exposure_and_no_longer() -> None:
    history = (bench("2026-09-10"), bench("2026-10-26", load=80))
    trained = tuple(
        SessionTrained(datetime.date(2026, 10, 26) + datetime.timedelta(days=d), "lower")
        for d in range(7, 43, 7)
    )

    assert carried(*history, on="2026-12-07", trained=trained) is not None
    assert carried(*history, on="2026-12-08", trained=trained) is None


def test_with_no_layoff_nothing_carries() -> None:
    assert carried(bench("2026-10-19"), bench("2026-10-26"), on="2026-11-02") is None


def test_a_live_point_at_or_above_the_carried_e1rm_ends_it() -> None:
    found = carried(bench("2026-09-10"), bench("2026-10-26", load=80), on="2026-11-02")
    assert found is not None
    at = E1rm(found.load, False, "exposure:w-2026-10-26/bb_bench_press")
    below = E1rm(Load(found.load.amount - 0.01, "total"), False, at.exposure)

    assert e1rm_read(at, found).carried is None
    assert e1rm_read(at, found).best == at
    assert e1rm_read(below, found).carried == found
    assert e1rm_read(below, found).best == E1rm(found.load, False, found.pre_layoff.exposure)
    assert e1rm_read(None, found).best == E1rm(found.load, False, found.pre_layoff.exposure)
