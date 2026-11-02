import datetime
from collections.abc import Mapping

from support.exposures import an_exposure

from coach.core.closed_week.close import WeekFacts, close_week
from coach.core.closed_week.match import WeekWorkout
from coach.core.closed_week.sessions import PlannedWork, TargetSet
from coach.core.prescription import PlannedSession
from coach.core.program.form import LiftDose

MONDAY = datetime.date(2026, 11, 2)
SETS = (TargetSet(6, 8),) * 3
MUSCLES = {"bb_bench_press": {"primary": ["chest"], "secondary": ["triceps"]}}


def planned(
    session_id: str, n: int, kind: str = "lifting", *, dropped: bool = False
) -> PlannedWork:
    on = MONDAY + datetime.timedelta(days=n)
    targets = {"bb_bench_press": SETS} if kind == "lifting" else {}
    return PlannedWork(PlannedSession(session_id, on, "home", kind, ()), targets, dropped=dropped)


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


def test_a_manual_coach_led_workout_on_a_wednesday_trains_its_standing_session() -> None:
    wednesday = MONDAY + datetime.timedelta(days=2)
    pt = PlannedWork(PlannedSession("pt", MONDAY, "gym", "coach_led", (), "standing"))
    facts = WeekFacts(
        MONDAY, (pt,), (WeekWorkout("m-1", wednesday),), claims={"m-1": (wednesday, "pt")}
    )

    week = close_week(facts)

    assert [(s.trained, s.workout_id) for s in week.sessions] == [(True, "m-1")]
    assert week.kind == "hard"


def test_a_rehab_workout_counts_only_its_sets_logged_above_rpe_5() -> None:
    def rehab_workout(id_: str, rpe: float | None) -> WeekWorkout:
        exposure = an_exposure(MONDAY.isoformat(), (20, 15, rpe), (20, 15, None), workout_id=id_)
        return WeekWorkout(id_, MONDAY, (exposure,))

    def dose(rpe: float | None) -> Mapping[str, float]:
        facts = WeekFacts(
            MONDAY, (planned("knee", 0, "rehab"),), (rehab_workout("h-1", rpe),), muscles=MUSCLES
        )
        return close_week(facts).dose

    assert dose(None) == {}
    assert dose(6) == {"chest": 1, "triceps": 0.5}


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


PULL_UP_DOSE = {"pull_up": LiftDose(8, ("negative_pull_up", "band_pull_up"))}


def pulls(id_: str, n: int, *counts: tuple[str, int, float | None]) -> WeekWorkout:
    on = MONDAY + datetime.timedelta(days=n)
    exposures = tuple(
        an_exposure(on.isoformat(), *[(None, 5, rpe)] * sets, workout_id=id_, exercise_id=ex)
        for ex, sets, rpe in counts
    )
    return WeekWorkout(id_, on, exposures)


def test_a_lifts_weekly_figure_adds_the_hard_sets_of_its_counted_variants() -> None:
    workout = pulls(
        "h-1", 2, ("pull_up", 1, 9), ("negative_pull_up", 3, 8), ("band_pull_up", 7, None)
    )

    week = close_week(WeekFacts(MONDAY, (), (workout,), lift_dose=PULL_UP_DOSE))

    assert week.lift_dose == {"pull_up": 11}
    assert week.lift_dose_target == {"pull_up": 8}


def test_an_easy_set_or_a_rehab_negative_at_rpe_5_adds_nothing_to_the_lift() -> None:
    lifting = pulls("h-1", 2, ("pull_up", 2, 8), ("negative_pull_up", 1, 4))
    rehab = pulls("h-2", 0, ("negative_pull_up", 2, 5), ("band_pull_up", 1, 6))
    facts = WeekFacts(
        MONDAY, (planned("elbow", 0, "rehab"),), (lifting, rehab), lift_dose=PULL_UP_DOSE
    )

    assert close_week(facts).lift_dose == {"pull_up": 3}


def test_a_lift_with_no_hard_sets_reads_0_and_a_coach_led_estimate_adds_nothing() -> None:
    pt = WeekWorkout("w-1", MONDAY + datetime.timedelta(days=1))
    facts = WeekFacts(
        MONDAY,
        (planned("pt", 1, "coach_led"),),
        (pt,),
        claims={"w-1": (MONDAY + datetime.timedelta(days=1), "pt")},
        estimated={"pt": {"lats": 4}},
        lift_dose=PULL_UP_DOSE,
    )

    assert close_week(facts).lift_dose == {"pull_up": 0}
