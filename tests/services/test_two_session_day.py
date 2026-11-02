"""A weekday naming a lifting session and a conditioning session beside it."""

import datetime
import tomllib
from typing import Any, cast

import pytest
from support.check_in_cards import field_of, opened
from support.clock import FixedClock
from support.closed_weeks import closed_through, monday
from support.history import a_logged_workout, an_annotation
from support.kit_fixtures import kit_files
from support.plans import SQUAT_LINE, a_squat_program, an_approved_plan, squat_logged
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config, the_worked_store

from coach.core.errors import Invalid
from coach.core.plan_draft import PlanDraft
from coach.services.closed_weeks import closed_weeks
from coach.services.history import read_history
from coach.services.plan_draft import plan_draft
from coach.services.program import adopt, show_draft
from coach.services.query import exposures
from coach.store import programs

SWINGS = a_session(
    "cond-swings",
    a_line("kb_swing", scheme={"name": "hold"}, start_load=35, sets=[{"count": 1, "reps": 12}]),
    kind="conditioning",
    tier="optional",
    minutes=16,
    scheme={
        "name": "emom_density",
        "minutes": 12,
        "minutes_cap": 16,
        "minutes_step": 2,
        "reps": {"kb_swing": 12},
        "reps_cap": {"kb_swing": 15},
        "rpe_target": 8,
    },
)
LOWER = a_session("lower", SQUAT_LINE)
SWING_TEMPLATE = "F8A0FCCA"


def a_monday(*ids: object) -> dict[str, Any]:
    return {"rotation": ["A"], "A": {"mon": list(ids)}}


def adopted(**draft: Any) -> Any:
    return adopt(
        the_worked_store(),
        toml(a_draft(LOWER, SWINGS, **draft)),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


def drafted(*sessions: dict[str, Any], schedule: dict[str, Any]) -> PlanDraft:
    conn = a_squat_program(*sessions, schedule=schedule)
    return plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(datetime.datetime(2026, 11, 1)),
        week=datetime.date.fromisoformat(monday(0)),
        position="A",
    ).draft


def test_a_weekday_listing_two_sessions_adopts() -> None:
    conn = the_worked_store()
    result = adopt(
        conn,
        toml(a_draft(LOWER, SWINGS, schedule=a_monday("lower", "cond-swings"))),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )

    assert result.version_id == "pv-1"
    stored = programs.latest(conn)
    assert stored is not None
    assert stored.form.schedule.weeks["A"]["mon"] == ("lower", "cond-swings")


def test_the_plan_draft_plans_both_sessions_on_the_monday_lifting_first() -> None:
    draft = drafted(LOWER, SWINGS, schedule=a_monday("lower", "cond-swings"))

    assert [(s.session.date.isoformat(), s.session.session_id) for s in draft.sessions] == [
        ("2026-11-02", "lower"),
        ("2026-11-02", "cond-swings"),
    ]


def test_the_list_order_is_the_order_within_the_day() -> None:
    draft = drafted(LOWER, SWINGS, schedule=a_monday("cond-swings", "lower"))

    assert [s.session.session_id for s in draft.sessions] == ["cond-swings", "lower"]


def test_the_conditioning_session_prescribes_under_its_own_session_scheme() -> None:
    draft = drafted(LOWER, SWINGS, schedule=a_monday("lower", "cond-swings"))

    lifting, conditioning = draft.sessions
    assert conditioning.dose is not None
    assert (conditioning.dose.scheme, conditioning.dose.minutes) == ("emom_density", 12)
    assert conditioning.dose.reps == {"kb_swing": 12}
    assert lifting.dose is None


def test_quality_conditioning_beside_a_lifting_session_suggests_dropping_it() -> None:
    draft = drafted(LOWER, SWINGS, schedule=a_monday("lower", "cond-swings"))

    [flag] = [f for f in draft.week_checks if f.code == "session_drop_suggested"]
    assert flag.scope.session_id == "cond-swings"
    assert flag.params == {
        "reason": "quality_stack",
        "evidence": ["planned_session:2026-11-02/cond-swings", "planned_session:2026-11-02/lower"],
    }


def test_one_session_twice_on_a_weekday_is_refused_as_a_duplicate_id() -> None:
    with pytest.raises(Invalid) as refused:
        adopted(schedule=a_monday("lower", "lower", "cond-swings"))

    assert refused.value.code == "duplicate_id"


def test_a_listed_session_the_version_lacks_names_its_week_weekday_and_id() -> None:
    with pytest.raises(Invalid) as refused:
        adopted(schedule=a_monday("lower", "cond-swings", "cond-rower"))

    assert refused.value.code == "schedule_session_missing"
    flags = cast(list[dict[str, Any]], refused.value.details["violations"])
    [flag] = [f for f in flags if f["code"] == "schedule_session_missing"]
    assert flag["params"] == {"week": "A", "weekday": "mon", "session_id": "cond-rower"}


@pytest.mark.parametrize("monday_", [[], ["lower", 3]])
def test_an_empty_list_or_a_non_string_entry_is_the_wrong_shape(monday_: list[object]) -> None:
    with pytest.raises(Invalid) as refused:
        adopted(schedule={"rotation": ["A"], "A": {"mon": monday_}})

    assert refused.value.code == "invalid_argument"
    assert "schedule.A.mon" in refused.value.message


