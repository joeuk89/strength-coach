import datetime
from dataclasses import replace
from typing import Any, cast

import pytest
from support.clock import FixedClock
from support.ledger import a_store, an_exercise

from coach.core.errors import Invalid
from coach.services.query import ledger
from coach.services.record import RecordResult, record
from coach.store.connection import Connection

TODAY = datetime.date(2026, 10, 30)

HAMSTRING = """
[[niggle]]
key = "hamstring"
site = "left hamstring"
opened = 2026-10-10
date = 2026-10-24
status = "easing"
text = "tight after runs"

[[niggle.constraints]]
kind = "rpe_cap"
pattern = "hinge"
value = 7

[[niggle.constraints]]
kind = "no_added_load"
"""


def run(conn: Connection, text: str) -> RecordResult:
    return record(conn, text.encode("utf-8"), file="d.toml", clock=FixedClock())


def niggles(conn: Connection, *, open_: bool = False) -> list[dict[str, Any]]:
    return ledger(conn, kind="niggle", id_=None, open_=open_, today=TODAY, last=None).rows


def events(row: dict[str, Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], row["events"])


def test_a_new_niggle_writes_the_niggle_its_first_event_and_the_constraints_in_force() -> None:
    conn = a_store()

    result = run(conn, HAMSTRING)

    assert result.ids == {"niggle": ["n-0001"]}
    [row] = niggles(conn)
    assert (row["id"], row["site"], row["opened"], row["status"]) == (
        "n-0001",
        "left hamstring",
        "2026-10-10",
        "easing",
    )
    assert row["constraints"] == [
        {"kind": "rpe_cap", "exercise_id": None, "pattern": "hinge", "value": 7.0},
        {"kind": "no_added_load", "exercise_id": None, "pattern": None, "value": None},
    ]
    assert [(e["id"], e["date"], e["status"]) for e in events(row)] == [
        ("ne-0001", "2026-10-24", "easing")
    ]


def test_a_later_event_with_a_smaller_set_leaves_its_rows_binding() -> None:
    conn = a_store()
    run(conn, HAMSTRING)

    result = run(
        conn,
        '[[niggle]]\nniggle = "n-0001"\ndate = 2026-10-29\nstatus = "easing"\n'
        '[[niggle.constraints]]\nkind = "rpe_cap"\npattern = "hinge"\nvalue = 8\n',
    )

    assert result.ids == {"niggle": ["n-0001"]}
    [row] = niggles(conn)
    assert row["constraints"] == [
        {"kind": "rpe_cap", "exercise_id": None, "pattern": "hinge", "value": 8.0}
    ]
    assert [len(e["constraints"]) for e in events(row)] == [2, 1]
    assert row["date"] == "2026-10-29"


def test_a_resolved_event_carrying_constraints_is_refused_and_writes_nothing() -> None:
    conn = a_store()
    run(conn, HAMSTRING)

    with pytest.raises(Invalid) as raised:
        run(
            conn,
            '[[niggle]]\nniggle = "n-0001"\ndate = 2026-10-29\nstatus = "resolved"\n'
            '[[niggle.constraints]]\nkind = "no_added_load"\n',
        )

    assert raised.value.code == "niggle_constraint_on_resolved"
    assert len(events(niggles(conn)[0])) == 1


def test_a_resolved_niggle_binds_nothing_and_leaves_the_open_list() -> None:
    conn = a_store()
    run(conn, HAMSTRING)

    run(conn, '[[niggle]]\nniggle = "n-0001"\ndate = 2026-10-29\nstatus = "resolved"\n')

    [row] = niggles(conn)
    assert (row["status"], row["constraints"]) == ("resolved", [])
    assert niggles(conn, open_=True) == []


def test_an_event_on_a_niggle_that_is_not_stored_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), '[[niggle]]\nniggle = "n-0009"\ndate = 2026-10-29\nstatus = "easing"\n')

    assert "n-0009" in raised.value.message
    assert raised.value.code == "draft_ref_unresolved"


