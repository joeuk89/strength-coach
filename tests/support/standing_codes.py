"""One scenario per warning outside a plan: a store seeded into the code's state, `status` read
while it stands, then the fact behind it changed by its own verb and `status` read again."""

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from coach.cli import app
from coach.core.clock import Clock
from coach.core.config import Location
from coach.core.goal import PhaseOpen, Until
from coach.core.kit import KitFiles
from coach.services.hevy_import import import_hevy
from coach.services.program import adopt
from coach.services.record import record
from coach.services.status import status
from coach.store import phases
from coach.store.connection import Connection
from support.blocks import BOUNDARY, PULL_UP_LINE, two_closed_blocks
from support.cli import run_coach
from support.clock import NOON, FixedClock, at
from support.closed_weeks import a_check_in
from support.fake_hevy import FakeHevy
from support.hevy_payloads import a_workout, an_exercise
from support.instances import an_instance
from support.kit_fixtures import kit_files
from support.ledger import a_store, a_weigh_in
from support.plan_drafts import a_plan_draft
from support.plans import a_frozen_prescription, a_squat_program, an_approved_plan
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config
from support.pushes import a_pushed_week, push

ENGINE = "0.4.0"
TODAY = datetime.date(2026, 11, 29)


@dataclass(frozen=True)
class Standing:
    raised: tuple[str, ...]
    cleared: tuple[str, ...]


type Scenario = Callable[[Path, pytest.MonkeyPatch], Standing]


def status_codes(
    conn: Connection,
    on: datetime.date = TODAY,
    *,
    hevy_on: bool = False,
    locations: tuple[Location, ...] = (),
    kits: tuple[KitFiles, ...] = (),
) -> tuple[str, ...]:
    """Lift loads in lb and bodyweight in kg, so a scenario catches either read in the other's."""
    result = status(
        conn,
        FixedClock(at(on)),
        engine_version=ENGINE,
        pin=ENGINE,
        hevy_on=hevy_on,
        exported={},
        units="lb",
        bodyweight_units="kg",
        locations=locations,
        kits=kits,
    )
    return tuple(w.code for w in result.warnings)


def recorded(conn: Connection, text: str) -> None:
    record(conn, text.encode(), file="d.toml", clock=FixedClock())


