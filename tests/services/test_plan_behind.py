import datetime

from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.plan_drafts import NEXT_MONDAY, a_plan_draft
from support.plans import a_squat_program, an_approved_plan
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config

from coach.core.flag import Flag
from coach.services.plan_apply import apply, dry_run
from coach.services.program import AdoptResult, adopt
from coach.services.status import status
from coach.store.connection import Connection

FIRST_ADOPTED = datetime.datetime(2026, 10, 30, 12, 0, tzinfo=datetime.UTC)
MIDWEEK = datetime.datetime(2026, 11, 4, 12, 0, tzinfo=datetime.UTC)
THREE_SETS = a_line(
    "bb_back_squat",
    sets=[
        {"count": 1, "type": "warm_up", "reps": 5},
        {"count": 1, "type": "warm_up", "reps": 3},
        {"count": 3, "reps": [6, 8], "rpe": 8},
    ],
    start_load=100,
)


def applied(conn: Connection, at: datetime.datetime) -> None:
    data = a_plan_draft(conn, week=NEXT_MONDAY)
    config, kits, clock = a_config(), (kit_files(),), FixedClock(at)
    digest = dry_run(conn, data, file="p.toml", config=config, kits=kits, clock=clock)
    apply(
        conn,
        None,
        data,
        file="p.toml",
        expect=digest.write_plan_hash,
        config=config,
        kits=kits,
        clock=clock,
    )


def an_amend(conn: Connection, at: datetime.datetime, *, dry: bool = False) -> AdoptResult:
    return adopt(
        conn,
        toml(a_draft(a_session("lower", THREE_SETS), kind="amend", because="one set fewer")),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(at),
        dry_run=dry,
    )


def standing(conn: Connection, at: datetime.datetime) -> list[Flag]:
    result = status(
        conn,
        FixedClock(at),
        engine_version="0.4.0",
        pin="0.4.0",
        hevy_on=False,
        exported={},
        units="lb",
    )
    return [w for w in result.warnings if w.code == "plan_behind_program"]


def a_week_planned_under_pv1() -> Connection:
    conn = a_squat_program()
    applied(conn, FIRST_ADOPTED + datetime.timedelta(hours=1))
    return conn


def test_status_lists_the_plan_approved_before_a_midweek_adopt_with_both_ids() -> None:
    conn = a_week_planned_under_pv1()
    an_amend(conn, MIDWEEK)

    (flag,) = standing(conn, MIDWEEK)

    assert flag.key == "plan_behind_program@week:2026-11-02"
    assert flag.params == {
        "plan_id": "wp-2026-11-02",
        "approved_under": "pv-1",
        "version_id": "pv-2",
    }


def test_the_adopt_that_leaves_the_plan_behind_carries_the_warning() -> None:
    conn = a_week_planned_under_pv1()

    result = an_amend(conn, MIDWEEK)

    behind = [w for w in result.warnings if w.code == "plan_behind_program"]
    assert [w.params["version_id"] for w in behind] == ["pv-2"]
    assert behind[0].left is None


def test_the_adopt_dry_run_carries_the_warning_for_the_version_it_would_record() -> None:
    conn = a_week_planned_under_pv1()

    result = an_amend(conn, MIDWEEK, dry=True)

    (flag,) = [w for w in result.warnings if w.code == "plan_behind_program"]
    assert flag.params["version_id"] == "pv-2"
    assert standing(conn, MIDWEEK) == []


def test_a_no_op_adopt_carries_no_warning_of_its_own() -> None:
    conn = a_week_planned_under_pv1()
    an_amend(conn, MIDWEEK)

    again = an_amend(conn, MIDWEEK + datetime.timedelta(hours=1))

    assert again.no_op
    assert [w for w in again.warnings if w.code == "plan_behind_program"] == []


def test_a_superseding_plan_applied_for_the_week_clears_it() -> None:
    conn = a_week_planned_under_pv1()
    an_amend(conn, MIDWEEK)
    assert len(standing(conn, MIDWEEK)) == 1

    applied(conn, MIDWEEK + datetime.timedelta(hours=1))

    assert standing(conn, MIDWEEK + datetime.timedelta(hours=2)) == []


def test_a_program_adopted_before_the_plan_was_approved_raises_nothing() -> None:
    conn = a_week_planned_under_pv1()

    assert standing(conn, MIDWEEK) == []


def test_no_plan_in_force_raises_nothing() -> None:
    conn = a_squat_program()
    result = an_amend(conn, MIDWEEK)

    assert standing(conn, MIDWEEK) == []
    assert [w for w in result.warnings if w.code == "plan_behind_program"] == []


def test_a_plan_whose_week_has_passed_raises_nothing() -> None:
    conn = a_squat_program()
    an_approved_plan(conn, "2026-10-26", approved_at="2026-10-26T08:00:00+00:00")

    assert len(standing(conn, FIRST_ADOPTED)) == 1
    assert standing(conn, MIDWEEK) == []
