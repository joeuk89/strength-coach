import datetime
import json
from collections.abc import Callable
from typing import Any, cast

import pytest
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.ladders import a_ladder_program, ladder_rung_decision
from support.plan_drafts import a_plan_draft
from support.plans import SQUAT_LINE, a_squat_program, squat_logged
from support.program_drafts import a_draft, a_session, toml
from support.programs import a_config
from support.pushes import a_pushed_week, push

from coach.core.errors import Invalid
from coach.hevy.parse import parse_routine
from coach.hevy.protocol import ReadBack, RoutineDiff, WriteContext
from coach.services.hevy_import import import_hevy
from coach.services.program import adopt
from coach.services.projections import projection, session_facts
from coach.services.record import record
from coach.store import mirrors, routine_map, week_plans
from coach.store.connection import Connection

AT = "2026-10-25T12:00:00+00:00"
LATER = FixedClock(datetime.datetime(2026, 10, 31, 9, 0, tzinfo=datetime.UTC))
PIN_115 = """
[[override]]
kind = "pin_load"
session = "lower"
exercise = "bb_back_squat"
load = 115
because = "coach_judgement"
text = "Hold the squat under the last top set."
"""
PIN_125 = PIN_115.replace("load = 115", "load = 125")


def drift_keys(conn: Connection, hevy: FakeHevy) -> list[tuple[str, object]]:
    found = import_hevy(conn, hevy, LATER, full=False, units="lb").warnings
    return [(f.key, f.params["drift_class"]) for f in found if f.code == "routine_drift"]


def drift_plans(conn: Connection, hevy: FakeHevy) -> list[object]:
    found = import_hevy(conn, hevy, LATER, full=False, units="lb").warnings
    return [f.params["plan_in_force"] for f in found if f.code == "routine_drift"]


def test_an_app_edit_to_a_live_routine_warns_routine_drift_until_the_next_push_overwrites_it() -> (
    None
):
    conn, hevy, routine = a_pushed_week()
    quiet = drift_keys(conn, hevy)
    hevy.edit_in_app(routine, 70.0, "2026-10-31T08:00:00Z")

    drifted = drift_keys(conn, hevy)
    push(conn, hevy, a_plan_draft(conn, hevy=True, overrides=PIN_115))

    assert quiet == []
    assert drifted == [(f"routine_drift@routine:{routine}", "load")]
    assert drift_keys(conn, hevy) == []


def test_a_routine_hevy_stops_returning_flips_its_map_row_to_missing_and_keeps_its_mirror_row() -> (
    None
):
    conn, hevy, routine = a_pushed_week()
    hevy.stop_returning(routine)

    import_hevy(conn, hevy, LATER, full=False, units="lb")

    assert routine_map.every(conn) == [("lower", routine, "missing")]
    assert routine in {r.hevy_id for r in mirrors.routines(conn)}
    assert drift_keys(conn, hevy) == []


def test_adopting_a_version_that_renames_a_session_raises_no_drift_and_the_rerun_sends_no_put() -> (
    None
):
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    push(conn, hevy, data)
    renamed = a_session("lower", {**SQUAT_LINE, "cues": "Brace hard"}, title="Legs day")
    adopt(
        conn,
        toml(a_draft(renamed)),
        file="next.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=LATER,
    )

    drifted = drift_keys(conn, hevy)
    hevy.calls.clear()
    push(conn, hevy, data)

    assert drifted == []
    assert [c for c in hevy.calls if c[0] == "PUT"] == []


def test_a_routine_left_unchanged_by_a_superseding_plan_is_judged_against_that_plan() -> None:
    conn, hevy, routine = a_pushed_week()
    push(conn, hevy, a_plan_draft(conn, hevy=True, overrides=PIN_125))
    superseding = week_plans.in_force(conn, "2026-11-02")
    hevy.edit_in_app(routine, 70.0, "2026-10-31T08:00:00Z")

    found = drift_plans(conn, hevy)

    assert superseding is not None
    assert found == [superseding["id"]]


REHAB = """
[[niggle]]
site = "left shoulder"
date = 2026-10-24
status = "reported"

[niggle.rehab]
session = "shoulder_rehab"
title = "Shoulder rehab"
cadence = "standing"

[[niggle.rehab.line]]
exercise = "dead_hang"
rest_s = 60

[[niggle.rehab.line.sets]]
count = 3
duration_s = 30
"""
RESOLVED = '[[niggle]]\nniggle = "n-0001"\ndate = 2026-10-29\nstatus = "resolved"\n'