def followup_due(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    recorded(conn, '[[follow_up]]\nraised = 2026-11-01\ntext = "retest"\ndue = 2026-11-28\n')
    raised = status_codes(conn)
    recorded(conn, '[[follow_up]]\nfollow_up = "f-0001"\nkind = "resolved"\ndate = 2026-11-29\n')
    return Standing(raised, status_codes(conn))


def niggle_unconstrained(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    recorded(
        conn,
        '[[niggle]]\nsite = "left knee"\nopened = 2026-11-20\ndate = 2026-11-20\n'
        'status = "reported"\n',
    )
    raised = status_codes(conn)
    recorded(
        conn,
        '[[niggle]]\nniggle = "n-0001"\ndate = 2026-11-29\nstatus = "easing"\n'
        '[[niggle.constraints]]\nkind = "rpe_cap"\npattern = "squat"\nvalue = 8\n',
    )
    return Standing(raised, status_codes(conn))


def a_phase(conn: Connection, kind: str, rate: float, until: Until) -> None:
    with conn:
        phases.insert(
            conn,
            id_="ph-0001",
            phase=PhaseOpen(kind, rate, until, "cutting for the meet"),
            opened="2026-10-01",
            opened_by="goal:g-0001",
            draft_hash="sha256:ph",
            recorded_at="2026-10-01T09:00:00+00:00",
        )


def the_phase_closed(conn: Connection) -> None:
    with conn:
        phases.close(conn, "ph-0001", closed="2026-11-29", closed_by="goal:g-0002", because="done")


def phase_trend_off(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    a_phase(conn, "deficit", -0.5, Until("coachs_call"))
    a_weigh_in(conn, "2026-11-01", 80.0, id_="wi-0001")
    a_weigh_in(conn, "2026-11-29", 80.0, id_="wi-0002")
    raised = status_codes(conn)
    the_phase_closed(conn)
    return Standing(raised, status_codes(conn))


def phase_condition_met(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    a_phase(conn, "deficit", -0.5, Until("bodyweight_at_or_below", 80))
    a_weigh_in(conn, "2026-11-20", 80.4, id_="wi-0001")
    a_weigh_in(conn, "2026-11-27", 79.4, id_="wi-0002")
    raised = status_codes(conn)
    the_phase_closed(conn)
    return Standing(raised, status_codes(conn))


def training_max_unused(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_squat_program()
    recorded(
        conn,
        '[[decision]]\nkind = "training_max"\nexercise = "bb_back_squat"\nload = 140\n'
        'because = "coach_judgement"\ntext = "tested single"\n',
    )
    raised = status_codes(conn)
    decision = conn.execute("SELECT id FROM decision WHERE kind = 'training_max'").fetchone()[0]
    recorded(
        conn,
        f'[[decision]]\nkind = "retire"\ndecision = "{decision}"\n'
        'because = "coach_judgement"\ntext = "no wave planned"\n',
    )
    return Standing(raised, status_codes(conn))


def an_activity(conn: Connection, on: str, *, rpe: float = 5, distance_km: float = 5) -> None:
    quality = "true" if rpe >= 7 else "false"
    recorded(
        conn,
        f'[[activity]]\ndate = {on}\nkind = "run"\nminutes = 40\nrpe = {rpe}\n'
        f"quality = {quality}\ndistance_km = {distance_km}\n",
    )


def the_week_closed(conn: Connection) -> tuple[str, ...]:
    """A Check-in on Sunday 29 Nov closes the week; `status` read on the Monday after."""
    a_check_in(conn, "2026-11-23", TODAY.isoformat())
    return status_codes(conn, TODAY + datetime.timedelta(days=1))


def activity_cap_exceeded(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    for on in ("2026-11-23", "2026-11-25", "2026-11-27"):
        an_activity(conn, on, rpe=8)
    return Standing(status_codes(conn), the_week_closed(conn))


def run_spike(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    an_activity(conn, "2026-11-05", distance_km=10)
    an_activity(conn, "2026-11-29", distance_km=12)
    return Standing(status_codes(conn), the_week_closed(conn))


def a_new_version(conn: Connection, *lines: dict[str, object]) -> None:
    adopt(
        conn,
        toml(a_draft(a_session("push", *lines), kind="amend", because="cadence")),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(at(BOUNDARY)),
    )


def cadence_slow(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = two_closed_blocks()
    raised = status_codes(conn, BOUNDARY)
    wave = a_line("bb_bench_press", sets=[{"count": 3}], scheme={"name": "wave_531"})
    a_new_version(conn, wave, PULL_UP_LINE)
    return Standing(raised, status_codes(conn, BOUNDARY))


def cadence_fast(_: Path, __: pytest.MonkeyPatch) -> Standing:
    """Bench rising with the one-row cap setting every top: the cap holds it back."""
    capped: dict[str, object] = {"step": "scheme", "from": 100, "to": 102.5, "cause": "one_row_cap"}
    conn = two_closed_blocks(bench_tops=(100, 105, 105, 110, 115, 115), steps=[capped])
    raised = status_codes(conn, BOUNDARY)
    wave = a_line("bb_bench_press", sets=[{"count": 3}], scheme={"name": "wave_531"})
    a_new_version(conn, wave, PULL_UP_LINE)
    return Standing(raised, status_codes(conn, BOUNDARY))


IMPORTED = NOON.date()
WORKOUT = "10000000-0000-4000-8000-00000000000a"


def imported(
    conn: Connection, *workouts: dict[str, object], clock: FixedClock | None = None
) -> None:
    moment = clock or FixedClock()
    import_hevy(conn, FakeHevy(moment, workouts=list(workouts)), moment, full=True, units="lb")


def snapshot_stale(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    imported(conn)
    raised = status_codes(conn, hevy_on=True)
    imported(conn, clock=FixedClock(at(TODAY)))
    return Standing(raised, status_codes(conn, hevy_on=True))


def workout_reappeared(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    imported(conn, a_workout(WORKOUT))
    imported(conn)
    imported(conn, a_workout(WORKOUT), clock=FixedClock(NOON + datetime.timedelta(hours=1)))
    raised = status_codes(conn, IMPORTED, hevy_on=True)
    recorded(
        conn,
        f'[[annotation]]\nkind = "void"\ntarget = "workout:{WORKOUT}"\n'
        'because = "coach_judgement"\n',
    )
    return Standing(raised, status_codes(conn, IMPORTED, hevy_on=True))


def exercise_unmapped(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    custom = an_exercise("C0FFEE01", "Hollow Hold")
    imported(conn, a_workout(WORKOUT, exercises=[custom]))
    raised = status_codes(conn, IMPORTED, hevy_on=True)
    recorded(
        conn,
        '[[exercise]]\nid = "custom_hollow_hold"\nname = "Hollow hold"\n'
        'load_mode = "duration"\nequipment_kind = "bodyweight"\npattern = "core"\n'
        'muscles = {primary = ["abdominals"], secondary = []}\n'
        'hevy_template_id = "C0FFEE01"\nhevy_title = "Hollow Hold"\n',
    )
    return Standing(raised, status_codes(conn, IMPORTED, hevy_on=True))


def routine_drift(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn, hevy, routine = a_pushed_week()
    hevy.edit_in_app(routine, 70.0, "2026-10-31T08:00:00Z")
    later = FixedClock(datetime.datetime(2026, 10, 31, 9, 0, tzinfo=datetime.UTC))
    import_hevy(conn, hevy, later, full=False, units="lb")
    raised = status_codes(conn, later.today(), hevy_on=True)
    push(conn, hevy, a_plan_draft(conn, hevy=True, overrides=PIN_SQUAT))
    return Standing(raised, status_codes(conn, later.today(), hevy_on=True))


PIN_SQUAT = """
[[override]]
kind = "pin_load"
session = "lower"
exercise = "bb_back_squat"
load = 115
because = "coach_judgement"
text = "Hold the squat under the last top set."
"""


def frozen_load_off_rack(_: Path, __: pytest.MonkeyPatch) -> Standing:
    """The 26 Oct plan froze 121 lb, which the home rack cannot build."""
    conn = a_squat_program()
    plan_id = an_approved_plan(conn, "2026-10-26")
    working = {"type": "working", "count": 4, "load": 121.0, "load_kg": 54.88, "range": [6, 8]}
    a_frozen_prescription(
        conn, plan_id, "lower", "2026-10-26", "bb_back_squat", set_groups=[working], change="held"
    )
    locations, kits = a_config().locations, (kit_files(),)
    raised = status_codes(conn, IMPORTED, locations=locations, kits=kits)
    an_approved_plan(conn, "2026-11-02")
    return Standing(raised, status_codes(conn, IMPORTED, locations=locations, kits=kits))


RELEASE = "0.3.0"


def a_fake_hevy(_: str, __: Path, clock: Clock) -> FakeHevy:
    return FakeHevy(clock)


def cli_status_codes(monkeypatch: pytest.MonkeyPatch, engine: str = RELEASE) -> tuple[str, ...]:
    monkeypatch.setattr(app, "engine_version", lambda: engine)
    run = run_coach("status", clock=FixedClock(), make_client=a_fake_hevy)
    assert run.code == 0, run.stdout
    return tuple(w["code"] for w in run.envelope["warnings"])


def engine_pin_dev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standing:
    """Cleared by running the release the instance pins."""
    monkeypatch.chdir(an_instance(tmp_path, pin=RELEASE))
    raised = cli_status_codes(monkeypatch, f"{RELEASE}.dev0")
    return Standing(raised, cli_status_codes(monkeypatch))


def generated_file_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standing:
    """Cleared by writing the file back as the engine generates it, as `coach upgrade` does."""
    root = an_instance(tmp_path, pin=RELEASE)
    monkeypatch.chdir(root)
    claude_md = root / "CLAUDE.md"
    generated = claude_md.read_text(encoding="utf-8")
    claude_md.write_text(generated + "Always answer in French.\n", encoding="utf-8")
    raised = cli_status_codes(monkeypatch)
    claude_md.write_text(generated, encoding="utf-8")
    return Standing(raised, cli_status_codes(monkeypatch))


SCENARIOS: dict[str, Scenario] = {
    "engine_pin_dev": engine_pin_dev,
    "generated_file_drift": generated_file_drift,
    "snapshot_stale": snapshot_stale,
    "workout_reappeared": workout_reappeared,
    "exercise_unmapped": exercise_unmapped,
    "routine_drift": routine_drift,
    "frozen_load_off_rack": frozen_load_off_rack,
    "followup_due": followup_due,
    "niggle_unconstrained": niggle_unconstrained,
    "phase_trend_off": phase_trend_off,
    "phase_condition_met": phase_condition_met,
    "training_max_unused": training_max_unused,
    "activity_cap_exceeded": activity_cap_exceeded,
    "run_spike": run_spike,
    "cadence_slow": cadence_slow,
    "cadence_fast": cadence_fast,
}