@pytest.mark.parametrize(
    "constraint",
    [
        'kind = "load_cap"\npattern = "hinge"\nvalue = 60',
        'kind = "rpe_cap"\nexercise = "bb_deadlift"\npattern = "hinge"\nvalue = 7',
        'kind = "rpe_cap"\npattern = "hinge"',
        'kind = "no_added_load"\nvalue = 3',
        'kind = "avoid"',
        'kind = "cap"\nvalue = 3',
    ],
)
def test_a_constraint_outside_its_scope_table_is_refused(constraint: str) -> None:
    text = (
        '[[niggle]]\nsite = "knee"\ndate = 2026-10-29\nstatus = "reported"\n'
        f"[[niggle.constraints]]\n{constraint}\n"
    )

    with pytest.raises(Invalid):
        run(a_store(), text)


def test_a_constraint_on_an_exercise_the_library_lacks_is_refused() -> None:
    text = (
        '[[niggle]]\nsite = "knee"\ndate = 2026-10-29\nstatus = "reported"\n'
        '[[niggle.constraints]]\nkind = "avoid"\nexercise = "nope"\n'
    )

    with pytest.raises(Invalid) as raised:
        run(a_store(), text)

    assert "nope" in raised.value.message
    assert raised.value.code == "unknown_exercise"


REHAB = """
[[niggle]]
site = "left shoulder"
date = 2026-10-24
status = "reported"

[niggle.rehab]
session = "shoulder_rehab"
title = "Shoulder rehab"
cadence = "daily"

[[niggle.rehab.line]]
exercise = "band_external_rotation"
rest_s = 30

[[niggle.rehab.line.sets]]
count = 2
reps = 15
"""


def test_a_niggle_with_a_rehab_session_raises_the_session_with_hold_lines() -> None:
    conn = a_store()
    an_exercise(conn, "band_external_rotation", load_mode="band", equipment_kind="band")

    run(conn, REHAB)

    [row] = niggles(conn)
    assert row["rehab_session_id"] == "shoulder_rehab"
    rehab = row["rehab_session"]
    assert (rehab["title"], rehab["tier"], rehab["cadence"]) == (
        "Shoulder rehab",
        "optional",
        "daily",
    )
    assert rehab["lines"] == [
        {
            "exercise_id": "band_external_rotation",
            "position": 0,
            "load_mode": None,
            "set_groups": [{"count": 2, "type": "working", "reps": 15}],
            "rest_s": 30,
            "cues": None,
            "scheme": {"name": "hold"},
            "start_load": None,
            "superset": None,
        }
    ]
    assert run_manual_workout_on(conn, "shoulder_rehab") == ["w-0001"]


def run_manual_workout_on(conn: Connection, session_id: str) -> list[str]:
    text = f'[[workout]]\ndate = 2026-10-25\nsession_id = "{session_id}"\nminutes = 10\n'
    return run(conn, text).ids["workout"]


def test_a_rehab_session_on_a_later_event_is_refused() -> None:
    conn = a_store()
    run(conn, HAMSTRING)
    text = REHAB.replace('site = "left shoulder"', 'niggle = "n-0001"')

    with pytest.raises(Invalid) as raised:
        run(conn, text)

    assert "rehab" in raised.value.message


def test_re_running_a_niggle_draft_returns_the_same_ids_and_writes_nothing() -> None:
    conn = a_store()
    first = run(conn, HAMSTRING)

    second = run(conn, HAMSTRING)

    assert second == replace(first, no_op=True)
    assert len(events(niggles(conn)[0])) == 1


def test_a_rehab_line_on_an_exercise_the_library_lacks_is_an_unknown_exercise() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), REHAB)

    assert raised.value.code == "unknown_exercise"


def test_a_rehab_session_reusing_a_session_id_is_a_duplicate_id() -> None:
    conn = a_store()
    an_exercise(conn, "band_external_rotation", load_mode="band", equipment_kind="band")
    run(conn, REHAB)

    with pytest.raises(Invalid) as raised:
        run(conn, REHAB.replace("left shoulder", "right shoulder"))

    assert raised.value.code == "duplicate_id"
