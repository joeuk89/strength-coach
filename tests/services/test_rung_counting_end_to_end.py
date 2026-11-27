import datetime

from support.clock import FixedClock, at
from support.fake_hevy import FakeHevy
from support.history import a_logged_workout
from support.instances import a_coach_toml
from support.kit_fixtures import kit_files
from support.program_drafts import a_draft, a_ladder_line, a_rung, a_session, toml
from support.programs import HOME, the_worked_store

from coach.core.config import Config, parse_config
from coach.core.mirror import RoutineExercise
from coach.core.units import KG_PER_LB
from coach.services.plan_apply import apply, dry_run
from coach.services.plan_draft import plan_draft
from coach.services.program import adopt
from coach.services.record import record
from coach.store import exercises
from coach.store.connection import Connection

VEST_TEMPLATE = "VEST-0001"
VEST_GYM = {
    "kind": "grid",
    "implements": {"barbell": "bar", "vest": "vest"},
    "implement": {
        "bar": {"increment": 2.5, "base": 20},
        "vest": {"rack": [5, 10, 15, 20, 25, 30]},
    },
}
WEIGHTED_NEGATIVE = {
    "name": "Weighted Negative",
    "load_mode": "total",
    "equipment_kind": "vest",
    "pattern": "vertical_pull",
    "muscles": {"primary": ["lats"], "secondary": ["biceps"]},
}
REPS = [{"count": 3, "reps": 4, "rpe": 8}]
THREE_LOADED_RUNGS = a_ladder_line(
    "weighted_negative",
    a_rung(sets=REPS, cues="lower for 4 s"),
    a_rung("weighted_negative", sets=REPS, cues="lower for 8 s", start_load=20),
    a_rung("weighted_negative", sets=REPS, cues="lower for 10 s", start_load=30),
) | {"start_load": 10}
STEP_BACK_WEEK = datetime.date(2026, 11, 2)
BACK_ON_THE_RUNG = datetime.date(2026, 11, 9)


def a_config(*, hevy: bool = True) -> Config:
    document = a_coach_toml(pin="0.3.0", hevy=hevy, location={"home": HOME, "gym": VEST_GYM})
    document["athlete"] |= {"units": "lb"}
    return parse_config(document)


def on(day: str) -> FixedClock:
    return FixedClock(at(datetime.date.fromisoformat(day)))


def negatives_at(conn: Connection, day: str, pounds: float) -> None:
    sets = ((pounds * KG_PER_LB, 4, 8),) * 3
    a_logged_workout(conn, f"h-{day}", day, (VEST_TEMPLATE, sets))


def standing_on_rung_three_after_a_layoff() -> Connection:
    conn = the_worked_store()
    session = a_session("pull", THREE_LOADED_RUNGS, location="gym")
    draft = toml(a_draft(session, exercise={"weighted_negative": WEIGHTED_NEGATIVE}))
    adopt(
        conn,
        draft,
        file="d.toml",
        config=a_config(hevy=False),
        kits=(kit_files(),),
        clock=on("2026-08-01"),
    )
    with conn:
        exercises.update(conn, "weighted_negative", {"hevy_template_id": VEST_TEMPLATE})
    record(
        conn,
        b'[[decision]]\nkind = "ladder_rung"\nsession = "pull"\nexercise = "weighted_negative"\n'
        b'rung = 3\nbecause = "progress"\ntext = "Clean sets; the athlete said yes."\n',
        file="decision.toml",
        clock=on("2026-09-01"),
    )
    negatives_at(conn, "2026-09-07", 30)
    negatives_at(conn, "2026-09-14", 30)
    return conn


def approved(conn: Connection, hevy: FakeHevy, week: datetime.date, clock: FixedClock) -> None:
    text = plan_draft(conn, config=a_config(), kits=(kit_files(),), clock=clock, week=week).text
    data = text.replace("confirmed = false", "confirmed = true").encode()
    found = dry_run(
        conn, data, file="plan.toml", config=a_config(), kits=(kit_files(),), clock=clock
    )
    apply(
        conn,
        hevy,
        data,
        file="plan.toml",
        expect=found.write_plan_hash,
        config=a_config(),
        kits=(kit_files(),),
        clock=clock,
    )


def the_negatives_on(hevy: FakeHevy) -> RoutineExercise:
    [routine] = hevy.routines()
    return next(e for e in routine.exercises if e.hevy_template_id == VEST_TEMPLATE)


def pounds(exercise: RoutineExercise) -> list[float]:
    return [round((s.weight_kg or 0) / KG_PER_LB, 1) for s in exercise.sets]


def test_after_a_step_back_week_logged_at_rung_ones_load_rung_three_is_prescribed_at_30() -> None:
    conn = standing_on_rung_three_after_a_layoff()
    hevy = FakeHevy(on("2026-10-30"))

    approved(conn, hevy, STEP_BACK_WEEK, on("2026-10-30"))
    step_back = pounds(the_negatives_on(hevy))
    negatives_at(conn, STEP_BACK_WEEK.isoformat(), 10)
    approved(conn, hevy, BACK_ON_THE_RUNG, on("2026-11-06"))

    assert step_back == [5, 5]
    assert pounds(the_negatives_on(hevy)) == [30, 30, 30]
