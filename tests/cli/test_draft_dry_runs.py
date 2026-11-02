import hashlib
from contextlib import closing
from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.goals import STRENGTH, WORKED
from support.instances import an_instance

from coach.cli import app
from coach.cli.declaration import MakeClient
from coach.core.clock import Clock
from coach.store.catalogue import seed_catalogue
from coach.store.connection import open_store

ENGINE = "0.3.0"
CLOCK = FixedClock()
STORE = Path(".coach") / "coach.db"

DRAFTS = {
    "record": "[[weigh_in]]\ndate = 2026-10-29\nkg = 82.4\n",
    "goal adopt": WORKED,
    "checkin record": 'date = 2026-10-30\ntier = "light"\nread = "a steady week"\n',
}
REFUSED = {
    "record": (
        '[[note]]\ndate = 2026-10-29\ntext = "x"\nabout = "niggle:@x"\n',
        "draft_ref_unresolved",
    ),
    "goal adopt": (STRENGTH.replace('["bb_bench_press"]', '["bench"]'), "unknown_exercise"),
    "checkin record": (
        DRAFTS["checkin record"] + '[phase]\nclose = true\nbecause = "done"\n',
        "state_conflict",
    ),
}
VERBS = list(DRAFTS)


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path, pin=ENGINE)
    (root / ".coach").mkdir()
    with closing(open_store(root / STORE)) as conn, conn:
        seed_catalogue(conn)
    monkeypatch.chdir(root)
    return root


def no_hevy(key: str, audit_path: Path, clock: Clock) -> FakeHevy:
    return FakeHevy(clock)


MAKE_CLIENT: MakeClient = no_hevy


def coach(*argv: str) -> Run:
    return run_coach(*argv, clock=CLOCK, make_client=MAKE_CLIENT)


def run(verb: str, text: str, *flags: str) -> Run:
    Path("draft.toml").write_text(text, encoding="utf-8")
    return coach(*verb.split(), "draft.toml", *flags)


def store_hash(root: Path) -> str:
    return hashlib.sha256((root / STORE).read_bytes()).hexdigest()


@pytest.mark.parametrize("verb", VERBS)
def test_a_dry_run_returns_the_real_result_and_the_store_file_is_unchanged(
    instance: Path, verb: str
) -> None:
    before = store_hash(instance)

    dry = run(verb, DRAFTS[verb], "--dry-run")

    assert dry.code == 0, dry.stdout
    assert dry.envelope["result"]["dry_run"] is True
    assert dry.envelope["result"]["no_op"] is False
    assert store_hash(instance) == before
    real = run(verb, DRAFTS[verb])
    assert real.code == 0, real.stdout
    assert real.envelope["result"] == {
        k: v for k, v in dry.envelope["result"].items() if k not in ("dry_run", "no_op")
    }


def test_a_dry_run_record_shows_no_new_row_in_query(instance: Path) -> None:
    run("record", DRAFTS["record"], "--dry-run")

    assert coach("query", "readings", "--kind", "weigh_in").envelope["result"]["count"] == 0


def test_a_dry_run_goal_adopt_leaves_status_without_a_goal(instance: Path) -> None:
    run("goal adopt", WORKED, "--dry-run")

    assert coach("status").envelope["result"]["goal"] is None


@pytest.mark.parametrize("verb", VERBS)
def test_a_dry_run_of_a_stored_draft_returns_the_stored_ids_as_a_no_op(
    instance: Path, verb: str
) -> None:
    real = run(verb, DRAFTS[verb])
    before = store_hash(instance)

    dry = run(verb, DRAFTS[verb], "--dry-run")

    assert dry.envelope["result"] == real.envelope["result"] | {"dry_run": True, "no_op": True}
    assert store_hash(instance) == before


@pytest.mark.parametrize("verb", VERBS)
def test_a_refused_draft_fails_the_dry_run_as_it_fails_the_real_run(
    instance: Path, verb: str
) -> None:
    text, code = REFUSED[verb]
    before = store_hash(instance)

    dry = run(verb, text, "--dry-run")

    assert (dry.code, dry.envelope["error"]["code"]) == (1, code)
    assert store_hash(instance) == before
    real = run(verb, text)
    assert (dry.code, dry.envelope["error"]) == (real.code, real.envelope["error"])


@pytest.mark.parametrize("verb", VERBS)
def test_schema_and_help_show_the_dry_run(verb: str) -> None:
    schema = coach("schema", verb).envelope["result"]
    usage = coach(*verb.split(), "--help").envelope["result"]["usage"]

    assert "dry_run" in schema["input"]["properties"]
    assert "--dry-run" in usage
