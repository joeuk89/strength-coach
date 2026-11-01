import datetime
from typing import Any

import pytest
from support.clock import FixedClock
from support.ledger import a_hevy_workout, a_store, an_exercise

from coach.core.errors import Invalid
from coach.services.query import ledger
from coach.services.record import RecordResult, record
from coach.store.connection import Connection

TODAY = datetime.date(2026, 10, 30)
WORKOUT = "b7e2c1a0-5d3f-4e8a-9c21-7f0a4d6b9e13"
EXPOSURE = f"exposure:{WORKOUT}/bb_bench_press"
REASON = 'because = "coach_judgement"\ntext = "agreed"\n'


def run(conn: Connection, text: str) -> RecordResult:
    return record(conn, text.encode("utf-8"), file="d.toml", clock=FixedClock())


def decisions(conn: Connection, *, open_: bool = False) -> list[dict[str, Any]]:
    return ledger(conn, kind="decision", id_=None, open_=open_, today=TODAY, last=None).rows


def in_force(conn: Connection) -> list[str]:
    return [id_ for (id_,) in conn.execute("SELECT id FROM decision_in_force ORDER BY id")]


def a_decision(kind: str, body: str = "") -> str:
    return f'[[decision]]\nkind = "{kind}"\n{body}{REASON}'


def training_max(load: int) -> str:
    return a_decision("training_max", f'exercise = "bb_bench_press"\nload = {load}\n')


def a_store_with_bench() -> Connection:
    conn = a_store()
    an_exercise(conn, "bb_bench_press")
    return conn


def a_session(conn: Connection, session_id: str = "conditioning") -> str:
    """A session id raised the one way this engine build can: a niggle's rehab session."""
    an_exercise(conn, "dead_hang", load_mode="duration", equipment_kind="bodyweight")
    run(
        conn,
        '[[niggle]]\nsite = "elbow"\ndate = 2026-10-01\nstatus = "reported"\n'
        f'[niggle.rehab]\nsession = "{session_id}"\ntitle = "Hangs"\ncadence = "daily"\n'
        '[[niggle.rehab.line]]\nexercise = "dead_hang"\nrest_s = 60\n'
        "[[niggle.rehab.line.sets]]\ncount = 3\nduration_s = 30\n",
    )
    return session_id


def test_a_training_max_decision_is_written_with_its_exercise_as_a_column() -> None:
    conn = a_store_with_bench()

    result = run(conn, training_max(100))

    assert result.ids == {"decision": ["d-0001"]}
    [row] = decisions(conn)
    assert (row["id"], row["kind"], row["exercise_id"], row["session_id"]) == (
        "d-0001",
        "training_max",
        "bb_bench_press",
        None,
    )
    assert (row["params"], row["until"], row["because"], row["text"]) == (
        {"load": 100.0},
        None,
        "coach_judgement",
        "agreed",
    )
    assert in_force(conn) == ["d-0001"]


def test_a_second_training_max_on_the_same_exercise_supersedes_the_first() -> None:
    conn = a_store_with_bench()
    run(conn, training_max(100))

    run(conn, training_max(105))

    assert in_force(conn) == ["d-0002"]
    first = next(r for r in decisions(conn) if r["id"] == "d-0001")
    assert (first["superseded_by"], first["retired_by"]) == ("d-0002", None)


def test_a_training_max_on_another_exercise_supersedes_nothing() -> None:
    conn = a_store_with_bench()
    an_exercise(conn, "bb_back_squat")
    run(conn, training_max(100))

    run(conn, training_max(140).replace("bb_bench_press", "bb_back_squat"))

    assert in_force(conn) == ["d-0001", "d-0002"]


def test_a_retire_row_sets_retired_by_and_the_retired_decision_leaves_in_force() -> None:
    conn = a_store_with_bench()
    run(conn, training_max(100))

    result = run(conn, a_decision("retire", 'decision = "d-0001"\n'))

    assert result.ids == {"decision": ["d-0002"]}
    assert in_force(conn) == []
    rows = {r["id"]: r for r in decisions(conn)}
    assert rows["d-0001"]["retired_by"] == "d-0002"
    assert rows["d-0002"]["params"] == {"decision": "d-0001"}


