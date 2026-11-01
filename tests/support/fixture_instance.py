"""The Fixture instance (testing.md, "Fixtures"): a year of one program, built through `init`,
`store` functions and the verbs, then copied as git sees it into `tests/fixtures/instance/`.

Regenerate it from `tests/` with `uv run python -m support.fixture_instance`.
"""

import datetime
import json
import os
import shutil
import sys
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from coach.cli import app
from coach.core.clock import Clock
from coach.core.units import KG_PER_LB
from coach.render.toml import dumps
from coach.store import exercises, workouts
from coach.store.connection import open_store
from support.cli import Run, run_coach
from support.clock import FixedClock, at
from support.fake_hevy import FakeHevy
from support.kit_fixtures import INVENTORY, TABLES
from support.program_drafts import toml

PIN = "1.0.0"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instance"
KEY = {"HEVY_API_KEY": "fixture-key"}
# Today in the instance: the Friday of the week its plan in force covers.
TODAY = datetime.date(2026, 10, 30)
PLAN_WEEK = datetime.date(2026, 10, 26)
ADOPTED = datetime.date(2025, 11, 3)
WEEKS = 52
SETS = 2
UNTRACKED = (".git", ".coach", ".env")

GYM: dict[str, Any] = {
    "kind": "grid",
    "implements": {"barbell": "bar", "dumbbell": "rack", "cable": "stack", "machine": "stack"},
    "implement": {
        "bar": {"increment": 5, "base": 45},
        "rack": {"rack": [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]},
        "stack": {"increment": 10},
    },
}
HOME: dict[str, Any] = {
    "kind": "plate-pool",
    "kit": "home",
    "collars": "clamp",
    "dumbbells": "pair",
    "implements": {"barbell": "barbell", "dumbbell": "dumbbell"},
}

# (session, weekday, ((exercise, start load in lb, weekly step in lb), ...)); a step of 0 stalls.
WEEKLY: tuple[tuple[str, str, tuple[tuple[str, float, float], ...]], ...] = (
    ("lower-a", "mon", (("bb_back_squat", 135, 2.5), ("bb_romanian_deadlift", 135, 0))),
    ("upper-a", "tue", (("bb_bench_press", 115, 2.5), ("bb_bent_over_row", 95, 0))),
    ("lower-b", "wed", (("bb_deadlift", 185, 2.5), ("db_lunge", 25, 0))),
    ("upper-b", "thu", (("bb_overhead_press", 75, 1), ("db_row", 40, 0))),
    ("arms", "fri", (("ez_bar_curl", 55, 0), ("cable_triceps_pushdown", 40, 0))),
    ("upper-c", "sat", (("bb_incline_bench_press", 95, 0), ("cable_seated_row", 90, 0))),
    ("lower-c", "sun", (("bb_front_squat", 95, 0), ("bb_hip_thrust", 135, 0))),
)
STANDING: tuple[tuple[str, str, float], ...] = (
    ("core-a", "cable_crunch", 60),
    ("core-b", "db_farmers_walk", 40),
    ("calves", "db_calf_raise", 30),
    ("shoulders", "db_lateral_raise", 15),
)


def generate(root: Path) -> None:
    """Build the instance in `root`, an empty directory the caller has made the working one, with
    `app.engine_version` reporting PIN and git's identity set."""
    clock = FixedClock(at(TODAY))
    hevy = FakeHevy(clock)
    coach = _coach(clock, hevy)
    _ok(coach("init", "--defaults", "--timezone", "UTC", "--units", "lb", "--hevy", "yes"))
    _athlete_files(root)
    _library(root)
    clock.moment = at(ADOPTED)
    _ok(coach("import"))
    _ok(coach("goal", "adopt", _draft(root, "goal", GOAL)))
    _ok(coach("program", "adopt", _draft(root, "program", toml(_program()).decode())))
    _history(root)
    clock.moment = at(PLAN_WEEK - datetime.timedelta(days=1))
    drafted = _ok(coach("plan", "draft", "--week", PLAN_WEEK.isoformat()))["result"]
    plan = root / str(drafted["path"])
    plan.write_text(plan.read_text().replace("confirmed = false", "confirmed = true"))
    checked = _ok(coach("plan", "apply", str(plan), "--dry-run"))["result"]
    _ok(coach("plan", "apply", str(plan), "--expect", str(checked["write_plan_hash"])))
    clock.moment = at(TODAY) - datetime.timedelta(hours=6)
    _ok(coach("import"))
    clock.moment = at(TODAY)
    _ok(coach("record", _draft(root, "record", _ledger())))
    _ok(coach("record", _draft(root, "resolve", _resolutions())))
    _ok(coach("checkin", "record", _draft(root, "checkin", _first_check_in())))
    _ok(coach("checkin", "record", _draft(root, "checkin-2", _second_check_in())))
    _ok(coach("publish"))