def test_each_workout_of_the_day_matches_its_own_session_and_the_swings_deliver_no_dose() -> None:
    conn = a_squat_program(LOWER, SWINGS, schedule=a_monday("lower", "cond-swings"))
    an_approved_plan(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 8)] * 4)
    a_logged_workout(conn, "h-2", monday(0), (SWING_TEMPLATE, ((24.0, 12, 8.0),) * 12))
    closed_through(conn, 1)

    [week] = closed_weeks(conn).weeks

    assert [(s.session.session_id, s.workout_id) for s in week.sessions] == [
        ("lower", "h-1"),
        ("cond-swings", "h-2"),
    ]
    assert week.dose == {"quadriceps": 4, "glutes": 4, "adductors": 2.0, "lower_back": 2.0}


def test_the_swings_workout_matched_to_the_conditioning_session_is_an_activity() -> None:
    conn = a_squat_program(LOWER, SWINGS, schedule=a_monday("lower", "cond-swings"))
    an_approved_plan(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 8)] * 4)
    a_logged_workout(conn, "h-2", monday(0), (SWING_TEMPLATE, ((24.0, 12, 8.0),) * 12))

    rows = field_of(opened(conn), "activities").facts["rows"]

    assert rows == [
        {
            "id": "h-2",
            "date": "2026-11-02",
            "kind": "conditioning",
            "minutes": None,
            "rpe": 8.0,
            "quality": True,
        }
    ]


def a_swings_monday() -> Any:
    conn = a_squat_program(LOWER, SWINGS, schedule=a_monday("lower", "cond-swings"))
    an_approved_plan(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 8)] * 4)
    a_logged_workout(conn, "h-2", monday(0), (SWING_TEMPLATE, ((24.0, 12, 8.0),) * 12))
    return conn


def test_the_swings_workout_gives_the_check_in_no_lift_row() -> None:
    rows = cast(list[dict[str, Any]], field_of(opened(a_swings_monday()), "lifts").facts["rows"])

    assert [r["exercise"] for r in rows] == ["bb_back_squat"]


def test_the_next_swings_hold_line_anchors_on_the_logged_swings() -> None:
    conn = a_swings_monday()

    draft = plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(datetime.datetime(2026, 11, 8)),
        week=datetime.date.fromisoformat(monday(1)),
        position="A",
    ).draft

    [swings] = [s for s in draft.sessions if s.session.session_id == "cond-swings"]
    [line] = swings.lines
    load = line.groups[-1].load
    assert line.derived_from == "exposure:h-2/kb_swing"
    assert load is not None and load.amount == 52.5


def test_a_swings_only_day_is_not_a_lifting_day_for_the_return_week() -> None:
    conn = a_squat_program(LOWER, SWINGS, schedule=a_monday("lower", "cond-swings"))
    squat_logged(conn, "h-0", monday(-3), *[(120, 8, 8)] * 4)
    an_approved_plan(conn, monday(0))
    a_logged_workout(conn, "h-2", monday(0), (SWING_TEMPLATE, ((24.0, 12, 8.0),) * 12))
    an_annotation(
        conn,
        "a-1",
        "match",
        "workout:h-2",
        planned_session=f"planned_session:{monday(0)}/cond-swings",
    )
    an_approved_plan(conn, monday(1))
    squat_logged(conn, "h-3", monday(1), *[(120, 8, 8)] * 4)
    closed_through(conn, 2)

    kinds = [w.kind for w in closed_weeks(conn).weeks]

    assert kinds == ["partial", "return"]


def test_the_program_draft_keeps_the_two_session_day_and_adopts_again_unchanged() -> None:
    conn = a_squat_program(LOWER, SWINGS, schedule=a_monday("lower", "cond-swings"))

    text = show_draft(conn).text
    again = adopt(
        conn,
        text.encode(),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
        dry_run=True,
    )

    assert tomllib.loads(text)["schedule"]["A"] == {"mon": ["lower", "cond-swings"]}
    assert "schedule" not in again.diff.version


def test_each_exposure_of_a_derived_match_carries_the_session_id_and_kind() -> None:
    exposures = read_history(a_swings_monday(), "kg").exposures

    assert {(e.ref, e.match and (e.match.session_id, e.match.kind)) for e in exposures} == {
        ("exposure:h-1/bb_back_squat", ("lower", "lifting")),
        ("exposure:h-2/kb_swing", ("cond-swings", "conditioning")),
    }


def test_query_exposures_shows_the_conditioning_rows_with_their_session() -> None:
    rows = exposures(a_swings_monday(), exercises=(), since=None, last=10, units="kg").rows

    assert {(r["exposure"], r["session"]) for r in rows} == {
        ("exposure:h-1/bb_back_squat", "lower"),
        ("exposure:h-2/kb_swing", "cond-swings"),
    }


def test_the_closed_week_log_and_the_history_read_agree_on_every_match() -> None:
    conn = a_swings_monday()
    an_approved_plan(conn, monday(1))
    a_logged_workout(
        conn,
        "w-0001",
        monday(1),
        (SWING_TEMPLATE, ((24.0, 12, 8.0),) * 12),
        session_id="cond-swings",
    )
    an_approved_plan(conn, monday(2))
    tuesday = (datetime.date.fromisoformat(monday(2)) + datetime.timedelta(days=1)).isoformat()
    squat_logged(conn, "h-3", tuesday, *[(120, 8, 8)] * 4)
    an_annotation(
        conn, "a-1", "match", "workout:h-3", planned_session=f"planned_session:{monday(2)}/lower"
    )
    closed_through(conn, 3)

    logged = {
        s.workout_id: s.session.session_id
        for week in closed_weeks(conn).weeks
        for s in week.sessions
        if s.workout_id is not None
    }
    read = {e.workout_id: e.session_id for e in read_history(conn, "kg").exposures}

    assert (
        logged
        == read
        == {
            "h-1": "lower",
            "h-2": "cond-swings",
            "w-0001": "cond-swings",
            "h-3": "lower",
        }
    )
