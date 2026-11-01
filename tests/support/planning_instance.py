"""An instance on disk ready to plan: the fixture kit in pounds, the catalogue, a Goal and a
one-session squat version adopted through `program adopt`."""

import shutil
from pathlib import Path

from coach.core.goal import Goal
from coach.store import exercises, goals
from coach.store.catalogue import seed_catalogue
from coach.store.connection import Connection, open_store
from support.cli import Run, run_coach
from support.clock import FixedClock
from support.instances import an_instance
from support.kit_fixtures import INVENTORY, TABLES
from support.plans import SQUAT_LINE, SQUAT_TEMPLATE
from support.program_drafts import a_draft, a_session, toml
from support.programs import GYM, HOME

ENGINE = "0.3.0"
CLOCK = FixedClock()


def coach(*argv: str) -> Run:
    return run_coach(*argv, clock=CLOCK)


def a_planning_instance(root: Path, *, hevy: bool = False) -> Path:
    """Run from inside `root`; the caller chdirs there and pins the engine version."""
    an_instance(root, pin=ENGINE, hevy=hevy, location={"home": HOME, "gym": GYM})
    text = (root / "coach.toml").read_text().replace('units = "kg"', 'units = "lb"', 1)
    (root / "coach.toml").write_text(text)
    (root / "kit").mkdir()
    shutil.copyfile(INVENTORY, root / "kit" / "home.json")
    shutil.copyfile(TABLES, root / "kit" / "home.achievable.json")
    (root / ".coach").mkdir()
    conn = open_store(root / ".coach" / "coach.db")
    with conn:
        seed_catalogue(conn)
        exercises.update(conn, "bb_back_squat", {"hevy_template_id": SQUAT_TEMPLATE})
        goals.insert(
            conn,
            id_="g-0001",
            goal=Goal("hypertrophy", "first goal", ("bb_back_squat",), ""),
            milestone_ids=(),
            adopted="2026-10-01",
            draft_hash="sha256:g",
            recorded_at="2026-10-01T12:00:00+00:00",
        )
    conn.close()
    return root


def adopt_the_squat_version(root: Path) -> None:
    (root / "v1.toml").write_bytes(toml(a_draft(a_session("lower", SQUAT_LINE))))
    assert coach("program", "adopt", "v1.toml").code == 0


def the_store(root: Path) -> Connection:
    return open_store(root / ".coach" / "coach.db")
