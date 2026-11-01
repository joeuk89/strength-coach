from support.exposures import an_exposure
from support.prescribe import a_line, a_request, warm_up, working

from coach.core.exposure import Exposure
from coach.core.prescribe import prescribe
from coach.core.prescription import LinePrescription, Step

BENCH = a_line(
    "bb_bench_press",
    warm_up(5),
    working(1, 3, 8),
    working(3, 5, 8),
    scheme="top_backoff",
    pct_of_top=85,
)


def bench(*exposures: Exposure) -> LinePrescription:
    return prescribe(a_request(BENCH, exposures=exposures)).lines[0]


def loads(line: LinePrescription) -> list[tuple[str, int, float | None]]:
    return [(g.type, g.count, None if g.load is None else g.load.amount) for g in line.groups]


def test_an_e1rm_asking_for_two_rows_above_the_anchor_prescribes_one_row_above() -> None:
    great_day = an_exposure("2026-10-12", (150, 3, 8), (125, 5, 7), workout_id="w-1")
    anchor = an_exposure("2026-10-26", (140, 3, 8), (120, 5, 7), workout_id="w-2")

    line = bench(great_day, anchor)

    assert line.steps[0] == Step("scheme", 140, 145, "one_row_cap")
    assert loads(line) == [("warm_up", 1, 80), ("working", 1, 145), ("working", 3, 125)]
    assert line.change == "1×3 @8 + 3×5 @8: 140 → 145"
    assert line.flags == ()


def test_the_top_is_the_e1rm_model_load_rounded_down() -> None:
    line = bench(an_exposure("2026-10-26", (140, 3, 7), (120, 5, 7)))

    assert line.steps[0] == Step("scheme", 140, 140, "e1rm")
    assert loads(line)[1:] == [("working", 1, 140), ("working", 3, 120)]
    assert line.change == "held"


def test_with_no_e1rm_in_42_days_it_holds_the_anchor_top_and_warns_no_e1rm() -> None:
    line = bench(an_exposure("2026-09-01", (140, 3, 8), (120, 5, 7)))

    assert loads(line)[1:] == [("working", 1, 140), ("working", 3, 120)]
    assert [(f.code, dict(f.params)) for f in line.flags] == [
        ("no_e1rm", {"exercise_id": "bb_bench_press", "scheme": "top_backoff"})
    ]
    assert line.change == "held"


def test_one_bad_day_never_lowers_the_top_set() -> None:
    good_day = an_exposure("2026-10-19", (140, 3, 8), (120, 5, 7), workout_id="w-1")
    bad_day = an_exposure("2026-10-26", (140, 3, 10), (120, 5, 9), workout_id="w-2")

    line = bench(good_day, bad_day)

    assert loads(line)[1:] == [("working", 1, 140), ("working", 3, 120)]


def test_a_start_load_is_the_top_set_and_the_back_offs_derive_from_it() -> None:
    line = prescribe(
        a_request(
            a_line(
                "bb_bench_press",
                *BENCH.sets[1:],
                scheme="top_backoff",
                pct_of_top=85,
                start_load=100,
            )
        )
    ).lines[0]

    assert loads(line) == [("working", 1, 100), ("working", 3, 85)]
    assert line.derived_from == "start_load"
