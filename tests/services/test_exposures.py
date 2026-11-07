import datetime

import pytest
from support.history import a_logged_workout, a_status_span, an_annotation
from support.ledger import a_store, an_exercise
from support.scenarios import a_session

from coach.core.anchor import AnchorExposure, StartLoad, anchor
from coach.core.errors import Invalid
from coach.services.history import days_off_for_line, read_history
from coach.services.query import exposures
from coach.store.connection import Connection

BENCH = "79D0BB3A"
SQUAT = "D04AC939"
PLANNED = datetime.date(2026, 11, 2)


def a_library() -> Connection:
    conn = a_store()
    an_exercise(conn, "bb_bench_press", hevy_template_id=BENCH)
    an_exercise(conn, "bb_back_squat", hevy_template_id=SQUAT, pattern="squat")
    return conn


def bench_anchor(conn: Connection) -> AnchorExposure | StartLoad:
    history = read_history(conn, "kg")
    return anchor(
        history.exposures,
        exercise_id="bb_bench_press",
        session_id="push_a",
        on=PLANNED,
        start_load=None,
    )


def test_the_view_shows_each_exposure_newest_first_with_its_e1rm() -> None:
    conn = a_library()
    a_logged_workout(conn, "h-1", "2026-10-19", (BENCH, ((100, 5, 8), (100, 5, 9))))
    a_logged_workout(
        conn, "h-2", "2026-10-26", (BENCH, ((102.5, 5, None),)), (SQUAT, ((140, 5, 8),))
    )

    result = exposures(conn, exercises=("bb_bench_press",), since=None, last=10, units="kg")

    assert result.rows == [
        {
            "exposure": "exposure:h-2/bb_bench_press",
            "exercise": "bb_bench_press",
            "date": "2026-10-26",
            "session": None,
            "load": 102.5,
            "load_mode": "total",
            "reps": [5],
            "rpe": [None],
            "e1rm": 119.58,
            "e1rm_lower_bound": True,
            "annotations": [],
        },
        {
            "exposure": "exposure:h-1/bb_bench_press",
            "exercise": "bb_bench_press",
            "date": "2026-10-19",
            "session": None,
            "load": 100,
            "load_mode": "total",
            "reps": [5, 5],
            "rpe": [8, 9],
            "e1rm": 123.33,
            "e1rm_lower_bound": False,
            "annotations": [],
        },
    ]
    assert (result.count, result.truncated) == (2, False)


def test_each_row_names_its_exercise_beside_the_exposure() -> None:
    conn = a_library()
    a_logged_workout(conn, "h-1", "2026-10-26", (BENCH, ((100, 5, 8),)), (SQUAT, ((140, 5, 8),)))

    result = exposures(conn, exercises=(), since=None, last=10, units="kg")

    assert [(row["exposure"], row["exercise"]) for row in result.rows] == [
        ("exposure:h-1/bb_back_squat", "bb_back_squat"),
        ("exposure:h-1/bb_bench_press", "bb_bench_press"),
    ]


def test_the_view_keeps_the_last_n_and_says_more_exist() -> None:
    conn = a_library()
    for week in range(7):
        on = (datetime.date(2026, 9, 7) + datetime.timedelta(weeks=week)).isoformat()
        a_logged_workout(conn, f"h-{week}", on, (BENCH, ((100, 5, 8),)))

    result = exposures(conn, exercises=("bb_bench_press",), since=None, last=5, units="kg")

    assert [row["date"] for row in result.rows] == [
        "2026-10-19",
        "2026-10-12",
        "2026-10-05",
        "2026-09-28",
        "2026-09-21",
    ]
    assert (result.count, result.truncated) == (7, True)


def test_since_keeps_exposures_on_or_after_the_date_and_no_exercise_reads_every_one() -> None:
    conn = a_library()
    a_logged_workout(conn, "h-1", "2026-10-19", (BENCH, ((100, 5, 8),)))
    a_logged_workout(conn, "h-2", "2026-10-26", (BENCH, ((100, 5, 8),)), (SQUAT, ((140, 5, 8),)))

    result = exposures(conn, exercises=(), since=datetime.date(2026, 10, 26), last=10, units="kg")

    assert [row["exposure"] for row in result.rows] == [
        "exposure:h-2/bb_back_squat",
        "exposure:h-2/bb_bench_press",
    ]


def test_an_exercise_outside_the_library_is_refused() -> None:
    with pytest.raises(Invalid) as refused:
        exposures(a_library(), exercises=("bb_nope",), since=None, last=10, units="kg")
    assert refused.value.code == "unknown_exercise"


def test_a_void_annotation_removes_the_exposure_from_the_view_and_the_anchor() -> None:
    conn = a_library()
    a_logged_workout(conn, "h-1", "2026-10-19", (BENCH, ((100, 5, 8),)))
    a_logged_workout(conn, "h-2", "2026-10-26", (BENCH, ((150, 5, 8),)))
    an_annotation(conn, "a-0001", "void", "workout:h-2/bb_bench_press")

    view = exposures(conn, exercises=("bb_bench_press",), since=None, last=10, units="kg")

    assert [row["exposure"] for row in view.rows] == ["exposure:h-1/bb_bench_press"]
    assert bench_anchor(conn).derived_from == "exposure:h-1/bb_bench_press"