def a_fixture_instance(target: Path) -> Path:
    """A copy of the committed Fixture instance at `target`."""
    shutil.copytree(FIXTURE, target)
    return target


def hevy_holding(root: Path, clock: Clock, *, more_folders: Sequence[str] = ()) -> FakeHevy:
    """A FakeHevy holding the routines and folders the instance's mirror says Hevy holds, and a
    folder for each title in `more_folders`."""
    export = root / "export"
    routines = [json.loads(str(row["raw"])) for row in _rows(export / "routine.jsonl")]
    mirrored = [
        (int(str(row["hevy_id"])), str(row["title"])) for row in _rows(export / "folder.jsonl")
    ]
    more = [(8000 + n, title) for n, title in enumerate(more_folders)]
    folders = [
        {
            "id": id_,
            "index": n,
            "title": title,
            "updated_at": "2026-10-25T12:00:00+00:00",
            "created_at": "2026-10-25T12:00:00+00:00",
        }
        for n, (id_, title) in enumerate([*mirrored, *more])
    ]
    return FakeHevy(clock, routines=routines, folders=folders)


def tree(root: Path) -> dict[str, bytes]:
    """Every file under `root` by its path relative to it."""
    files = sorted(p for p in root.rglob("*") if p.is_file())
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in files}


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def copy_tracked(root: Path, target: Path) -> None:
    """The instance as its git repository holds it: everything but git's own and ignored files."""
    shutil.copytree(root, target, ignore=lambda d, names: [n for n in names if n in UNTRACKED])


GOAL = """kind = "hypertrophy"
because = "first goal at onboarding"
priority_lifts = ["bb_bench_press", "bb_back_squat"]
why = "Bigger and stronger across the board."

[[milestones]]
exercise = "bb_bench_press"
target = { kind = "load_x_reps", load = 185, reps = 5 }

[phase]
open = { kind = "maintenance", until = { kind = "coachs_call" }, because = "recomp" }
"""


# More than the ten rows a default list keeps, of every record kind and reading.
OVERFLOW = 11
# How many niggles, follow-ups and Observations stay open of the OVERFLOW written.
OPEN = 2
FIRST_CHECK_IN = datetime.date(2026, 10, 16)
SECOND_CHECK_IN = datetime.date(2026, 10, 23)
_NIGGLE_CAP = {"kind": "rpe_cap", "pattern": "hinge", "value": 9}


