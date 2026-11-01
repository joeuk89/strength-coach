import datetime

from coach.core.exposure import (
    Annotation,
    ExposureSet,
    LibraryEntry,
    LoggedWorkout,
    Matched,
    resolve,
)
from coach.core.load import Load
from coach.core.log import StoredSet

BENCH = "79D0BB3A"
SQUAT = "D04AC939"
LIBRARY = {
    BENCH: LibraryEntry("bb_bench_press", "total"),
    SQUAT: LibraryEntry("bb_back_squat", "total"),
    "DB000001": LibraryEntry("db_bench_press", "per_hand_x2"),
}


def a_set(
    position: int,
    template: str = BENCH,
    *,
    kg: float | None = 100,
    reps: int | None = 5,
    rpe: float | None = 8,
    set_type: str = "working",
) -> StoredSet:
    return StoredSet(position, template, None, set_type, kg, reps, None, None, rpe, None)


def a_workout(*sets: StoredSet, id_: str = "w1", match: Matched | None = None) -> LoggedWorkout:
    return LoggedWorkout(id_, datetime.date(2026, 10, 26), sets, match)


def an_annotation(id_: str, kind: str, target: str, **params: object) -> Annotation:
    return Annotation(id_, kind, target, params)


def test_each_exercise_in_a_workout_with_a_working_set_is_one_exposure() -> None:
    workout = a_workout(
        a_set(0, kg=60, set_type="warm_up"),
        a_set(1),
        a_set(2, SQUAT, kg=140),
        a_set(3, reps=4, rpe=9),
        match=Matched("push_a"),
    )

    bench, squat = resolve([workout], LIBRARY, [], "kg")

    assert bench.ref == "exposure:w1/bb_bench_press"
    assert bench.session_id == "push_a"
    assert bench.sets == (
        ExposureSet(1, "working", Load(100, "total"), 5, 8),
        ExposureSet(3, "working", Load(100, "total"), 4, 9),
    )
    assert squat.exercise_id == "bb_back_squat"


def test_activation_and_warm_up_sets_alone_yield_no_exposure() -> None:
    workout = a_workout(a_set(0, set_type="warm_up"), a_set(1, set_type="activation"))

    assert resolve([workout], LIBRARY, [], "kg") == ()


def test_a_test_set_rides_on_the_exposure_but_is_not_working() -> None:
    (exposure,) = resolve(
        [a_workout(a_set(0, rpe=9, reps=1, set_type="test"), a_set(1))], LIBRARY, [], "kg"
    )

    assert [s.set_type for s in exposure.sets] == ["test", "working"]
    assert len(exposure.working) == 1


def test_a_set_whose_template_no_exercise_carries_is_skipped() -> None:
    assert resolve([a_workout(a_set(0, "CUSTOM01"))], LIBRARY, [], "kg") == ()


def test_the_exercise_s_load_mode_converts_the_logged_weight() -> None:
    (exposure,) = resolve([a_workout(a_set(0, "DB000001", kg=50))], LIBRARY, [], "lb")

    assert exposure.sets[0].load == Load(55.12, "per_hand_x2")


def test_void_on_a_workout_drops_every_exposure_in_it() -> None:
    workout = a_workout(a_set(0), a_set(1, SQUAT))

    assert resolve([workout], LIBRARY, [an_annotation("a-0001", "void", "workout:w1")], "kg") == ()


def test_void_on_one_exercise_drops_that_exposure_only() -> None:
    workout = a_workout(a_set(0), a_set(1, SQUAT))
    void = an_annotation("a-0001", "void", "workout:w1/bb_bench_press")

    (squat,) = resolve([workout], LIBRARY, [void], "kg")

    assert squat.exercise_id == "bb_back_squat"


def test_discount_on_one_set_drops_that_set_and_names_the_annotation() -> None:
    discount = an_annotation("a-0001", "discount", "workout:w1/bb_bench_press", position=1)

    (exposure,) = resolve([a_workout(a_set(0), a_set(1, kg=200))], LIBRARY, [discount], "kg")

    assert [s.position for s in exposure.sets] == [0]
    assert exposure.annotations == ("a-0001",)


def test_discount_on_the_exercise_drops_the_exposure() -> None:
    discount = an_annotation("a-0001", "discount", "workout:w1/bb_bench_press")

    assert resolve([a_workout(a_set(0))], LIBRARY, [discount], "kg") == ()


def test_repair_corrects_one_field_of_one_set() -> None:
    repair = an_annotation(
        "a-0001", "repair", "workout:w1/bb_bench_press", position=0, field="weight_kg", value=105
    )

    (exposure,) = resolve([a_workout(a_set(0, kg=1050))], LIBRARY, [repair], "kg")

    assert exposure.sets[0].load == Load(105, "total")


def test_load_mode_reads_the_exposure_under_another_mode() -> None:
    mode = an_annotation("a-0001", "load_mode", "workout:w1/db_bench_press", load_mode="total")

    (exposure,) = resolve([a_workout(a_set(0, "DB000001", kg=50))], LIBRARY, [mode], "kg")

    assert exposure.sets[0].load == Load(50, "total")


def test_annotations_apply_in_id_order() -> None:
    first = an_annotation(
        "a-0002", "repair", "workout:w1/bb_bench_press", position=0, field="reps", value=6
    )
    second = an_annotation(
        "a-0010", "repair", "workout:w1/bb_bench_press", position=0, field="reps", value=7
    )

    (exposure,) = resolve([a_workout(a_set(0))], LIBRARY, [second, first], "kg")

    assert exposure.sets[0].reps == 7
    assert exposure.annotations == ("a-0002", "a-0010")


def test_an_annotation_on_another_workout_or_a_planned_session_changes_nothing() -> None:
    others = [
        an_annotation("a-0001", "void", "workout:w2"),
        an_annotation("a-0002", "trained_unlogged", "planned_session:2026-10-26/push_a"),
    ]

    (exposure,) = resolve([a_workout(a_set(0))], LIBRARY, others, "kg")

    assert exposure.annotations == ()
