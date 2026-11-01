import datetime
import tomllib

from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.plans import SQUAT_LINE, a_squat_program, squat_logged
from support.program_drafts import a_line, a_session
from support.programs import a_config

from coach.core.load import Load
from coach.core.overrides import parse_plan_overrides
from coach.core.prescription import LinePrescription
from coach.services.plan_draft import PlanDraftResult, plan_draft
from coach.services.record import record
from coach.store import decisions
from coach.store.connection import Connection

NEXT_MONDAY = datetime.date(2026, 11, 2)
REASON = 'because = "schedule"\ntext = "Away."\n'

# The three overrides of the plan Draft shape in the override catalogue.
CATALOGUE_OVERRIDES = """\
[[override]]
kind = "light_week"
load_cut_pct = 10
because = "fatigue"
text = "Sixth hard week and the squat drifted two sessions running."

[[override]]
kind = "swap_exercise"
session = "a-mon-lower"
exercise = "bb_back_squat"
to = "goblet_squat"
start_load = 24
because = "pain"
text = "Knee niggle flares under the bar; the goblet keeps the pattern."
evidence = ["niggle:n-0004"]

[[override]]
kind = "pin_load"
session = "b-sat-push"
exercise = "bb_bench_press"
load = 100
because = "coach_judgement"
text = "Open the new block two steps under the model; the last exposure was a grinder."
evidence = ["exposure:b7e2c1a0-5d3f-4e8a-9c21-7f0a4d6b9e13/bb_bench_press"]
"""


def the_catalogue_week() -> Connection:
    """`a-mon-lower` (the squat) on Monday and `b-sat-push` (bench) on Wednesday."""
    return a_squat_program(
        a_session("a-mon-lower", SQUAT_LINE), a_session("b-sat-push", a_line("bb_bench_press"))
    )


def drafted(conn: Connection, overrides: str = "") -> PlanDraftResult:
    return plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
        week=NEXT_MONDAY,
        overrides=parse_plan_overrides(tomllib.loads(overrides), file="plan.toml"),
    )


def lines(result: PlanDraftResult) -> dict[tuple[str, str], LinePrescription]:
    return {
        (s.session.session_id, line.exercise_id): line
        for s in result.draft.sessions
        for line in s.lines
    }


def an_override(kind: str, body: str = "") -> str:
    return f'[[override]]\nkind = "{kind}"\n{body}{REASON}'


def record_decision(conn: Connection, kind: str, body: str, until: str = "") -> None:
    text = f'[[decision]]\nkind = "{kind}"\n{body}{until}{REASON}'
    record(conn, text.encode("utf-8"), file="d.toml", clock=FixedClock())


def test_the_catalogue_overrides_parse_and_derive() -> None:
    result = drafted(the_catalogue_week(), CATALOGUE_OVERRIDES)

    found = lines(result)
    goblet = found["a-mon-lower", "goblet_squat"]
    bench = found["b-sat-push", "bb_bench_press"]
    assert goblet.derived_from == "start_load"
    assert goblet.steps[1].to == 24
    assert goblet.groups[-1].load == Load(20, "single_implement")
    load_steps = [(s.step, s.from_, s.to, s.cause) for s in bench.steps if s.step != "rpe_ceiling"]
    assert load_steps == [
        ("scheme", None, 60, "start_load"),
        ("override", 60, 100, "pin_load"),
        ("cut", 100, 90, "light"),
        ("cut", 3, 2, "sets"),
        ("rack", 90, 90, "row"),
    ]
    assert bench.groups[-1].load == Load(90, "total")


def test_the_draft_carries_the_overrides_it_derived_from() -> None:
    text = drafted(the_catalogue_week(), CATALOGUE_OVERRIDES).text

    kinds = [o["kind"] for o in tomllib.loads(text)["override"]]
    assert kinds == ["light_week", "swap_exercise", "pin_load"]


def test_an_override_decision_changes_a_plan_the_draft_never_mentions() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    record_decision(
        conn,
        "override",
        'session = "lower"\nexercise = "bb_back_squat"\n'
        'override = { kind = "pin_load", load = 110 }\n',
        'until = "2026-12-20"\n',
    )

    assert lines(drafted(conn))["lower", "bb_back_squat"].groups[-1].load == Load(110, "total")

    pinned = drafted(
        conn,
        an_override("pin_load", 'session = "lower"\nexercise = "bb_back_squat"\nload = 100\n'),
    )

    assert lines(pinned)["lower", "bb_back_squat"].groups[-1].load == Load(100, "total")
    assert [row["kind"] for row in decisions.in_force(conn)] == ["override"]


def test_conflicting_overrides_are_flagged_on_the_draft() -> None:
    hold = an_override("hold", 'session = "lower"\nexercise = "bb_back_squat"\n')

    flags = drafted(a_squat_program(), hold + hold).draft.flags

    assert [(f.code, f.params) for f in flags if f.code == "override_conflict"] == [
        ("override_conflict", {"kinds": ["hold", "hold"]})
    ]


def test_a_minimum_week_derives_only_its_kept_sessions() -> None:
    conn = the_catalogue_week()

    result = drafted(conn, an_override("minimum_week", 'keep = ["b-sat-push"]\n'))

    assert [s.session.session_id for s in result.draft.sessions] == ["b-sat-push"]


def test_an_add_session_on_two_dates_in_one_week_derives_both() -> None:
    added = an_override("add_session", 'session = "lower"\ndate = 2026-11-04\n') + an_override(
        "add_session", 'session = "lower"\ndate = 2026-11-06\n'
    )

    sessions = drafted(a_squat_program(), added).draft.sessions

    assert [s.session.date.isoformat() for s in sessions] == [
        "2026-11-02",
        "2026-11-04",
        "2026-11-06",
    ]


def test_a_parked_session_is_absent_until_it_is_resumed() -> None:
    conn = the_catalogue_week()

    record_decision(conn, "park_session", 'session = "b-sat-push"\n')
    parked = [s.session.session_id for s in drafted(conn).draft.sessions]
    record_decision(conn, "resume_session", 'session = "b-sat-push"\n')
    resumed = [s.session.session_id for s in drafted(conn).draft.sessions]

    assert parked == ["a-mon-lower"]
    assert resumed == ["a-mon-lower", "b-sat-push"]


def test_a_pin_on_a_parked_session_brought_back_by_add_session_derives_the_pinned_load() -> None:
    conn = the_catalogue_week()
    record_decision(conn, "park_session", 'session = "b-sat-push"\n')
    added = an_override("add_session", 'session = "b-sat-push"\ndate = 2026-11-05\n')
    pin = an_override(
        "pin_load", 'session = "b-sat-push"\nexercise = "bb_bench_press"\nload = 100\n'
    )

    bench = lines(drafted(conn, added + pin))["b-sat-push", "bb_bench_press"]

    assert bench.groups[-1].load == Load(100, "total")