def _ledger() -> str:
    days = [TODAY - datetime.timedelta(days=d) for d in range(OVERFLOW)]
    tables: dict[str, list[dict[str, Any]]] = {
        "niggle": [
            {
                "site": f"site {n}",
                "date": day - datetime.timedelta(weeks=8),
                "status": "resolved" if n >= OPEN else "easing",
                "constraints": [] if n >= OPEN else [_NIGGLE_CAP],
            }
            for n, day in enumerate(days)
        ],
        "followup": [
            {"raised": day, "text": f"follow-up {n}", "due": TODAY + datetime.timedelta(weeks=2)}
            for n, day in enumerate(days)
        ],
        "decision": [
            {
                "kind": "safety_ceiling",
                "exercise": exercise,
                "load": 2 * load + 100,
                "because": "coach_judgement",
                "text": "well above any working load",
            }
            for exercise, load, _ in _lifts()[:OVERFLOW]
        ],
        "annotation": [
            {
                "kind": "discount",
                "target": f"workout:{_workout_id(week, 0)}/bb_back_squat",
                "params": {"sets": [2]},
                "because": "fatigue",
                "text": "the last set ground out",
            }
            for week in range(OVERFLOW)
        ],
        "note": [
            {"date": PLAN_WEEK + datetime.timedelta(days=n % 5), "text": f"athlete note {n}"}
            for n in range(OVERFLOW)
        ],
        "workout": [
            {
                "date": day - datetime.timedelta(weeks=2),
                "title": "PT session",
                "minutes": 60,
                "session_rpe": 7,
            }
            for day in days
        ],
        "weigh_in": [{"date": day, "kg": 80 + n / 10} for n, day in enumerate(days)],
        "sleep_night": [{"night": day, "hours": 7 + n / 10} for n, day in enumerate(days)],
        "activity": [
            {
                "date": TODAY - datetime.timedelta(weeks=n, days=2),
                "kind": "run",
                "minutes": 30,
                "rpe": 6,
                "quality": False,
            }
            for n in range(OVERFLOW)
        ],
        "status_span": [
            {
                "kind": "travel",
                "from_date": ADOPTED + datetime.timedelta(weeks=2 * n + 1, days=5),
                "to_date": ADOPTED + datetime.timedelta(weeks=2 * n + 1, days=6),
            }
            for n in range(OVERFLOW)
        ],
    }
    return dumps(tables)


def _resolutions() -> str:
    """Most follow-ups closed, so the live list stays an athlete's, not the overflow."""
    return dumps(
        {
            "followup": [
                {"followup": f"f-{n:04d}", "kind": "resolved", "date": TODAY}
                for n in range(OPEN + 1, OVERFLOW + 1)
            ]
        }
    )


def _first_check_in() -> str:
    return dumps(
        {
            "date": FIRST_CHECK_IN,
            "tier": "deep",
            "read": "A steady year; the stalled lines want a change of scheme.",
            "window_start": FIRST_CHECK_IN - datetime.timedelta(days=6),
            "observation": [{"text": f"observation {n}"} for n in range(OVERFLOW)],
        }
    )


def _second_check_in() -> str:
    return dumps(
        {
            "date": SECOND_CHECK_IN,
            "tier": "light",
            "read": "A quiet week.",
            "observation": [
                {"retire": f"o-{n:04d}", "because": "no longer true"}
                for n in range(OPEN + 1, OVERFLOW + 1)
            ],
        }
    )


def _lifts() -> list[tuple[str, float, float]]:
    return [lift for _, _, lines in WEEKLY for lift in lines]


def _program() -> dict[str, Any]:
    sessions: list[dict[str, Any]] = [
        _session(id_, [_line(e, load) for e, load, _ in lines]) for id_, _, lines in WEEKLY
    ]
    sessions += [
        _session(id_, [_line(exercise, load)], cadence="standing", tier="optional")
        for id_, exercise, load in STANDING
    ]
    return {
        "name": "Seven days and four standing sessions",
        "kind": "redesign",
        "because": "first program",
        "emphasis": "hypertrophy",
        "location": "gym",
        "schedule": {"rotation": ["A"], "A": {day: id_ for id_, day, _ in WEEKLY}},
        "session": sessions,
    }


def _session(id_: str, lines: list[dict[str, Any]], **fields: Any) -> dict[str, Any]:
    return {"id": id_, "title": id_.title(), "kind": "lifting", "tier": "core", **fields} | {
        "line": lines
    }


def _line(exercise: str, start_load: float) -> dict[str, Any]:
    return {
        "exercise": exercise,
        "sets": [{"count": 3, "reps": [8, 10], "rpe": 8}],
        "rest_s": 120,
        "scheme": {"name": "double_progression"},
        "start_load": start_load,
    }


def _template(exercise: str) -> str:
    return f"FX-{exercise.upper()}"


