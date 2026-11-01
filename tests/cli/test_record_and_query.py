import io
from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.instances import an_instance

from coach.cli import app
from coach.core.clock import Clock

ENGINE = "0.3.0"

SEVEN_KINDS = """
[[note]]
date = 2026-10-29
text = "left knee clicks"
about = "exercise:@hold"

[[weigh_in]]
date = 2026-10-29
kg = 82.4

[[sleep_night]]
night = 2026-10-28
hours = 6.5

[[activity]]
date = 2026-10-27
kind = "run"
minutes = 30
rpe = 6
quality = false

[[status_span]]
kind = "travel"
from_date = 2026-11-02

[[workout]]
date = 2026-10-13
title = "PT session"
minutes = 60
session_rpe = 9

[[exercise]]
id = "custom_hollow_hold"
key = "hold"
name = "Hollow hold"
load_mode = "duration"
equipment_kind = "bodyweight"
pattern = "core"
muscles = {primary = ["abdominals"], secondary = []}
hevy_template_id = "A1B2C3D4-0000"
hevy_title = "Hollow Hold"
"""


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path, pin=ENGINE, hevy=True)
    monkeypatch.chdir(root)
    return root


def draft(root: Path, text: str, name: str = "d.toml") -> str:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return name


def coach(*argv: str) -> Run:
    return run_coach(*argv, clock=FixedClock())


def test_record_writes_all_seven_kinds_and_a_re_run_returns_the_same_ids(instance: Path) -> None:
    path = draft(instance, SEVEN_KINDS)

    first = coach("record", path)
    second = coach("record", path)

    assert first.code == 0
    assert first.envelope["result"]["ids"] == {
        "note": ["an-0001"],
        "weigh_in": ["wi-0001"],
        "sleep_night": ["sn-0001"],
        "activity": ["ac-0001"],
        "status_span": ["ss-0001"],
        "workout": ["w-0001"],
        "exercise": ["custom_hollow_hold"],
    }
    assert first.envelope["result"]["draft_hash"].startswith("sha256:")
    assert second.code == 0
    assert second.envelope["result"] == first.envelope["result"]
    weigh_ins = coach("query", "readings", "--kind", "weigh_in")
    assert weigh_ins.envelope["result"]["count"] == 1


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ('[[observation]]\ntext = "drift adds volume"\n', "record_kind_not_allowed"),
        ('[[weigh_in]]\ndate = 2026-10-29\nkg = 82\nunit = "kg"\n', "unknown_key"),
        ('[[note]]\ndate = 2026-10-29\ntext = "x"\nabout = "niggle:@x"\n', "draft_ref_unresolved"),
    ],
)
def test_a_bad_draft_is_exit_1_with_its_code_and_writes_nothing(
    instance: Path, text: str, code: str
) -> None:
    run = coach("record", draft(instance, text))

    assert run.code == 1
    assert run.envelope["error"]["code"] == code
    assert coach("query", "ledger", "--kind", "note").envelope["result"]["count"] == 0


def test_a_correction_leaves_one_live_weigh_in_and_a_duplicate_is_exit_1(instance: Path) -> None:
    coach("record", draft(instance, "[[weigh_in]]\ndate = 2026-10-29\nkg = 28.4\n", "a.toml"))

    fixed = coach(
        "record",
        draft(
            instance,
            '[[weigh_in]]\nwithdraws = "wi-0001"\n[[weigh_in]]\ndate = 2026-10-29\nkg = 82.4\n',
            "b.toml",
        ),
    )
    duplicate = coach(
        "record", draft(instance, "[[weigh_in]]\ndate = 2026-10-29\nkg = 82\n", "c.toml")
    )

    assert fixed.envelope["result"]["withdrawn"] == ["wi-0001"]
    assert duplicate.code == 1
    assert duplicate.envelope["error"]["code"] == "reading_duplicate"
    live = coach("query", "readings", "--kind", "weigh_in").envelope["result"]
    assert [(row["id"], row["kg"]) for row in live["rows"]] == [("wi-0003", 82.4)]