@pytest.mark.parametrize("target", ["d-0009", "d-0001"])
def test_retiring_a_decision_that_is_not_in_force_is_refused(target: str) -> None:
    conn = a_store_with_bench()
    run(conn, training_max(100))
    run(conn, training_max(105))

    with pytest.raises(Invalid) as raised:
        run(conn, a_decision("retire", f'decision = "{target}"\n'))

    assert target in raised.value.message


OVERRIDE = """
session = "conditioning"
exercise = "dead_hang"
override = {{ kind = "hold" }}
until = {until}
"""


@pytest.mark.parametrize(("until", "admitted"), [("2026-12-25", True), ("2026-12-26", False)])
def test_an_override_decision_lasts_at_most_eight_weeks(until: str, admitted: bool) -> None:
    conn = a_store()
    a_session(conn)
    text = a_decision("override", OVERRIDE.format(until=until))

    if admitted:
        run(conn, text)
        [row] = decisions(conn)
        assert (row["session_id"], row["exercise_id"], row["params"]) == (
            "conditioning",
            "dead_hang",
            {"override": {"kind": "hold"}},
        )
    else:
        with pytest.raises(Invalid) as raised:
            run(conn, text)
        assert "2026-12-25" in raised.value.message


def test_an_override_on_the_same_line_and_kind_supersedes_and_another_kind_does_not() -> None:
    conn = a_store()
    a_session(conn)
    run(conn, a_decision("override", OVERRIDE.format(until="2026-12-01")))

    run(conn, a_decision("override", OVERRIDE.format(until="2026-12-20")))
    run(
        conn,
        a_decision(
            "override",
            OVERRIDE.format(until="2026-12-20").replace('"hold" ', '"pin_load", load = 20 '),
        ),
    )

    assert in_force(conn) == ["d-0002", "d-0003"]


@pytest.mark.parametrize(
    "override",
    [
        '{ kind = "light_week" }',
        '{ kind = "hold", load = 20 }',
        "{ load = 20 }",
        '{ kind = "pin_load" }',
        '{ kind = "swap_exercise", start_load = 20 }',
    ],
)
def test_an_override_decision_wraps_one_line_scope_kind_with_its_params(override: str) -> None:
    conn = a_store()
    a_session(conn)
    body = OVERRIDE.format(until="2026-12-01").replace('{ kind = "hold" }', override)

    with pytest.raises(Invalid):
        run(conn, a_decision("override", body))


def test_park_and_resume_on_one_session_supersede_each_other() -> None:
    conn = a_store()
    a_session(conn)
    run(conn, a_decision("park_session", 'session = "conditioning"\n'))

    run(conn, a_decision("resume_session", 'session = "conditioning"\n'))

    assert in_force(conn) == ["d-0002"]


def test_a_decision_on_a_session_no_version_or_niggle_raised_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), a_decision("park_session", 'session = "nope"\n'))

    assert "nope" in raised.value.message
    assert raised.value.code == "draft_ref_unresolved"


def test_a_decline_ceiling_lasts_to_the_sunday_of_the_week_it_is_made_in() -> None:
    conn = a_store()

    run(conn, a_decision("decline_ceiling", 'block = "b-2026-10-05"\n'))

    [row] = decisions(conn)
    assert (row["until"], row["params"]) == ("2026-11-01", {"block": "b-2026-10-05"})


def test_a_decline_ceiling_with_another_until_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        run(
            a_store(), a_decision("decline_ceiling", 'block = "b-2026-10-05"\nuntil = 2026-11-08\n')
        )

    assert "2026-11-01" in raised.value.message


def test_a_later_defer_deep_review_wins() -> None:
    conn = a_store()
    run(conn, a_decision("defer_deep_review", "until = 2026-11-07\n"))

    run(conn, a_decision("defer_deep_review", "until = 2026-11-14\n"))

    assert in_force(conn) == ["d-0002"]