def _library(root: Path) -> None:
    used = [e for _, _, lines in WEEKLY for e, _, _ in lines] + [e for _, e, _ in STANDING]
    with closing(open_store(root / ".coach" / "coach.db")) as conn, conn:
        for exercise in used:
            exercises.update(conn, exercise, {"hevy_template_id": _template(exercise)})


def _history(root: Path) -> None:
    with closing(open_store(root / ".coach" / "coach.db")) as conn, conn:
        for week in range(WEEKS):
            monday = ADOPTED + datetime.timedelta(weeks=week)
            for n, (session, _, lines) in enumerate(WEEKLY):
                day = monday + datetime.timedelta(days=n)
                if day >= PLAN_WEEK:
                    continue
                sets = [
                    workouts.SetRow(
                        position=SETS * i + s,
                        hevy_template_id=_template(exercise),
                        hevy_title=None,
                        set_type="working",
                        weight_kg=round((load + step * week) * KG_PER_LB, 3),
                        reps=10 if s == 0 else 8,
                        rpe=8.0,
                    )
                    for i, (exercise, load, step) in enumerate(lines)
                    for s in range(SETS)
                ]
                workout_id = _workout_id(week, n)
                workouts.insert(
                    conn,
                    workouts.WorkoutRow(
                        id=workout_id,
                        updated_at=f"{day.isoformat()}T18:00:00+00:00",
                        source="hevy",
                        date=day.isoformat(),
                        title=session.title(),
                        routine_id=None,
                        session_id=session,
                        minutes=60,
                        session_rpe=None,
                        notes=None,
                        raw="{}",
                        check_in=None,
                        draft_hash=None,
                        recorded_at=f"{day.isoformat()}T19:00:00+00:00",
                    ),
                    sets,
                )


def _workout_id(week: int, n: int) -> str:
    return f"00000000-0000-4000-8000-{week:04d}{n:08d}"


def _athlete_files(root: Path) -> None:
    (root / "kit").mkdir(exist_ok=True)
    shutil.copyfile(INVENTORY, root / "kit" / "home.json")
    shutil.copyfile(TABLES, root / "kit" / "home.achievable.json")
    with (root / "coach.toml").open("a", encoding="utf-8") as config:
        config.write("\n" + dumps({"location": {"gym": GYM, "home": HOME}}))
    (root / "profile.md").write_text(PROFILE, encoding="utf-8")


PROFILE = """# Athlete

Synthetic athlete for the engine's fixture instance. Trains seven days a week at a gym.
"""


def _draft(root: Path, kind: str, text: str) -> str:
    path = root / ".coach" / "drafts" / f"{kind}.toml"
    path.write_text(text, encoding="utf-8")
    return str(path.relative_to(root))


def _coach(clock: FixedClock, hevy: FakeHevy) -> Callable[..., Run]:
    def serving(key: str, audit_path: Path, _: Clock) -> FakeHevy:
        return hevy

    def coach(*argv: str) -> Run:
        return run_coach(*argv, env=KEY, clock=clock, make_client=serving)

    return coach


def _ok(run: Run) -> Mapping[str, Any]:
    if run.code != 0:
        raise AssertionError(f"{run.stdout}\n{run.stderr}")
    return run.envelope


@contextmanager
def _isolated(home: Path) -> Generator[None]:
    saved = dict(os.environ)
    os.environ.update(
        GIT_CONFIG_GLOBAL=str(home / "no-global-gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Athlete",
        GIT_AUTHOR_EMAIL="athlete@example.com",
        GIT_COMMITTER_NAME="Athlete",
        GIT_COMMITTER_EMAIL="athlete@example.com",
    )
    version = app.engine_version
    app.engine_version = lambda: PIN
    cwd = Path.cwd()
    try:
        yield
    finally:
        os.chdir(cwd)
        app.engine_version = version
        os.environ.clear()
        os.environ.update(saved)


def regenerate(scratch: Path, target: Path) -> None:
    root = scratch / "athlete"
    root.mkdir(parents=True)
    with _isolated(scratch):
        os.chdir(root)
        generate(root)
    if target.exists():
        shutil.rmtree(target)
    copy_tracked(root, target)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        regenerate(Path(scratch), Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURE)
