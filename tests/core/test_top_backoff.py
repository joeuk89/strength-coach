import datetime
from typing import Any

from support.exposures import an_exposure
from support.prescribe import a_line, a_rack, a_request, warm_up, working

from coach.core.days_off import SessionTrained
from coach.core.exposure import Exposure
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import LinePrescription, PlanOverride, Step

RACK = a_rack(*[70 + 2.5 * i for i in range(21)])
BENCH = a_line(
    "bb_bench_press",
    warm_up(5),
    working(1, 3, 8),
    working(3, 5, None),
    scheme="top_backoff",
    pct_of_top=85,
)


def bench_on(on: str, top_rpe: float, top: float = 100) -> Exposure:
    return an_exposure(on, (top, 3, top_rpe), *[(85, 5, 7)] * 3, session_id="lower")


def derive(*exposures: Exposure, line: Any = BENCH, **request: Any) -> LinePrescription:
    built = a_request(line, exposures=exposures, racks={"barbell": RACK}, **request)
    return prescribe(built).lines[0]


def working_loads(line: LinePrescription) -> list[tuple[int, Load | None]]:
    return [(g.count, g.load) for g in line.groups if g.type == "working"]


def test_an_e1rm_asking_for_two_rows_above_the_anchor_prescribes_one_row_above() -> None:
    # e1RM 100 × (1 + 7/30) = 123.33; three reps at RPE 8 is 105.71, down to 105: two rows up
    line = derive(bench_on("2026-10-26", top_rpe=6))

    assert line.steps[0] == Step("scheme", 100, 102.5, "one_row_cap")
    assert working_loads(line) == [(1, Load(102.5, "total")), (3, Load(87.5, "total"))]
    assert line.change == "1×3 @8 + 3×5: 100 → 102.5"


def test_an_e1rm_inside_one_row_sets_the_top_rounded_down() -> None:
    # e1RM 100 × (1 + 5.5/30) = 118.33; three reps at RPE 8 is 101.43, down to 100
    line = derive(bench_on("2026-10-26", top_rpe=7.5))

    assert working_loads(line) == [(1, Load(100, "total")), (3, Load(85, "total"))]
    assert line.change == "held"


def test_with_no_e1rm_in_42_days_the_top_holds_and_warns_no_e1rm() -> None:
    trained = (SessionTrained(datetime.date(2026, 10, 26), "lower"),)

    line = derive(bench_on("2026-09-10", top_rpe=6), trained=trained)

    assert working_loads(line) == [(1, Load(100, "total")), (3, Load(85, "total"))]
    assert [(f.code, dict(f.params)) for f in line.flags] == [
        ("no_e1rm", {"exercise_id": "bb_bench_press", "scheme": "top_backoff"})
    ]


def test_one_bad_day_never_lowers_the_top_set() -> None:
    good = derive(bench_on("2026-10-26", top_rpe=6))

    after_a_bad_day = derive(
        bench_on("2026-10-19", top_rpe=6),
        an_exposure("2026-10-26", (100, 3, 9.5), *[(85, 4, 9)] * 3, session_id="lower"),
    )

    assert working_loads(after_a_bad_day) == working_loads(good)


def test_a_bad_day_at_a_lighter_top_never_lowers_the_top_set() -> None:
    good = derive(bench_on("2026-10-26", top_rpe=8, top=110))

    after_a_bad_day = derive(
        bench_on("2026-10-19", top_rpe=8, top=110),
        an_exposure("2026-10-26", (100, 3, 9.5), *[(85, 4, 9)] * 3, session_id="lower"),
    )

    assert working_loads(good)[0] == (1, Load(110, "total"))
    assert working_loads(after_a_bad_day) == working_loads(good)


def test_with_no_exposure_the_start_load_is_the_top_and_the_back_offs_derive_from_it() -> None:
    opening = a_line(
        "bb_bench_press",
        working(1, 3, 8),
        working(3, 5, None),
        scheme="top_backoff",
        pct_of_top=80,
        start_load=100,
    )

    line = derive(line=opening)

    assert working_loads(line) == [(1, Load(100, "total")), (3, Load(80, "total"))]


def test_a_light_cut_lowers_the_back_offs_with_their_top() -> None:
    light = PlanOverride("light_week", params={"load_cut_pct": 10})

    line = derive(bench_on("2026-10-26", top_rpe=7.5), overrides=(light,))

    assert working_loads(line) == [(1, Load(90, "total")), (2, Load(77.5, "total"))]


def test_a_heavier_top_in_another_session_never_lifts_the_cap_past_one_row() -> None:
    upper = an_exposure("2026-10-23", (110, 3, 8), *[(92.5, 5, 7)] * 3, session_id="upper")

    line = derive(bench_on("2026-10-19", top_rpe=8), upper, bench_on("2026-10-26", top_rpe=8))

    assert working_loads(line)[0] == (1, Load(102.5, "total"))
