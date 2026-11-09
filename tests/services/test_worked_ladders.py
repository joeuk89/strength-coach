"""The worked ladders of docs/spec/program.md: copies of each Draft, adopted as a version."""

import datetime

import pytest
from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.program_drafts import BALANCE_HOLDS_DRAFT, PULL_UP_NEGATIVES_DRAFT
from support.programs import a_config, the_worked_store

from coach.services.program import AdoptResult, adopt, show, show_draft
from coach.store.connection import Connection

BALANCE_CUES = "both feet, still, near a wall · soft knees · eyes on a point ahead"


def adopted(conn: Connection, draft: str, *, hevy: bool, dry_run: bool = False) -> AdoptResult:
    return adopt(
        conn,
        draft.encode(),
        file="draft.toml",
        config=a_config(hevy=hevy),
        kits=(kit_files(),),
        clock=FixedClock(),
        dry_run=dry_run,
    )


@pytest.mark.parametrize("hevy", [False, True], ids=["hevy off", "hevy on"])
def test_the_balance_holds_ladder_climbs_one_exercise_by_hold_length(hevy: bool) -> None:
    conn = the_worked_store()

    result = adopted(conn, BALANCE_HOLDS_DRAFT, hevy=hevy)

    assert result.version_id == "pv-1"
    [ladder] = show(conn, units="lb", zone=datetime.UTC).ladders
    assert {rung.exercise for rung in ladder.rungs} == {"custom_balance_board_hold"}
    assert [rung.label for rung in ladder.rungs] == [
        f"rung 1 · 2×30 s @5 · {BALANCE_CUES}",
        f"rung 2 · 2×40 s @5 · {BALANCE_CUES}",
        f"rung 3 · 2×50 s @6 · {BALANCE_CUES}",
        f"rung 4 · 2×60 s @6 · {BALANCE_CUES}",
    ]
    assert ladder.rungs[2].criterion == {"duration_s": 50, "rpe_at_most": 6, "exposures": 3}


@pytest.mark.parametrize("hevy", [False, True], ids=["hevy off", "hevy on"])
def test_the_pull_up_negatives_ladder_tops_out_on_a_weighted_rung(hevy: bool) -> None:
    conn = the_worked_store()

    result = adopted(conn, PULL_UP_NEGATIVES_DRAFT, hevy=hevy)

    assert result.version_id == "pv-1"
    [ladder] = show(conn, units="lb", zone=datetime.UTC).ladders
    assert [rung.exercise for rung in ladder.rungs] == [
        "negative_pull_up",
        "negative_pull_up",
        "negative_pull_up",
        "custom_weighted_negative_pull_up",
    ]
    assert [rung.label for rung in ladder.rungs] == [
        "rung 1 · 3×5 @8 · jump or step to the top · lower for 4 s · dead hang at the bottom",
        "rung 2 · 3×5 @8 · jump or step to the top · lower for 6 s · dead hang at the bottom",
        "rung 3 · 3×5 @8 · jump or step to the top · lower for 8 s · dead hang at the bottom",
        "rung 4 · Weighted negative pull-up · 3×5 @8 · 10 lb · "
        "dumbbell between the feet · lower for 8 s · dead hang at the bottom",
    ]


def test_the_pull_up_negatives_dry_run_lists_the_weighted_rungs_start_load() -> None:
    result = adopted(the_worked_store(), PULL_UP_NEGATIVES_DRAFT, hevy=False, dry_run=True)

    assert [(load["rung"], load["start_load"]) for load in result.start_loads] == [(4, 10)]


@pytest.mark.parametrize(
    "draft", [BALANCE_HOLDS_DRAFT, PULL_UP_NEGATIVES_DRAFT], ids=["balance", "negatives"]
)
def test_a_worked_ladder_re_adopts_unchanged_from_its_own_draft(draft: str) -> None:
    conn = the_worked_store()
    adopted(conn, draft, hevy=False)

    again = adopted(conn, show_draft(conn).text, hevy=False, dry_run=True)

    assert again.diff.empty