def test_a_retired_rehab_routine_whose_read_back_differed_raises_no_drift_on_import() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    record(conn, REHAB.encode(), file="n.toml", clock=FixedClock())
    hevy = FakeHevy(FixedClock())
    push(conn, hevy, a_plan_draft(conn, hevy=True))
    rehab = routine_map.mapped(conn)["shoulder_rehab"]
    record(conn, RESOLVED.encode(), file="r.toml", clock=FixedClock())
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        push(conn, hevy, a_plan_draft(conn, hevy=True))

    held = routine_map.every(conn)

    assert ("shoulder_rehab", rehab, "unverified") in held
    assert drift_keys(conn, hevy) == []


def test_a_shared_program_folder_title_skips_drift_rather_than_failing_the_pull() -> None:
    """Two Hevy folders titled Program mirror neither; `plan apply` refuses that state."""
    conn, hevy, routine = a_pushed_week()
    hevy.edit_in_app(routine, 70.0, "2026-10-31T08:00:00Z")
    with conn:
        conn.execute("DELETE FROM folder")
    shared = [
        {"id": 7000 + n, "index": n, "title": "Program", "updated_at": AT, "created_at": AT}
        for n in range(2)
    ]
    held = [json.loads(r.raw) for r in hevy.routines()]

    assert drift_keys(conn, FakeHevy(LATER, routines=held, folders=shared)) == []
    assert mirrors.folders(conn) == ()


APP_EDIT_AT = "2026-10-31T08:00:00Z"
OLD_NEXT = "Next: Hanging Leg Raise"
RUNG_TWO_NEXT = "Next: rung 3 · Hanging Leg Raise · 3×6 @8 · hanging_leg_raise cues"


def a_ladder_week_at_rung_two() -> Connection:
    conn = a_ladder_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    record(conn, ladder_rung_decision(2).encode(), file="d.toml", clock=FixedClock())
    return conn


def a_pushed_ladder(hevy: FakeHevy | None = None) -> tuple[Connection, FakeHevy, str]:
    """`lower` pushed with the squat first and the ladder standing on rung 2, `ab_wheel`, second."""
    conn = a_ladder_week_at_rung_two()
    client = hevy or FakeHevy(FixedClock())
    push(conn, client, a_plan_draft(conn, hevy=True))
    return conn, client, routine_map.mapped(conn)["lower"]


def frozen_before_rungs(conn: Connection) -> None:
    with conn:
        conn.execute("UPDATE prescription SET rung = NULL")


def edited_in_app(hevy: FakeHevy, change: Callable[[dict[str, Any]], None]) -> FakeHevy:
    """A Hevy holding the same routines after the athlete changed the first one."""
    held = [json.loads(r.raw) for r in hevy.routines()]
    change(held[0])
    held[0]["updated_at"] = APP_EDIT_AT
    return FakeHevy(LATER, routines=held)


def with_ladder_note(change: Callable[[list[str]], list[str]]) -> Callable[[dict[str, Any]], None]:
    def edit(routine: dict[str, Any]) -> None:
        ladder = routine["exercises"][1]
        ladder["notes"] = "\n".join(change(ladder["notes"].split("\n")))

    return edit


def next_line_as(wording: str) -> Callable[[list[str]], list[str]]:
    return lambda note: [wording if line.startswith("Next: ") else line for line in note]


def test_a_note_in_the_old_next_wording_raises_no_drift_on_a_row_frozen_before_rungs() -> None:
    conn, hevy, _ = a_pushed_ladder()
    frozen_before_rungs(conn)

    upgraded = edited_in_app(hevy, with_ladder_note(next_line_as(OLD_NEXT)))

    assert drift_keys(conn, upgraded) == []


def test_an_athletes_edit_to_the_next_line_alone_raises_no_drift() -> None:
    conn, hevy, _ = a_pushed_ladder()

    edited = edited_in_app(hevy, with_ladder_note(next_line_as("Next: the rings, I think")))

    assert drift_keys(conn, edited) == []


def test_a_note_with_its_next_line_removed_raises_no_drift() -> None:
    conn, hevy, _ = a_pushed_ladder()
    frozen_before_rungs(conn)

    def without_next(note: list[str]) -> list[str]:
        return [line for line in note if not line.startswith("Next: ")]

    assert drift_keys(conn, edited_in_app(hevy, with_ladder_note(without_next))) == []


def _cues_changed(note: list[str]) -> list[str]:
    return ["Cues: slower" if line.startswith("Cues: ") else line for line in note]


