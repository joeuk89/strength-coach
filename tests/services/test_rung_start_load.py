import datetime
import tomllib
from typing import Any

import pytest
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.history import a_logged_workout
from support.instances import a_coach_toml
from support.kit_fixtures import kit_files
from support.program_drafts import a_draft, a_ladder_line, a_rung, a_session, toml
from support.programs import HOME, the_worked_store

from coach.core.config import Config, parse_config
from coach.core.errors import Invalid
from coach.core.prescription import LinePrescription
from coach.core.units import KG_PER_LB
from coach.services.plan_apply import apply, dry_run
from coach.services.plan_draft import PlanDraftResult, plan_draft
from coach.services.program import AdoptResult, adopt, show_draft
from coach.services.record import record
from coach.store import exercises
from coach.store.connection import Connection

NEXT_MONDAY = datetime.date(2026, 11, 2)
VEST_TEMPLATE = "VEST-0001"
VEST_GYM = {
    "kind": "grid",
    "implements": {"barbell": "bar", "vest": "vest"},
    "implement": {"bar": {"increment": 2.5, "base": 20}, "vest": {"rack": [5, 10, 15]}},
}
WEIGHTED_NEGATIVE = {
    "name": "Weighted Negative",
    "load_mode": "total",
    "equipment_kind": "vest",
    "pattern": "vertical_pull",
    "muscles": {"primary": ["lats"], "secondary": ["biceps"]},
}
REPS = [{"count": 3, "reps": 4, "rpe": 8}]


def a_config(*, hevy: bool = False) -> Config:
    document = a_coach_toml(pin="0.3.0", hevy=hevy, location={"home": HOME, "gym": VEST_GYM})
    document["athlete"] |= {"units": "lb"}
    return parse_config(document)


def a_weighted_ladder(**rung: Any) -> dict[str, Any]:
    fields = {"sets": REPS, "cues": "vest on", "start_load": 5, **rung}
    return a_ladder_line(
        "pull_up",
        a_rung(sets=REPS, cues="lower for 4 s"),
        a_rung("weighted_negative", **fields),
    )


def adopting(**rung: Any) -> tuple[Connection, bytes]:
    session = a_session("pull", a_weighted_ladder(**rung), location="gym")
    draft = a_draft(session, exercise={"weighted_negative": WEIGHTED_NEGATIVE})
    return the_worked_store(), toml(draft)


def adopted(conn: Connection, draft: bytes, *, dry: bool = False) -> AdoptResult:
    return adopt(
        conn,
        draft,
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
        dry_run=dry,
    )


def climbed_to_rung_2(conn: Connection, line_key: str) -> None:
    record(
        conn,
        f'[[decision]]\nkind = "ladder_rung"\nsession = "pull"\nexercise = "{line_key}"\n'
        'rung = 2\nbecause = "progress"\ntext = "Clean sets; the athlete said yes."\n'.encode(),
        file="decision.toml",
        clock=FixedClock(),
    )


def standing_on_the_weighted_rung(**rung: Any) -> Connection:
    conn, draft = adopting(**rung)
    adopted(conn, draft)
    with conn:
        exercises.update(conn, "weighted_negative", {"hevy_template_id": VEST_TEMPLATE})
    climbed_to_rung_2(conn, "pull_up")
    return conn


def next_weeks_plan(conn: Connection, *, hevy: bool = False) -> PlanDraftResult:
    return plan_draft(
        conn, config=a_config(hevy=hevy), kits=(kit_files(),), clock=FixedClock(), week=NEXT_MONDAY
    )


def the_line(conn: Connection) -> LinePrescription:
    [line] = next_weeks_plan(conn).draft.sessions[0].lines
    return line


def working_load(line: LinePrescription) -> float:
    [group] = line.groups
    assert group.load is not None
    return group.load.amount


def test_a_weighted_last_rung_with_its_start_load_adopts() -> None:
    conn, draft = adopting()

    result = adopted(conn, draft)

    assert result.version_id


