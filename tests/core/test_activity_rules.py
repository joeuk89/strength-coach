import datetime

from coach.core.activity_rules import (
    LoggedActivity,
    activity_cap_exceeded,
    quality_stack,
    run_spikes,
    status_span_drops,
)
from coach.core.prescription import (
    LinePrescription,
    PlannedSession,
    PrescribedGroup,
    SessionPrescription,
    StatusSpan,
)

MONDAY = datetime.date(2026, 11, 2)


def day(n: int) -> datetime.date:
    return MONDAY + datetime.timedelta(days=n)


def an_activity(
    id_: str, on: datetime.date, *, rpe: float = 6, distance_km: float | None = None
) -> LoggedActivity:
    return LoggedActivity(id_, on, "run", 30, rpe, rpe >= 7, distance_km)


def test_three_quality_activities_in_a_week_exceed_the_cap_of_two() -> None:
    activities = [
        an_activity("ac-0001", day(0), rpe=8),
        an_activity("ac-0002", day(2), rpe=7),
        an_activity("ac-0003", day(4), rpe=9),
    ]

    flag = activity_cap_exceeded(activities, MONDAY)

    assert flag is not None
    assert flag.params == {
        "cap": 2,
        "observed": 3,
        "activities": ["ac-0001", "ac-0002", "ac-0003"],
    }


def test_two_quality_activities_and_an_easy_one_are_inside_the_cap() -> None:
    activities = [
        an_activity("ac-0001", day(0), rpe=8),
        an_activity("ac-0002", day(2), rpe=7),
        an_activity("ac-0003", day(4)),
    ]

    assert activity_cap_exceeded(activities, MONDAY) is None


def test_a_quality_bout_in_another_week_does_not_count() -> None:
    activities = [
        an_activity("ac-0001", day(-1), rpe=8),
        an_activity("ac-0002", day(2), rpe=7),
        an_activity("ac-0003", day(4), rpe=9),
    ]

    assert activity_cap_exceeded(activities, MONDAY) is None


HISTORY = [
    an_activity("ac-0001", day(-20), distance_km=10),
    an_activity("ac-0002", day(-10), distance_km=8),
]


def test_a_run_1_2_times_the_30_day_longest_with_14_days_of_history_spikes() -> None:
    run = an_activity("ac-0003", day(1), distance_km=12)

    [flag] = run_spikes([*HISTORY, run], since=MONDAY)

    assert flag.scope.workout_id == "ac-0003"
    assert flag.params == {"distance": 12, "longest_30_days": 10, "ratio": 1.2}


def test_without_14_days_of_history_a_run_is_not_judged() -> None:
    recent = [an_activity("ac-0001", day(-10), distance_km=10)]

    assert run_spikes([*recent, an_activity("ac-0003", day(1), distance_km=12)], since=MONDAY) == []


def test_a_run_1_1_times_the_longest_is_no_spike() -> None:
    assert (
        run_spikes([*HISTORY, an_activity("ac-0003", day(1), distance_km=11)], since=MONDAY) == []
    )


def test_a_run_just_over_1_1_times_the_longest_spikes_before_rounding() -> None:
    run = an_activity("ac-0003", day(1), distance_km=11.04)

    [flag] = run_spikes([*HISTORY, run], since=MONDAY)

    assert flag.params["ratio"] == 1.1


def a_line(exercise: str, groups: tuple[PrescribedGroup, ...]) -> LinePrescription:
    return LinePrescription(exercise, "top_backoff", groups, None, (), (), "")


def a_session(
    session_id: str,
    on: datetime.date,
    kind: str,
    *groups: PrescribedGroup,
    exercise: str = "bb_back_squat",
    cadence: str = "weekly",
) -> SessionPrescription:
    planned = PlannedSession(session_id, on, "home", kind, (), cadence)
    return SessionPrescription(planned, (a_line(exercise, groups),) if groups else ())


HEAVY = PrescribedGroup("working", 4, reps=5, rpe=8)
PATTERNS = {"bb_back_squat": "squat", "db_curl": "elbow_flexion"}