def test_against_research_rows_supersede_nothing() -> None:
    conn = a_store()
    body = 'ref = "rn:deloads.3"\n'
    run(conn, a_decision("against_research", body))

    run(conn, a_decision("against_research", body.replace("3", "4")))

    assert in_force(conn) == ["d-0001", "d-0002"]


def test_a_leave_warning_names_one_calendar_free_key_and_supersedes_the_earlier() -> None:
    conn = a_store()
    body = (
        'flag = "cadence_slow@exercise:bb_bench_press"\nparams_hash = "sha256:ab"\n'
        "until = 2026-12-01\n"
    )
    run(conn, a_decision("leave_warning", body))

    run(conn, a_decision("leave_warning", body.replace("12-01", "12-08")))

    assert in_force(conn) == ["d-0002"]


def test_an_activity_cap_cites_a_niggle_raised_in_the_same_file_by_key() -> None:
    conn = a_store()

    run(
        conn,
        '[[niggle]]\nkey = "hamstring"\nsite = "hamstring"\ndate = 2026-10-24\n'
        'status = "easing"\n'
        '[[decision]]\nkind = "activity_cap"\nactivity_kind = "run"\nweekly_distance = 17\n'
        'single_distance = 6\nbecause = "pain"\ntext = "while the hamstring settles"\n'
        'evidence = ["niggle:@hamstring", "block:b-2026-10-05", "rn:deloads.3"]\n',
    )

    [row] = decisions(conn)
    assert row["params"] == {
        "activity_kind": "run",
        "weekly_distance": 17.0,
        "single_distance": 6.0,
    }
    assert row["evidence"] == ["niggle:n-0001", "block:b-2026-10-05", "rn:deloads.3"]


def test_evidence_naming_no_stored_record_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        run(
            a_store(),
            a_decision("defer_deep_review", 'until = 2026-11-07\nevidence = ["niggle:n-0004"]\n'),
        )

    assert "niggle:n-0004" in raised.value.message
    assert raised.value.code == "draft_ref_unresolved"


def test_evidence_may_cite_an_exposure_on_a_stored_workout() -> None:
    conn = a_store_with_bench()
    a_hevy_workout(conn, WORKOUT)

    run(conn, training_max(100).replace(REASON, REASON + f'evidence = ["{EXPOSURE}"]\n'))

    [row] = decisions(conn)
    assert row["evidence"] == [EXPOSURE]


def test_evidence_citing_an_exposure_on_an_unstored_workout_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        run(
            a_store_with_bench(),
            training_max(100).replace(REASON, REASON + f'evidence = ["{EXPOSURE}"]\n'),
        )

    assert EXPOSURE in raised.value.message
    assert raised.value.code == "draft_ref_unresolved"


def test_ledger_open_keeps_decisions_in_force_today() -> None:
    conn = a_store_with_bench()
    run(
        conn,
        a_decision(
            "safety_ceiling", 'exercise = "bb_bench_press"\nload = 120\nuntil = 2026-10-29\n'
        )
        + a_decision("defer_deep_review", "until = 2026-10-30\n"),
    )

    assert [r["id"] for r in decisions(conn, open_=True)] == ["d-0002"]
    assert len(decisions(conn)) == 2


def test_re_running_a_decision_draft_returns_the_same_ids() -> None:
    conn = a_store_with_bench()
    first = run(conn, training_max(100))

    assert run(conn, training_max(100)) == first
    assert in_force(conn) == ["d-0001"]


def test_retiring_a_decision_that_is_not_stored_is_an_unresolved_ref() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), a_decision("retire", 'decision = "d-0009"\n'))

    assert raised.value.code == "draft_ref_unresolved"


def test_a_decision_on_an_exercise_the_library_lacks_is_an_unknown_exercise() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), training_max(100))

    assert raised.value.code == "unknown_exercise"