def test_the_same_ladder_with_no_start_load_is_refused_at_adopt() -> None:
    conn, draft = adopting(start_load=None)

    with pytest.raises(Invalid) as refused:
        adopted(conn, draft)

    assert refused.value.code == "start_load_missing"


def test_a_rung_start_load_off_the_rack_is_refused_at_adopt() -> None:
    conn, draft = adopting(start_load=7)

    with pytest.raises(Invalid) as refused:
        adopted(conn, draft)

    assert refused.value.code == "start_load_off_rack"


def test_a_dry_run_shows_a_rungs_start_load_with_its_rung_and_hevy_kg() -> None:
    conn, draft = adopting()

    result = adopted(conn, draft, dry=True)

    assert list(result.start_loads) == [
        {
            "session": "pull",
            "exercise": "weighted_negative",
            "rung": 2,
            "start_load": 5,
            "units": "lb",
            "kg": 2.268,
        }
    ]


def test_a_rungs_start_load_survives_the_store_and_the_program_draft() -> None:
    conn = standing_on_the_weighted_rung()

    [_, rung] = tomllib.loads(show_draft(conn).text)["session"][0]["line"][0]["scheme"]["rungs"]
    assert rung["start_load"] == 5


def test_standing_on_the_weighted_rung_plan_draft_prescribes_its_load_and_raises_nothing() -> None:
    line = the_line(standing_on_the_weighted_rung())

    assert line.exercise_id == "weighted_negative"
    assert working_load(line) == 5
    assert line.flags == ()


def test_older_logs_of_the_rungs_exercise_at_another_load_do_not_anchor_it() -> None:
    conn = standing_on_the_weighted_rung()
    heavy = ((15 * KG_PER_LB, 4, 8),) * 3
    a_logged_workout(conn, "h-old", "2026-10-29", (VEST_TEMPLATE, heavy))

    line = the_line(conn)

    assert working_load(line) == 5
    assert line.derived_from == "start_load"


def test_a_shared_rung_opens_on_its_own_load_after_a_workout_on_the_decisions_date() -> None:
    conn = the_worked_store()
    ladder = a_ladder_line(
        "weighted_negative",
        a_rung(sets=REPS, cues="lower for 4 s"),
        a_rung("weighted_negative", sets=REPS, cues="lower for 8 s", start_load=15),
    )
    session = a_session("pull", ladder | {"start_load": 5}, location="gym")
    adopted(conn, toml(a_draft(session, exercise={"weighted_negative": WEIGHTED_NEGATIVE})))
    with conn:
        exercises.update(conn, "weighted_negative", {"hevy_template_id": VEST_TEMPLATE})
    earned_the_climb = ((5 * KG_PER_LB, 4, 8),) * 3
    a_logged_workout(
        conn, "h-climb", FixedClock().today().isoformat(), (VEST_TEMPLATE, earned_the_climb)
    )
    climbed_to_rung_2(conn, "weighted_negative")

    line = the_line(conn)

    assert working_load(line) == 15
    assert line.derived_from == "start_load"


def test_the_hevy_routine_for_the_weighted_rung_carries_the_load() -> None:
    conn = standing_on_the_weighted_rung()
    hevy = FakeHevy(FixedClock())
    plan = next_weeks_plan(conn, hevy=True).text.encode()
    data = plan.replace(b"confirmed = false", b"confirmed = true")
    dry = dry_run(
        conn,
        data,
        file="plan.toml",
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )

    apply(
        conn,
        hevy,
        data,
        file="plan.toml",
        expect=dry.write_plan_hash,
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )

    [routine] = hevy.routines()
    [exercise] = [e for e in routine.exercises if e.hevy_template_id == VEST_TEMPLATE]
    assert [s.weight_kg for s in exercise.sets] == [round(5 * KG_PER_LB, 4)] * 3