def test_a_quality_conditioning_session_the_day_before_a_heavy_squat_suggests_a_drop() -> None:
    sessions = [
        a_session("intervals", day(0), "conditioning"),
        a_session("lower", day(1), "lifting", HEAVY),
    ]

    [flag] = quality_stack(sessions, quality={"intervals"}, patterns=PATTERNS)

    assert flag.code == "session_drop_suggested"
    assert flag.scope.session_id == "intervals"
    assert flag.params == {
        "reason": "quality_stack",
        "evidence": ["planned_session:2026-11-02/intervals", "planned_session:2026-11-03/lower"],
    }


def test_an_easy_conditioning_session_stacks_with_nothing() -> None:
    sessions = [
        a_session("intervals", day(0), "conditioning"),
        a_session("lower", day(1), "lifting", HEAVY),
    ]

    assert quality_stack(sessions, quality=set(), patterns=PATTERNS) == []


def test_a_light_squat_session_is_not_heavy() -> None:
    light = PrescribedGroup("working", 3, reps=10, rpe=6)
    sessions = [
        a_session("intervals", day(0), "conditioning"),
        a_session("lower", day(1), "lifting", light),
    ]

    assert quality_stack(sessions, quality={"intervals"}, patterns=PATTERNS) == []


def test_six_reps_with_no_rpe_is_heavy() -> None:
    unrated = PrescribedGroup("working", 3, reps=6)
    sessions = [
        a_session("intervals", day(0), "conditioning"),
        a_session("lower", day(1), "lifting", unrated),
    ]

    assert len(quality_stack(sessions, quality={"intervals"}, patterns=PATTERNS)) == 1


def test_quality_conditioning_on_the_day_of_any_lifting_session_stacks() -> None:
    curls = PrescribedGroup("working", 3, reps=12, rpe=7)
    sessions = [
        a_session("intervals", day(2), "conditioning"),
        a_session("arms", day(2), "lifting", curls, exercise="db_curl"),
    ]

    [flag] = quality_stack(sessions, quality={"intervals"}, patterns=PATTERNS)

    assert flag.rn == "rn:concurrent-training.4"


def test_quality_conditioning_two_days_before_a_heavy_squat_is_fine() -> None:
    sessions = [
        a_session("intervals", day(0), "conditioning"),
        a_session("lower", day(2), "lifting", HEAVY),
    ]

    assert quality_stack(sessions, quality={"intervals"}, patterns=PATTERNS) == []


def test_standing_quality_conditioning_does_not_stack_with_a_monday_lifting_session() -> None:
    sessions = [
        a_session("intervals", MONDAY, "conditioning", cadence="standing"),
        a_session("lower", MONDAY, "lifting", HEAVY),
    ]

    assert quality_stack(sessions, quality={"intervals"}, patterns=PATTERNS) == []


def test_standing_quality_conditioning_does_not_stack_before_a_heavy_tuesday_squat() -> None:
    sessions = [
        a_session("intervals", MONDAY, "conditioning", cadence="standing"),
        a_session("lower", day(1), "lifting", HEAVY),
    ]

    assert quality_stack(sessions, quality={"intervals"}, patterns=PATTERNS) == []


def test_weekly_quality_conditioning_does_not_stack_with_a_standing_lifting_session() -> None:
    sessions = [
        a_session("intervals", MONDAY, "conditioning"),
        a_session("core-a", MONDAY, "lifting", HEAVY, cadence="standing"),
    ]

    assert quality_stack(sessions, quality={"intervals"}, patterns=PATTERNS) == []


def test_a_core_session_on_an_ill_day_suggests_a_drop() -> None:
    sessions = [
        a_session("lower", day(1), "lifting", HEAVY),
        a_session("upper", day(3), "lifting", HEAVY),
    ]

    [flag] = status_span_drops(sessions, [StatusSpan("ill", day(0), day(2))])

    assert flag.scope.session_id == "lower"
    assert flag.params == {"reason": "status_span", "evidence": []}
