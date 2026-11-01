from support.blocks import BENCH_LINE, BOUNDARY, PULL_UP_LINE, two_closed_blocks
from support.check_in_cards import opened
from support.clock import FixedClock, at
from support.kit_fixtures import kit_files
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config

from coach.core.flag import Flag
from coach.services.program import adopt
from coach.services.record import record
from coach.services.status import status
from coach.store.connection import Connection


def signals_at_check_in(conn: Connection) -> dict[str, Flag]:
    return {
        str(f.scope.exercise_id): f
        for f in opened(conn, BOUNDARY).warnings
        if f.code.startswith("cadence_")
    }


def signals_in_status(conn: Connection) -> dict[str, Flag]:
    result = status(
        conn,
        FixedClock(at(BOUNDARY)),
        engine_version="0.4.0",
        pin="0.4.0",
        hevy_on=False,
        exported={},
        units="lb",
    )
    return {str(f.scope.exercise_id): f for f in result.warnings if f.code.startswith("cadence_")}


def test_checkin_open_reports_cadence_slow_on_a_flat_bench_and_a_stalled_pull_up() -> None:
    found = signals_at_check_in(two_closed_blocks())

    assert {k: (f.code, f.params["scheme"]) for k, f in found.items()} == {
        "bb_bench_press": ("cadence_slow", "top_backoff"),
        "pull_up": ("cadence_slow", "double_progression"),
    }
    assert found["bb_bench_press"].params["blocks"] == ["b-2026-10-30", "b-2026-11-23"]
    assert found["bb_bench_press"].params["may_schemes"] == ["wave_531"]


def test_status_reports_the_same_signals() -> None:
    assert set(signals_in_status(two_closed_blocks())) == {"bb_bench_press", "pull_up"}


def test_a_rising_bench_raises_no_signal() -> None:
    rising = (100, 105, 105, 110, 115, 115)

    assert "bb_bench_press" not in signals_at_check_in(two_closed_blocks(bench_tops=rising))


def test_a_leave_warning_decision_leaves_the_signal() -> None:
    conn = two_closed_blocks()
    slow = signals_at_check_in(conn)["bb_bench_press"]
    record(
        conn,
        (
            '[[decision]]\nkind = "leave_warning"\n'
            f'flag = "cadence_slow@exercise:bb_bench_press"\nparams_hash = "{slow.params_hash}"\n'
            'until = 2027-01-31\nbecause = "coach_judgement"\ntext = "a test week first"\n'
        ).encode(),
        file="d.toml",
        clock=FixedClock(at(BOUNDARY)),
    )

    left = signals_at_check_in(conn)["bb_bench_press"].left

    assert left is not None
    assert (left.source, left.text) == ("decision", "a test week first")


def test_a_version_giving_the_exercise_another_scheme_clears_the_signals() -> None:
    conn = two_closed_blocks()
    wave = a_line("bb_bench_press", sets=[{"count": 3}], scheme={"name": "wave_531"})
    adopt(
        conn,
        toml(a_draft(a_session("push", wave, PULL_UP_LINE), kind="amend", because="slow")),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(at(BOUNDARY)),
    )

    assert signals_at_check_in(conn) == {}


def test_a_version_keeping_the_scheme_clears_the_signals() -> None:
    conn = two_closed_blocks()
    more_sets = {**PULL_UP_LINE, "sets": [{"count": 4, "reps": [5, 8], "rpe": 8}]}
    adopt(
        conn,
        toml(a_draft(a_session("push", BENCH_LINE, more_sets), kind="amend", because="slow")),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(at(BOUNDARY)),
    )

    assert signals_at_check_in(conn) == {}


def test_adopt_reads_the_open_signals_for_scheme_change_off_signal() -> None:
    conn = two_closed_blocks()
    wave = a_line("bb_bench_press", sets=[{"count": 3}], scheme={"name": "wave_531"})
    linear = {**PULL_UP_LINE, "scheme": {"name": "linear"}}

    result = adopt(
        conn,
        toml(a_draft(a_session("push", wave, linear), kind="amend", because="slow")),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(at(BOUNDARY)),
        dry_run=True,
    )

    assert [w.key for w in result.warnings if w.code == "scheme_change_off_signal"] == [
        "scheme_change_off_signal@line:push/pull_up"
    ]
