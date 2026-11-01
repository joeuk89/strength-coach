import dataclasses
import json
from typing import Any, cast

import pytest
from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.program_drafts import WORKED_DRAFT_COMPLETE, a_draft, a_line, a_session, toml
from support.programs import a_config, a_goal, a_library_store, a_phase, the_worked_store

from coach.core.errors import Invalid, Setup
from coach.core.kit import KitFiles
from coach.services.program import AdoptResult, adopt, show, show_draft
from coach.store import exercises, programs
from coach.store.connection import Connection

CLOCK = FixedClock()


def run(
    conn: Connection,
    data: bytes | str,
    *,
    dry_run: bool = False,
    position: str | None = None,
    kits: tuple[KitFiles, ...] | None = None,
    **config: Any,
) -> AdoptResult:
    return adopt(
        conn,
        data.encode() if isinstance(data, str) else data,
        file="draft.toml",
        config=a_config(**config),
        kits=(kit_files(),) if kits is None else kits,
        clock=CLOCK,
        dry_run=dry_run,
        position=position,
    )


def rotation_draft(**fields: Any) -> bytes:
    draft = a_draft(a_session("push"), a_session("pull", a_line("bb_bent_over_row")), **fields)
    draft["schedule"] = {"rotation": ["A", "B"], "A": {"mon": "push"}, "B": {"mon": "pull"}}
    return toml(draft)


def test_the_worked_draft_adopts_with_no_violations_as_the_first_version() -> None:
    conn = the_worked_store()

    result = run(conn, WORKED_DRAFT_COMPLETE)

    assert (result.version_id, result.kind, result.position) == ("pv-1", "redesign", "A")
    assert (result.block, result.block_reset) == ("b-2026-10-30", True)
    stored = programs.latest(conn)
    assert stored is not None and stored.adopted == "2026-10-30"
    assert programs.line_counts(conn, "pv-1")[:4] == [
        ("pt-tuesday", 0),
        ("a-mon-lower", 6),
        ("b-sat-push", 1),
        ("a-sat-pull", 3),
    ]


def test_omitted_dose_and_deload_are_filled_stored_and_marked_in_the_dry_run() -> None:
    conn = the_worked_store()

    dry = run(conn, WORKED_DRAFT_COMPLETE, dry_run=True)
    run(conn, WORKED_DRAFT_COMPLETE)

    change: Any = dry.diff.to_json()
    assert change["version"]["dose"]["filled"] is True
    assert change["version"]["deload"]["to"] == {
        "hard_weeks_ceiling": 6,
        "set_cut_pct": 40,
        "load_cut_pct": 0,
        "rpe_cap": 8,
        "test_priority_lifts": True,
    }
    assert "session.a-mon-lower.minutes" in change["filled"]
    row = conn.execute("SELECT dose, deload FROM program_version WHERE id = 'pv-1'").fetchone()
    assert json.loads(row[0]) == {"per_muscle": 10, "lift": {"bb_bench_press": 8, "pull_up": 8}}
    assert json.loads(row[1])["set_cut_pct"] == 40


def test_the_filled_version_keeps_every_authored_scheme_rpe_and_rest() -> None:
    conn = the_worked_store()

    run(conn, WORKED_DRAFT_COMPLETE)

    rows = conn.execute(
        "SELECT set_groups, rest_s, scheme FROM program_line "
        "WHERE session_id = 'b-sat-push' AND exercise_id = 'bb_bench_press'"
    ).fetchone()
    assert json.loads(rows[0])[2] == {"count": 4, "reps": 5, "rpe": 8}
    assert rows[1] == 180
    assert json.loads(rows[2]) == {"name": "linear"}


def test_a_dry_run_shows_each_start_load_with_its_hevy_kg_and_writes_nothing() -> None:
    conn = the_worked_store()

    result = run(conn, WORKED_DRAFT_COMPLETE, dry_run=True)

    assert result.dry_run and programs.latest(conn) is None
    assert {
        "session": "b-sat-push",
        "exercise": "bb_bench_press",
        "start_load": 120,
        "units": "lb",
        "kg": 54.431,
    } in result.start_loads


def test_a_draft_with_violations_is_refused_with_every_flag_and_writes_nothing() -> None:
    conn = the_worked_store()
    draft = a_draft(a_session("push", a_line(start_load=121), a_line("bb_floor_press")))

    with pytest.raises(Invalid) as refused:
        run(conn, toml(draft))

    assert refused.value.code == "start_load_off_rack"
    flags = cast(list[dict[str, Any]], refused.value.details["violations"])
    keys = [flag["key"] for flag in flags]
    assert keys == [
        "start_load_off_rack@line:push/bb_bench_press",
        "unknown_exercise@line:push/bb_floor_press",
    ]
    assert programs.latest(conn) is None


def test_the_same_draft_again_is_a_no_op_with_the_same_version_number() -> None:
    conn = the_worked_store()
    run(conn, WORKED_DRAFT_COMPLETE)

    again = run(conn, WORKED_DRAFT_COMPLETE)

    assert again.no_op and again.version_id == "pv-1"
    assert conn.execute("SELECT count(*) FROM program_version").fetchone() == (1,)