def _target_changed(note: list[str]) -> list[str]:
    return ["Target: 5×5" if line.startswith("Target: ") else line for line in note]


def _line_added(note: list[str]) -> list[str]:
    return [*note, "Felt strong on these"]


def _cues_and_next_changed(note: list[str]) -> list[str]:
    return next_line_as(OLD_NEXT)(_cues_changed(note))


def _set_reps_changed(routine: dict[str, Any]) -> None:
    routine["exercises"][1]["sets"][0]["reps"] = 20


def _exercise_removed(routine: dict[str, Any]) -> None:
    del routine["exercises"][1]


def _exercises_reordered(routine: dict[str, Any]) -> None:
    routine["exercises"].reverse()


@pytest.mark.parametrize(
    "change",
    [
        with_ladder_note(_cues_changed),
        with_ladder_note(_target_changed),
        with_ladder_note(_line_added),
        with_ladder_note(_cues_and_next_changed),
        _set_reps_changed,
        _exercise_removed,
        _exercises_reordered,
    ],
)
def test_any_edit_beyond_the_next_line_is_still_structural_drift(
    change: Callable[[dict[str, Any]], None],
) -> None:
    conn, hevy, routine = a_pushed_ladder()

    assert drift_keys(conn, edited_in_app(hevy, change)) == [
        (f"routine_drift@routine:{routine}", "structural")
    ]


def test_a_note_edit_on_a_row_frozen_before_rungs_still_drifts() -> None:
    conn, hevy, routine = a_pushed_ladder()
    frozen_before_rungs(conn)

    assert drift_keys(conn, edited_in_app(hevy, with_ladder_note(_cues_changed))) == [
        (f"routine_drift@routine:{routine}", "structural")
    ]


def test_a_row_frozen_before_rungs_projects_the_cues_and_sets_it_pushed() -> None:
    conn, _, _ = a_pushed_ladder()
    frozen_before_rungs(conn)
    plan = week_plans.last_approved(conn)
    assert plan is not None

    body = projection(conn, plan, "lower", session_facts(conn, plan)["lower"], "lb")

    ladder = cast(list[dict[str, Any]], body["exercises"])[1]
    assert ladder["notes"].split("\n") == [
        "Target: 3×8 @8, choose the load",
        "Cues: ab_wheel cues",
        RUNG_TWO_NEXT,
    ]
    assert ladder["sets"] == [{"type": "normal", "reps": 8}] * 3


class OldNextLineHevy(FakeHevy):
    """Holds a routine's `Next:` line in the old wording, or returns it so on the next read-back."""

    moving_on_read_back = False

    def hold_old_next_line(self, routine_id: str) -> None:
        with_ladder_note(next_line_as(OLD_NEXT))(self._routines[routine_id])

    def read_back(self, routine_id: str, context: WriteContext, diff: RoutineDiff) -> ReadBack:
        if not self.moving_on_read_back:
            return super().read_back(routine_id, context, diff)
        changed = json.loads(self.routine(routine_id).raw)
        with_ladder_note(next_line_as(OLD_NEXT))(changed)
        routine = parse_routine({"routine": changed})
        return ReadBack(routine=routine, diff=diff(routine))


def test_a_put_whose_read_back_next_line_differs_fails_verification() -> None:
    hevy = OldNextLineHevy(FixedClock())
    conn, _, _ = a_pushed_ladder(hevy)
    hevy.moving_on_read_back = True

    with pytest.raises(Invalid) as failed:
        push(conn, hevy, a_plan_draft(conn, hevy=True, overrides=PIN_115))

    assert failed.value.code == "verify_failed"
    assert [c[0] for c in hevy.calls if c[0] == "PUT"] == ["PUT"]
    assert [status for _, _, status in routine_map.every(conn)] == ["unverified"]


def test_a_re_push_rewrites_a_routine_whose_next_line_alone_differs() -> None:
    hevy = OldNextLineHevy(FixedClock())
    conn = a_ladder_week_at_rung_two()
    data = a_plan_draft(conn, hevy=True)
    push(conn, hevy, data)
    routine = routine_map.mapped(conn)["lower"]
    hevy.hold_old_next_line(routine)
    import_hevy(conn, hevy, LATER, full=False, units="lb")
    hevy.calls.clear()

    push(conn, hevy, data)

    assert [c for c in hevy.calls if c[0] == "PUT"] == [("PUT", f"/v1/routines/{routine}")]
    assert str(hevy.routine(routine).exercises[1].notes).endswith(RUNG_TWO_NEXT)
