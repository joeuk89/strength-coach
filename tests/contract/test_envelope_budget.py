import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from support.cli import Run, run_coach
from support.clock import FixedClock, at
from support.fixture_instance import (
    GOAL,
    KEY,
    PIN,
    TODAY,
    a_fixture_instance,
    hevy_holding,
)
from support.fixture_instances import serving

from coach.cli import app
from coach.cli.declaration import Declaration
from coach.cli.envelope import BUDGET_BYTES
from coach.cli.registry import declarations
from coach.core.registries.agent import RECORD_KINDS, VIEWS
from coach.services.query import READING_KINDS

CLOCK = FixedClock(at(TODAY))
NEXT_WEEK = "2026-11-02"
CHECK_IN = f'date = {TODAY}\ntier = "light"\nread = "a steady week"\n'
RECORD = f"[[weigh_in]]\ndate = {TODAY}\nkg = 81.2\n"

type Coach = Callable[..., Run]


def coach_in(root: Path) -> Coach:
    def coach(*argv: str) -> Run:
        hevy = hevy_holding(root, CLOCK)
        return run_coach(*argv, env=KEY, clock=CLOCK, make_client=serving(hevy))

    return coach


def example_drafts(root: Path, coach: Coach) -> None:
    """The Drafts the declared examples name, made the way the agent would make them."""
    drafts = root / ".coach" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    plan = coach("plan", "draft", "--week", NEXT_WEEK, "--out", "next-plan.toml").envelope
    text = (
        (root / plan["result"]["path"]).read_text().replace("confirmed = false", "confirmed = true")
    )
    (drafts / "2026-11-01-plan.toml").write_text(text)
    program = coach("program", "show", "--draft", "--out", "program.toml").envelope
    shutil.copyfile(root / program["result"]["path"], drafts / "2026-10-30-program.toml")
    (drafts / "2026-10-30-goal.toml").write_text(GOAL)
    (drafts / "2026-11-01-checkin.toml").write_text(CHECK_IN)
    (drafts / "2026-10-30-record.toml").write_text(RECORD)


PLAN = ".coach/drafts/2026-11-01-plan.toml"
# Stands for the Write plan hash of the dry run, which is only known once it has run.
APPROVED = "<the dry run's hash>"
PUSH = ("plan", "apply", PLAN, "--expect", APPROVED)


def calls() -> list[tuple[str, ...]]:
    """Every declared example at its default size, every view and every list kind, and the
    approved push of next week's plan."""
    examples = [
        tuple(word for word in example.argv if word != "--full")
        for declaration in declarations()
        for example in declaration.examples
    ]
    lists = [
        *(("query", view) for view in VIEWS.names() if view != "ledger"),
        *(("query", "ledger", "--kind", kind) for kind in RECORD_KINDS.names()),
        *(("query", "readings", "--kind", kind) for kind in READING_KINDS),
    ]
    return list(dict.fromkeys([*examples, *lists, PUSH]))


@pytest.fixture(scope="module")
def envelopes(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, ...], Run]:
    """Each call's run on the fixture instance, its store rebuilt once; a call that writes runs
    on its own copy."""
    built = a_fixture_instance(tmp_path_factory.mktemp("budget") / "built")
    found: dict[tuple[str, ...], Run] = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(app, "engine_version", lambda: PIN)
        patch.chdir(built)
        coach = coach_in(built)
        example_drafts(built, coach)
        dry_run = coach("plan", "apply", PLAN, "--dry-run")
        digest = str(dry_run.envelope["result"]["write_plan_hash"])
        for n, argv in enumerate(calls()):
            root = built
            if declared(argv).writes != "none":
                root = tmp_path_factory.mktemp("call") / str(n)
                shutil.copytree(built, root)
            patch.chdir(root)
            found[argv] = coach_in(root)(*(digest if w == APPROVED else w for w in argv))
    return found


def declared(argv: tuple[str, ...]) -> Declaration:
    return max(
        (d for d in declarations() if list(argv[: len(d.name.split())]) == d.name.split()),
        key=lambda d: len(d.name.split()),
    )


# Envelopes the spec does not yet let fit 3 KB, each with the conflict that holds it over. Remove
# one when its verb fits, or the last test here fails.
OVER_BUDGET: dict[tuple[str, ...], str] = {
    ("checkin", "open"): "the card's sessions, dose and notes lists carry no list rule",
    ("checkin", "open", "--date", "2026-11-01", "--tier", "deep"): "as checkin open",
    ("plan", "apply", PLAN, "--dry-run"): "ADR 0006's 40-line prompt alone is about 3 KB",
    ("program", "adopt", ".coach/drafts/2026-10-30-program.toml", "--dry-run"): (
        "envelope warnings[] carry no list rule"
    ),
}


def every_call() -> list[Any]:
    return [pytest.param(argv, id=" ".join(argv)) for argv in calls()]


@pytest.mark.parametrize("argv", [a for a in every_call() if a.values[0] not in OVER_BUDGET])
def test_every_default_envelope_on_the_fixture_instance_is_under_3_kb(
    envelopes: dict[tuple[str, ...], Run], argv: tuple[str, ...]
) -> None:
    run = envelopes[argv]

    assert len(run.stdout.encode("utf-8")) <= BUDGET_BYTES


@pytest.mark.parametrize("argv", list(OVER_BUDGET), ids=" ".join)
def test_an_envelope_listed_over_budget_is_still_over_it(
    envelopes: dict[tuple[str, ...], Run], argv: tuple[str, ...]
) -> None:
    assert len(envelopes[argv].stdout.encode("utf-8")) > BUDGET_BYTES


@pytest.mark.parametrize("argv", every_call())
def test_no_declared_field_is_dropped(
    envelopes: dict[tuple[str, ...], Run], argv: tuple[str, ...]
) -> None:
    run = envelopes[argv]
    if not run.envelope["ok"]:
        return

    required = cast(list[str], declared(argv).output.get("required", []))
    assert set(required) <= set(run.envelope["result"])


def truncation_keys(schema: object) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    properties = cast(dict[str, object], cast(dict[str, object], schema).get("properties", {}))
    found = {key for key in properties if key == "truncated" or key.endswith("_truncated")}
    return found | {k for child in properties.values() for k in truncation_keys(child)}


@pytest.mark.parametrize(
    "declaration",
    [d for d in declarations() if truncation_keys(d.output)],
    ids=lambda d: d.name,
)
def test_every_list_a_summary_truncates_is_truncated_at_least_once(
    envelopes: dict[tuple[str, ...], Run], declaration: Declaration
) -> None:
    seen: set[str] = set()
    for argv, run in envelopes.items():
        if run.envelope["ok"] and declared(argv) is declaration:
            seen |= {key for key, value in run.envelope["result"].items() if value is True}

    assert truncation_keys(declaration.output) <= seen
