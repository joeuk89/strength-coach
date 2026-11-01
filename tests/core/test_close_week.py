import datetime

from support.exposures import an_exposure

from coach.core.closed_week.close import WeekFacts, close_week
from coach.core.closed_week.match import WeekWorkout
from coach.core.closed_week.sessions import PlannedWork, TargetSet
from coach.core.prescription import PlannedSession

MONDAY = datetime.date(2026, 11, 2)
SETS = (TargetSet(6, 8),) * 3
MUSCLES = {"bb_bench_press": {"primary": ["chest"], "secondary": ["triceps"]}}


def planned(session_id: str, n: int, kind: str = "lifting", **work: bool) -> PlannedWork:
    on = MONDAY + datetime.timedelta(days=n)
    targets = {"bb_bench_press": SETS} if kind == "lifting" else {}
    return PlannedWork(PlannedSession(session_id, on, "home", kind, ()), targets, **work)


def bench(id_: str, n: int) -> WeekWorkout:
    on = MONDAY + datetime.timedelta(days=n)
    exposure = an_exposure(on.isoformat(), *[(60, 6, 8)] * 3, workout_id=id_)
    return WeekWorkout(id_, on, (exposure,))


def test_matched_sessions_that_pass_the_gate_make_the_week_hard_with_its_dose() -> None:
    facts = WeekFacts(
        MONDAY,
        (planned("push", 0), planned("pull", 2)),
        (bench("h-1", 0), bench("h-2", 2)),
        muscles=MUSCLES,
        dose_target=10,
    )

    week = close_week(facts)

    assert week.kind == "hard"
    assert [s.workout_id for s in week.sessions] == ["h-1", "h-2"]
    assert week.dose == {"chest": 6, "triceps": 3}
    assert week.dose_target == 10


def test_a_dropped_core_session_is_a_miss_and_takes_no_workout() -> None:
    facts = WeekFacts(MONDAY, (planned("push", 0, dropped=True),), (bench("h-1", 0),))

    [session] = close_week(facts).sessions

    assert (session.trained, session.in_adherence, session.workout_id) == (False, True, None)


def test_a_conditioning_or_practice_workout_delivers_no_dose() -> None:
    facts = WeekFacts(
        MONDAY, (planned("hang", 0, "practice"),), (bench("h-1", 0),), muscles=MUSCLES
    )

    assert close_week(facts).dose == {}


def test_an_unmatched_lifting_workout_still_delivers_dose() -> None:
    facts = WeekFacts(MONDAY, (), (bench("h-1", 3),), muscles=MUSCLES)

    week = close_week(facts)

    assert (week.kind, week.dose) == ("partial", {"chest": 3, "triceps": 1.5})


def test_a_trained_coach_led_session_delivers_its_estimated_sets() -> None:
    facts = WeekFacts(
        MONDAY,
        (planned("pt", 1, "coach_led"),),
        (WeekWorkout("w-1", MONDAY + datetime.timedelta(days=1)),),
        claims={"w-1": (MONDAY + datetime.timedelta(days=1), "pt")},
        estimated={"pt": {"lats": 4}},
    )

    week = close_week(facts)

    assert (week.kind, week.dose) == ("hard", {"lats": 4})


def test_trained_unlogged_and_cancelled_annotations_count_by_their_planned_session() -> None:
    push, pull = planned("push", 0), planned("pull", 2)
    facts = WeekFacts(
        MONDAY,
        (push, pull),
        trained_unlogged=frozenset({push.ref}),
        cancelled=frozenset({pull.ref}),
    )

    first, second = close_week(facts).sessions

    assert (first.trained, second.in_adherence) == (True, False)