def test_a_redesign_starts_at_the_first_week_or_at_position() -> None:
    conn = the_worked_store()

    first = run(conn, rotation_draft())
    second = run(conn, rotation_draft(because="block 2"), position="B")

    assert (first.position, second.position) == ("A", "B")
    assert second.block_reset


def test_an_amend_keeps_the_position_and_the_block() -> None:
    conn = the_worked_store()
    run(conn, rotation_draft(), position="B")

    amend = run(conn, rotation_draft(kind="amend", because="swap"))

    assert (amend.version_id, amend.position) == ("pv-2", "B")
    assert (amend.block, amend.block_reset) == ("b-2026-10-30", False)


@pytest.mark.parametrize(
    ("draft", "position"),
    [
        (rotation_draft(kind="amend"), None),
        (rotation_draft(), "C"),
    ],
)
def test_an_amend_with_no_version_and_a_position_outside_the_rotation_are_invalid(
    draft: bytes, position: str | None
) -> None:
    with pytest.raises(Invalid) as refused:
        run(the_worked_store(), draft, position=position)

    assert refused.value.code == "invalid_argument"


def test_position_on_an_amend_is_invalid() -> None:
    conn = the_worked_store()
    run(conn, rotation_draft())

    with pytest.raises(Invalid):
        run(conn, rotation_draft(kind="amend", because="swap"), position="B")


def test_show_draft_re_adopts_as_an_amend_with_an_empty_diff() -> None:
    conn = the_worked_store()
    run(conn, WORKED_DRAFT_COMPLETE)

    text = show_draft(conn)
    dry = run(conn, text, dry_run=True)
    amend = run(conn, text)

    assert dry.diff.empty and dry.diff.filled == ()
    assert (amend.version_id, amend.kind, amend.block_reset) == ("pv-2", "amend", False)


def test_show_reads_the_version_in_force() -> None:
    conn = the_worked_store()
    run(conn, WORKED_DRAFT_COMPLETE)

    shown = show(conn)

    assert (shown.version_id, shown.kind, shown.emphasis, shown.adopted) == (
        "pv-1",
        "redesign",
        "hypertrophy",
        "2026-10-30",
    )
    assert shown.because.startswith("first program")
    assert shown.sessions[1] == ("a-mon-lower", 6)


def test_show_with_no_version_is_invalid() -> None:
    with pytest.raises(Invalid):
        show(a_library_store())


def test_a_stale_kit_at_a_location_the_draft_names_is_kit_tables_stale() -> None:
    conn = the_worked_store()
    stale = dataclasses.replace(kit_files(), inventory_sha256="0" * 64)

    with pytest.raises(Setup) as refused:
        run(conn, WORKED_DRAFT_COMPLETE, kits=(stale,))

    assert refused.value.code == "kit_tables_stale"


def test_a_stale_kit_at_a_location_the_draft_never_names_is_not_read() -> None:
    conn = the_worked_store()
    stale = dataclasses.replace(kit_files(), inventory_sha256="0" * 64)
    draft = a_draft(a_session("push", a_line(start_load=60)), location="gym")

    assert run(conn, toml(draft), kits=(stale,)).version_id == "pv-1"


def test_a_declared_exercise_is_upserted_without_a_template_id() -> None:
    conn = the_worked_store()
    ring = {
        "name": "Ring push-up",
        "load_mode": "bodyweight",
        "equipment_kind": "bodyweight",
        "pattern": "horizontal_push",
        "muscles": {"primary": ["chest"], "secondary": ["triceps"]},
        "hevy_title": "Ring Push Up",
    }
    draft = a_draft(
        a_session("push", a_line("custom_ring_push_up", start_load=None)),
        exercise={"custom_ring_push_up": ring, "custom_hollow_hold": {"hevy_title": "Hollow"}},
    )

    run(conn, toml(draft))

    stored = exercises.get(conn, "custom_ring_push_up")
    assert stored is not None and (stored["source"], stored["hevy_template_id"]) == ("draft", None)
    hollow = exercises.get(conn, "custom_hollow_hold")
    assert hollow is not None and (hollow["hevy_title"], hollow["hevy_template_id"]) == (
        "Hollow",
        "C-0005",
    )


def test_a_new_declared_exercise_missing_a_library_column_is_invalid() -> None:
    draft = a_draft(
        a_session("push", a_line("custom_ring_push_up", start_load=None)),
        exercise={"custom_ring_push_up": {"name": "Ring push-up", "load_mode": "bodyweight"}},
    )

    with pytest.raises(Invalid) as refused:
        run(the_worked_store(), toml(draft))

    assert refused.value.code == "invalid_argument"


def test_a_surplus_phase_fills_the_upper_half_of_the_dose_band() -> None:
    conn = a_library_store()
    a_goal(conn)
    a_phase(conn, "surplus")

    run(conn, toml(a_draft()))

    row = conn.execute("SELECT dose FROM program_version").fetchone()
    assert json.loads(row[0])["per_muscle"] == 15