def test_a_withdrawn_void_restores_the_exposure() -> None:
    conn = a_library()
    a_logged_workout(conn, "h-1", "2026-10-19", (BENCH, ((100, 5, 8),)))
    a_logged_workout(conn, "h-2", "2026-10-26", (BENCH, ((150, 5, 8),)))
    an_annotation(conn, "a-0001", "void", "workout:h-2")
    an_annotation(conn, "a-0002", "void", "workout:h-2", withdraws="a-0001")

    view = exposures(conn, exercises=("bb_bench_press",), since=None, last=10, units="kg")

    assert [row["exposure"] for row in view.rows] == [
        "exposure:h-2/bb_bench_press",
        "exposure:h-1/bb_bench_press",
    ]
    assert bench_anchor(conn).derived_from == "exposure:h-2/bb_bench_press"


def test_the_view_names_the_annotations_applied() -> None:
    conn = a_library()
    a_logged_workout(conn, "h-1", "2026-10-19", (BENCH, ((1000, 5, 8),)))
    an_annotation(
        conn,
        "a-0001",
        "repair",
        "workout:h-1/bb_bench_press",
        position=0,
        field="weight_kg",
        value=100,
    )

    (row,) = exposures(conn, exercises=(), since=None, last=10, units="kg").rows

    assert (row["load"], row["annotations"]) == (100, ["a-0001"])


def test_a_manual_coach_led_workout_carries_its_session_into_the_anchor() -> None:
    conn = a_library()
    a_session(conn, "push_a")
    a_logged_workout(conn, "w-0001", "2026-10-12", (BENCH, ((95, 5, 8),)), session_id="push_a")
    a_logged_workout(conn, "h-1", "2026-10-26", (BENCH, ((100, 5, 8),)))

    found = bench_anchor(conn)

    assert found.derived_from == "exposure:w-0001/bb_bench_press"
    assert isinstance(found, AnchorExposure) and found.step == "same_session"


def test_a_trained_unlogged_session_resets_the_layoff_and_exposure_age_and_anchors_nothing() -> (
    None
):
    conn = a_library()
    a_session(conn, "push_a")
    for back in (25, 32, 39, 46, 53):
        on = (PLANNED - datetime.timedelta(days=back)).isoformat()
        a_logged_workout(conn, f"h-{back}", on, (BENCH, ((100, 5, 8),)))
    before = days_off_for_line(
        conn, exercise_id="bb_bench_press", session_id="push_a", on=PLANNED, units="kg"
    )
    an_annotation(conn, "a-0001", "trained_unlogged", "planned_session:2026-10-29/push_a")

    after = days_off_for_line(
        conn, exercise_id="bb_bench_press", session_id="push_a", on=PLANNED, units="kg"
    )

    assert (before.days, before.layoff, before.exposure_age) == (25, 25, 25)
    assert (after.layoff, after.exposure_age) == (4, 4)
    assert bench_anchor(conn).derived_from == "exposure:h-25/bb_bench_press"


def test_a_trained_unlogged_session_moves_the_layoff_only_for_another_session_s_lines() -> None:
    conn = a_library()
    a_session(conn, "push_a")
    a_logged_workout(conn, "h-1", "2026-10-08", (BENCH, ((100, 5, 8),)))
    an_annotation(conn, "a-0001", "trained_unlogged", "planned_session:2026-10-29/legs_a")

    found = days_off_for_line(
        conn, exercise_id="bb_bench_press", session_id="push_a", on=PLANNED, units="kg"
    )

    assert (found.layoff, found.exposure_age) == (4, 25)


def test_a_hand_entered_workout_with_no_sets_is_an_exposure_date_for_its_session() -> None:
    conn = a_library()
    a_session(conn, "push_a")
    a_logged_workout(conn, "h-1", "2026-10-08", (BENCH, ((100, 5, 8),)))
    a_logged_workout(conn, "w-0001", "2026-10-30", session_id="push_a")

    found = days_off_for_line(
        conn, exercise_id="bb_bench_press", session_id="push_a", on=PLANNED, units="kg"
    )

    assert (found.layoff, found.exposure_age) == (3, 3)
    assert bench_anchor(conn).derived_from == "exposure:h-1/bb_bench_press"


def test_a_no_training_span_never_shortens_days_off() -> None:
    conn = a_library()
    a_logged_workout(conn, "h-1", "2026-10-08", (BENCH, ((100, 5, 8),)))
    a_status_span(conn, "ss-0001", "no_training", "2026-10-10", "2026-10-30")

    found = days_off_for_line(
        conn, exercise_id="bb_bench_press", session_id="push_a", on=PLANNED, units="kg"
    )

    assert found.days == 25