def test_a_manual_workout_never_reaches_hevy(instance: Path) -> None:
    clients: list[FakeHevy] = []

    def make_client(key: str, audit: Path, clock: Clock) -> FakeHevy:
        clients.append(FakeHevy(clock))
        return clients[-1]

    out = io.StringIO()
    code = app.main(
        ["record", draft(instance, "[[workout]]\ndate = 2026-10-13\nminutes = 60\n")],
        {},
        out,
        io.StringIO(),
        make_client=make_client,
        clock=FixedClock(),
    )

    assert code == 0
    assert all(client.audit == [] for client in clients)
    current = coach("query", "ledger", "--kind", "workout", "--open").envelope["result"]["rows"]
    assert [(row["id"], row["source"]) for row in current] == [("w-0001", "manual")]


def test_query_readings_keeps_the_last_n_and_says_more_exist(instance: Path) -> None:
    rows = "".join(f"[[weigh_in]]\ndate = 2026-10-0{d}\nkg = 8{d}\n" for d in range(1, 6))
    coach("record", draft(instance, rows))

    run = coach("query", "readings", "--kind", "weigh_in", "--last", "3")

    assert run.code == 0
    result = run.envelope["result"]
    assert [row["date"] for row in result["rows"]] == ["2026-10-05", "2026-10-04", "2026-10-03"]
    assert (result["count"], result["truncated"]) == (5, True)


def test_a_missing_draft_file_is_exit_1(instance: Path) -> None:
    run = coach("record", "nowhere.toml")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


def test_an_unknown_view_is_exit_1(instance: Path) -> None:
    run = coach("query", "readingz")

    assert run.code == 1
    assert run.envelope["verb"] == "query"


def test_query_ledger_by_id(instance: Path) -> None:
    coach("record", draft(instance, '[[note]]\ndate = 2026-10-29\ntext = "knee clicks"\n'))

    run = coach("query", "ledger", "--id", "an-0001")

    assert run.envelope["result"]["rows"][0]["text"] == "knee clicks"


COACHING = """
[[niggle]]
key = "hamstring"
site = "left hamstring"
date = 2026-10-24
status = "easing"

[[niggle.constraints]]
kind = "rpe_cap"
pattern = "hinge"
value = 7

[[follow_up]]
raised = 2026-10-24
text = "Re-test the hinge"
due = 2026-11-14

[[decision]]
kind = "activity_cap"
activity_kind = "run"
weekly_distance = 17
because = "pain"
text = "while the hamstring settles"
evidence = ["niggle:@hamstring"]
"""


def test_record_writes_niggles_follow_ups_and_decisions_and_query_reads_them(
    instance: Path,
) -> None:
    run = coach("record", draft(instance, COACHING))

    assert run.code == 0
    assert run.envelope["result"]["ids"] == {
        "niggle": ["n-0001"],
        "follow_up": ["f-0001"],
        "decision": ["d-0001"],
    }
    niggle = coach("query", "ledger", "--id", "n-0001").envelope["result"]["rows"][0]
    assert niggle["constraints"] == [
        {"kind": "rpe_cap", "exercise_id": None, "pattern": "hinge", "value": 7.0}
    ]
    decisions = coach("query", "ledger", "--kind", "decision", "--open").envelope["result"]
    assert [row["evidence"] for row in decisions["rows"]] == [["niggle:n-0001"]]


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (
            '[[niggle]]\nsite = "knee"\ndate = 2026-10-29\nstatus = "resolved"\n'
            '[[niggle.constraints]]\nkind = "no_added_load"\n',
            "niggle_constraint_on_resolved",
        ),
        (
            '[[decision]]\nkind = "defer_deep_review"\nuntil = 2026-11-07\noutcome = "taken"\n'
            'because = "schedule"\ntext = "busy week"\n',
            "unknown_key",
        ),
        (
            '[[decision]]\nkind = "block_reset"\nbecause = "schedule"\ntext = "x"\n',
            "invalid_argument",
        ),
    ],
)
def test_a_bad_coaching_record_is_exit_1_and_writes_nothing(
    instance: Path, text: str, code: str
) -> None:
    run = coach("record", draft(instance, text))

    assert run.code == 1
    assert run.envelope["error"]["code"] == code
    for kind in ("niggle", "decision"):
        assert coach("query", "ledger", "--kind", kind).envelope["result"]["count"] == 0
