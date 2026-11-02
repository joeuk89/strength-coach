import datetime

from support.exposures import an_exposure

from coach.core.closed_week.dose import (
    delivered_dose,
    dose_under_target,
    lift_dose_under_target,
    minimum_week_floor,
    session_dose_high,
    trailing_mean,
)
from coach.core.closed_week.kind import WeekKind
from coach.core.closed_week.week import ClosedWeek
from coach.core.prescription import (
    LinePrescription,
    PlannedSession,
    PrescribedGroup,
    SessionPrescription,
)

MONDAY = datetime.date(2026, 12, 7)
MUSCLES = {
    "bb_bench_press": {"primary": ["chest"], "secondary": ["triceps", "front_delts"]},
    "db_fly": {"primary": ["chest"], "secondary": []},
}


def test_a_hard_set_counts_1_for_a_direct_muscle_and_half_for_an_indirect_one() -> None:
    bench = an_exposure("2026-12-01", (60, 8, 8), (60, 8, 5), (60, 8, None))

    assert delivered_dose([bench], MUSCLES) == {"chest": 2, "triceps": 1, "front_delts": 1}


def test_a_coach_led_sessions_estimated_sets_count_as_direct_sets() -> None:
    assert delivered_dose([], MUSCLES, [{"lats": 4}]) == {"lats": 4}


def a_week(weeks_ago: int, chest: float, kind: WeekKind = "hard") -> ClosedWeek:
    monday = MONDAY - datetime.timedelta(weeks=weeks_ago + 1)
    return ClosedWeek(monday, kind, dose={"chest": chest}, dose_target=10)


def test_under_target_in_three_of_the_trailing_four_ordinary_weeks_warns_on_the_plan() -> None:
    weeks = [a_week(3, 8), a_week(2, 12), a_week(1, 9), a_week(0, 9.5)]

    flag = dose_under_target(weeks, MONDAY, ("chest",))

    assert flag is not None and flag.key == "dose_under_target@week:2026-12-07"
    assert flag.params == {"muscle": "chest", "target": 10, "weekly_figures": [8, 12, 9, 9.5]}


def test_two_of_four_or_a_disrupted_week_under_target_is_no_warning() -> None:
    two = [a_week(3, 8), a_week(2, 12), a_week(1, 10), a_week(0, 9)]
    light = [a_week(3, 12), a_week(2, 8, "light"), a_week(1, 10), a_week(0, 9)]

    assert dose_under_target(two, MONDAY, ("chest",)) is None
    assert dose_under_target(light, MONDAY, ("chest",)) is None


def test_the_trailing_mean_reads_the_last_four_ordinary_weeks() -> None:
    weeks = [a_week(4, 0), a_week(3, 8), a_week(2, 12, "light"), a_week(2, 10), a_week(1, 9)]

    assert trailing_mean(weeks, "chest") == (0 + 8 + 10 + 9) / 4


def bench_session(*groups: PrescribedGroup) -> SessionPrescription:
    planned = PlannedSession("push", MONDAY, "home", "lifting", ())
    line = LinePrescription("bb_bench_press", "linear", groups, None, (), (), "")
    fly = LinePrescription(
        "db_fly", "linear", (PrescribedGroup("working", 6, rpe=8),), None, (), (), ""
    )
    return SessionPrescription(planned, (line, fly))


def test_a_planned_session_over_11_fractional_sets_for_a_muscle_warns() -> None:
    high = bench_session(PrescribedGroup("working", 6, rpe=8))
    warmed = bench_session(PrescribedGroup("warm_up", 2), PrescribedGroup("working", 5, rpe=8))

    flag = session_dose_high(high, MUSCLES)

    assert flag is not None and flag.key == "session_dose_high@session:2026-12-07/push"
    assert flag.params == {"planned_sets": 12, "ceiling": 11}
    assert session_dose_high(warmed, MUSCLES) is None


def test_a_minimum_week_keeps_two_hard_sets_of_each_priority_lift() -> None:
    one_set = bench_session(PrescribedGroup("working", 1, rpe=8))
    two_sets = bench_session(PrescribedGroup("working", 2, rpe=8))

    flag = minimum_week_floor([one_set], ("push",), ("bb_bench_press",), MONDAY)

    assert flag is not None and flag.params == {
        "priority_lift": "bb_bench_press",
        "kept_sessions": ["push"],
    }
    assert minimum_week_floor([two_sets], ("push",), ("bb_bench_press",), MONDAY) is None


PULL_UP_COUNTS = {"pull_up": ("negative_pull_up", "band_pull_up")}


def a_pull_up_week(weeks_ago: int, figure: int, kind: WeekKind = "hard") -> ClosedWeek:
    monday = MONDAY - datetime.timedelta(weeks=weeks_ago + 1)
    return ClosedWeek(monday, kind, lift_dose={"pull_up": figure}, lift_dose_target={"pull_up": 8})


def test_a_lift_at_its_target_with_its_variants_every_week_raises_nothing() -> None:
    weeks = [a_pull_up_week(n, 11) for n in (3, 2, 1, 0)]

    assert lift_dose_under_target(weeks, MONDAY, PULL_UP_COUNTS) is None


def test_a_lift_under_its_target_in_three_of_four_ordinary_weeks_warns_with_its_variants() -> None:
    weeks = [a_pull_up_week(4, 1), a_pull_up_week(3, 11), a_pull_up_week(2, 2, "light")]
    weeks += [a_pull_up_week(1, 7), a_pull_up_week(0, 5)]

    flag = lift_dose_under_target(weeks, MONDAY, PULL_UP_COUNTS)

    assert flag is not None and flag.key == "lift_dose_under_target@week:2026-12-07"
    assert flag.params == {
        "exercise_id": "pull_up",
        "target": 8,
        "weekly_figures": [1, 11, 7, 5],
        "counted": ["negative_pull_up", "band_pull_up"],
    }


def test_weeks_before_the_lift_had_a_target_never_count_against_it() -> None:
    untargeted = ClosedWeek(MONDAY - datetime.timedelta(weeks=4), "hard")
    weeks = [untargeted, a_pull_up_week(2, 1), a_pull_up_week(1, 1)]

    assert lift_dose_under_target(weeks, MONDAY, PULL_UP_COUNTS) is None


def test_a_lift_the_version_in_force_no_longer_targets_raises_nothing() -> None:
    weeks = [
        ClosedWeek(
            MONDAY - datetime.timedelta(weeks=n + 1),
            "hard",
            lift_dose={"bb_back_squat": 0},
            lift_dose_target={"bb_back_squat": 8},
        )
        for n in (3, 2, 1, 0)
    ]

    assert lift_dose_under_target(weeks, MONDAY, PULL_UP_COUNTS) is None


def pull_session(*lines: tuple[str, int]) -> SessionPrescription:
    planned = PlannedSession("pull", MONDAY, "home", "lifting", ())
    return SessionPrescription(
        planned,
        tuple(
            LinePrescription(
                exercise, "linear", (PrescribedGroup("working", sets, rpe=8),), None, (), (), ""
            )
            for exercise, sets in lines
        ),
    )


def test_a_counted_variants_planned_hard_sets_keep_the_lifts_minimum_week_floor() -> None:
    bands = pull_session(("band_pull_up", 2))
    one_band = pull_session(("band_pull_up", 1))

    kept = minimum_week_floor([bands], ("pull",), ("pull_up",), MONDAY, PULL_UP_COUNTS)
    short = minimum_week_floor([one_band], ("pull",), ("pull_up",), MONDAY, PULL_UP_COUNTS)

    assert kept is None
    assert short is not None and short.params["priority_lift"] == "pull_up"
