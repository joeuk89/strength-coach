import json
from typing import Any, cast

import pytest

from coach.core.exposure import LibraryEntry
from coach.core.mirror import Routine, RoutineExercise, RoutineSet
from coach.core.program.form import Advance, ExerciseLadder, Line, Rung, SchemeRef, SetGroup
from coach.core.routine_projection import (
    FrozenLine,
    RoutineChange,
    SessionRoutine,
    authored_exercise,
    drift_class,
    project_routine,
    retired_routine,
    routine_diff,
)

SQUAT = Line(
    "bb_back_squat",
    (SetGroup(4, reps=(6, 8), rpe=8),),
    rest_s=180,
    scheme=SchemeRef("double_progression"),
    cues="brace before you unrack",
)
CURL = Line("db_curl", (SetGroup(3, reps=12),), rest_s=60, scheme=SchemeRef("hold"), superset="a")
SQUAT_GROUPS = [
    {"type": "warm_up", "count": 1, "load": 45.0, "load_kg": 20.411657, "reps": 5},
    {"type": "working", "count": 2, "load": 125.0, "load_kg": 56.699046, "range": [6, 8], "rpe": 8},
]
CURL_GROUPS = [{"type": "working", "count": 1, "reps": 12}]
TEMPLATES = {"bb_back_squat": "SQ-1", "db_curl": "CU-1", "db_hammer_curl": "HC-1"}
LIBRARY = {
    "SQ-1": LibraryEntry("bb_back_squat", "total"),
    "CU-1": LibraryEntry("db_curl", "per_hand_x2"),
    "HC-1": LibraryEntry("db_hammer_curl", "per_hand_x2"),
}


def a_session(*lines: FrozenLine) -> SessionRoutine:
    return SessionRoutine(
        title="Lower",
        folder_id="9000",
        week_line="Week of 2026-11-02, rotation week A",
        authored=(SQUAT, CURL),
        lines=lines,
    )


def projected(*lines: FrozenLine) -> dict[str, Any]:
    return cast(dict[str, Any], project_routine(a_session(*lines), TEMPLATES, "lb"))


def test_a_line_with_no_swap_was_authored_on_its_own_exercise() -> None:
    steps = [{"step": "cut", "from": "ab_wheel", "to": "dead_bug", "cause": "return short"}]

    assert authored_exercise("dead_bug", steps) == "dead_bug"
    assert authored_exercise("dead_bug", ()) == "dead_bug"


def test_a_swapped_line_was_authored_on_the_exercise_it_swapped_from() -> None:
    steps = [{"step": "swap", "from": "db_curl", "to": "db_hammer_curl", "cause": "swap_exercise"}]

    assert authored_exercise("db_hammer_curl", steps) == "db_curl"


def test_the_body_sends_the_hevy_kg_each_set_and_no_routine_level_note() -> None:
    body = projected(FrozenLine("bb_back_squat", SQUAT_GROUPS))

    assert body == {
        "title": "Lower",
        "folder_id": 9000,
        "exercises": [
            {
                "exercise_template_id": "SQ-1",
                "rest_seconds": 180,
                "notes": "Week of 2026-11-02, rotation week A\n"
                "Target: 2×6–8 at 125 lb @8\nCues: brace before you unrack",
                "sets": [
                    {"type": "warmup", "weight_kg": 20.411657, "reps": 5},
                    {"type": "normal", "weight_kg": 56.699046, "rep_range": {"start": 6, "end": 8}},
                    {"type": "normal", "weight_kg": 56.699046, "rep_range": {"start": 6, "end": 8}},
                ],
            }
        ],
    }


def test_lines_follow_the_authored_order_and_only_the_first_carries_the_week_line() -> None:
    body = projected(FrozenLine("db_curl", CURL_GROUPS), FrozenLine("bb_back_squat", SQUAT_GROUPS))

    first, second = body["exercises"]
    assert first["exercise_template_id"] == "SQ-1"
    assert second["notes"] == "Target: 1×12, choose the load"
    assert second["superset_id"] == 0
    assert "weight_kg" not in second["sets"][0]


def test_a_swapped_line_keeps_the_authored_lines_place_rest_and_cues() -> None:
    swap = [{"step": "swap", "from": "db_curl", "to": "db_hammer_curl", "cause": "swap_exercise"}]

    [exercise] = projected(FrozenLine("db_hammer_curl", CURL_GROUPS, swap))["exercises"]

    assert (exercise["exercise_template_id"], exercise["rest_seconds"]) == ("HC-1", 60)


REP_OUT_GROUPS = [
    {"type": "working", "count": 2, "load": 225.0, "load_kg": 102.058283, "reps": 5},
    {
        "type": "working",
        "count": 1,
        "load": 225.0,
        "load_kg": 102.058283,
        "reps": "5+",
        "rpe_cap": 9,
    },
]


def test_a_rep_out_sends_its_floor_as_reps_and_names_its_stop_rpe_in_the_note() -> None:
    [exercise] = projected(FrozenLine("bb_back_squat", REP_OUT_GROUPS))["exercises"]

    assert [s["reps"] for s in exercise["sets"]] == [5, 5, 5]
    assert "Target: 2×5 + 5+ (stop at RPE 9) at 225 lb" in exercise["notes"]


def test_a_line_with_no_working_load_asks_the_athlete_to_choose_it_once() -> None:
    groups = [
        {"type": "working", "count": 3, "reps": 8},
        {"type": "working", "count": 1, "reps": 6},
    ]

    [exercise] = projected(FrozenLine("db_curl", groups))["exercises"]

    assert (
        exercise["notes"]
        == "Week of 2026-11-02, rotation week A\nTarget: 3×8 + 1×6, choose the load"
    )


def as_routine(body: dict[str, Any], **changed: Any) -> Routine:
    """The routine Hevy returns for a body, as the parser reads it."""
    exercises = tuple(
        RoutineExercise(
            index=n,
            hevy_template_id=e["exercise_template_id"],
            title=None,
            rest_s=e.get("rest_seconds"),
            notes=e.get("notes"),
            superset_id=e.get("superset_id"),
            sets=tuple(
                RoutineSet(
                    index=m,
                    set_type=s["type"],
                    weight_kg=s.get("weight_kg"),
                    reps=s.get("reps"),
                    rep_range=(s["rep_range"]["start"], s["rep_range"]["end"])
                    if "rep_range" in s
                    else None,
                    duration_s=s.get("duration_seconds"),
                    distance_m=None,
                )
                for m, s in enumerate(e["sets"])
            ),
        )
        for n, e in enumerate(body["exercises"])
    )
    fields: dict[str, Any] = {
        "id": "r-1",
        "title": body["title"],
        "folder_id": str(body["folder_id"]),
        "updated_at": "2026-11-01T10:00:00Z",
        "notes": None,
        "exercises": exercises,
        "raw": json.dumps(body),
    }
    return Routine(**(fields | changed))


def test_a_faithful_read_back_has_no_diff_and_a_weight_within_a_gram_is_the_same() -> None:
    body = projected(FrozenLine("bb_back_squat", SQUAT_GROUPS))
    body["exercises"][0]["sets"][1]["weight_kg"] = 56.6995
    read_back = as_routine(projected(FrozenLine("bb_back_squat", SQUAT_GROUPS)))

    assert diff(body, read_back) == ()


def diff(body: dict[str, Any], routine: Routine) -> tuple[RoutineChange, ...]:
    return routine_diff(body, routine, LIBRARY, "lb")


def test_a_moved_weight_names_the_exercise_the_set_and_both_loads_in_athlete_units() -> None:
    body = projected(FrozenLine("bb_back_squat", SQUAT_GROUPS))
    heavier = json.loads(json.dumps(body))
    heavier["exercises"][0]["sets"][1]["weight_kg"] = 61.234991

    load = diff(body, as_routine(heavier))

    assert [c.to_json() for c in load] == [
        {"field": "load", "exercise_id": "bb_back_squat", "set": 2, "planned": 125, "found": 135}
    ]
    assert [c.text for c in load] == ["bb_back_squat set 2 load 125 → 135 lb"]
    assert drift_class(load) == "load"


def test_a_title_or_a_swapped_template_is_structural_and_names_both_exercises() -> None:
    body = projected(FrozenLine("bb_back_squat", SQUAT_GROUPS))
    swapped = json.loads(json.dumps(body))
    swapped["exercises"][0]["exercise_template_id"] = "OTHER"

    structural = diff(body, as_routine(swapped, title="Leg day"))

    assert [c.text for c in structural] == [
        "title Lower → Leg day",
        "bb_back_squat swapped for OTHER",
    ]
    assert structural[1].to_json() == {
        "field": "exercise",
        "exercise_id": "bb_back_squat",
        "set": None,
        "planned": "bb_back_squat",
        "found": "OTHER",
    }
    assert drift_class(structural) == "structural"


def test_a_per_hand_load_is_reported_per_hand() -> None:
    curl = [{"type": "working", "count": 1, "reps": 12, "load": 25.0, "load_kg": 22.679619}]
    body = projected(FrozenLine("db_curl", curl))
    heavier = json.loads(json.dumps(body))
    heavier["exercises"][0]["sets"][0]["weight_kg"] = 27.215542

    assert [c.text for c in diff(body, as_routine(heavier))] == ["db_curl set 1 load 25 → 30 lb"]


def test_an_exercise_removed_in_hevy_is_named() -> None:
    body = projected(FrozenLine("bb_back_squat", SQUAT_GROUPS), FrozenLine("db_curl", CURL_GROUPS))
    removed = json.loads(json.dumps(body))
    del removed["exercises"][1]

    found = diff(body, as_routine(removed))

    assert [c.to_json() for c in found] == [
        {
            "field": "removed",
            "exercise_id": "db_curl",
            "set": None,
            "planned": "db_curl",
            "found": None,
        }
    ]
    assert [c.text for c in found] == ["db_curl removed"]
    assert drift_class(found) == "structural"


def test_an_exercise_added_in_hevy_is_named_by_its_exercise_or_its_template() -> None:
    body = projected(FrozenLine("bb_back_squat", SQUAT_GROUPS))
    added = json.loads(json.dumps(body))
    added["exercises"] += [
        {**body["exercises"][0], "exercise_template_id": t} for t in ("HC-1", "X")
    ]

    found = diff(body, as_routine(added))

    assert [c.text for c in found] == ["db_hammer_curl added", "template X added"]


def test_a_retired_routine_keeps_its_exercises_under_the_unused_title_in_the_retired_folder() -> (
    None
):
    live = as_routine(projected(FrozenLine("bb_back_squat", SQUAT_GROUPS)), title="Upper")

    body = cast(dict[str, Any], retired_routine(live, "9002"))

    assert (body["title"], body["folder_id"]) == ("(unused) Upper", 9002)
    assert diff(body, as_routine(body)) == ()
    assert retired_routine(as_routine(body), "9002")["title"] == "(unused) Upper"


def test_a_faithful_read_back_of_a_rep_out_has_no_diff() -> None:
    body = projected(FrozenLine("bb_back_squat", REP_OUT_GROUPS))
    hevy_holds = json.loads(json.dumps(body))
    for one in hevy_holds["exercises"][0]["sets"]:
        one["reps"] = 5

    assert diff(body, as_routine(hevy_holds)) == ()


TEMPO_SETS = (SetGroup(3, reps=4, rpe=8),)
TEMPO_GROUPS = [{"type": "working", "count": 3, "reps": 4, "rpe": 8}]
TEMPO_LADDER = Line(
    "pull_up_negative",
    TEMPO_SETS,
    rest_s=120,
    scheme=SchemeRef(
        "exercise_ladder",
        {},
        ExerciseLadder(
            (
                Rung("pull_up_negative", TEMPO_SETS, "lower for 4 s"),
                Rung("pull_up_negative", TEMPO_SETS, "lower for 6 s"),
                Rung("weighted_negative", TEMPO_SETS, "lower for 6 s, loaded"),
            ),
            Advance(exposures=2),
        ),
    ),
)
LADDER_TEMPLATES = {"pull_up_negative": "PN-1", "weighted_negative": "WN-1"}


def the_ladder_note(frozen: FrozenLine) -> list[str]:
    session = SessionRoutine(
        title="Pull",
        folder_id="9000",
        week_line="Week of 2026-11-02, rotation week A",
        authored=(TEMPO_LADDER,),
        lines=(frozen,),
        names={"pull_up_negative": "Negative", "weighted_negative": "Weighted"},
    )
    body = cast(dict[str, Any], project_routine(session, LADDER_TEMPLATES, "lb"))
    return body["exercises"][0]["notes"].splitlines()[2:]


@pytest.mark.parametrize(
    ("rung", "cues", "following"),
    [
        (1, "lower for 4 s", "rung 2 · 3×4 @8 · lower for 6 s"),
        (2, "lower for 6 s", "rung 3 · Weighted · 3×4 @8 · lower for 6 s, loaded"),
    ],
)
def test_a_note_on_a_shared_exercise_reads_the_rung_the_row_froze(
    rung: int, cues: str, following: str
) -> None:
    frozen = FrozenLine("pull_up_negative", TEMPO_GROUPS, rung=rung)

    assert the_ladder_note(frozen) == [f"Cues: {cues}", f"Next: {following}"]


def test_a_note_on_the_top_rung_names_no_next_rung() -> None:
    frozen = FrozenLine("weighted_negative", TEMPO_GROUPS, rung=3)

    assert the_ladder_note(frozen) == ["Cues: lower for 6 s, loaded"]


def test_a_swapped_rung_keeps_the_cues_of_the_rung_the_row_froze() -> None:
    swap = [{"step": "swap", "from": "pull_up_negative", "to": "x", "cause": "swap_exercise"}]
    frozen = FrozenLine("weighted_negative", TEMPO_GROUPS, swap, rung=1)

    assert the_ladder_note(frozen) == [
        "Cues: lower for 4 s",
        "Next: rung 2 · 3×4 @8 · lower for 6 s",
    ]


def test_a_stepped_back_rung_names_only_its_index_and_no_next_rung() -> None:
    step = [{"step": "cut", "from": "rung 3", "to": "rung 1", "cause": "return 43+, 52 days off"}]
    frozen = FrozenLine("pull_up_negative", TEMPO_GROUPS, step, rung=1)

    assert the_ladder_note(frozen) == [
        "Cues: lower for 4 s",
        "This week: rung 1",
    ]


def test_a_stepped_back_rung_reads_the_rung_the_step_stored_not_its_wording() -> None:
    step = [
        {
            "step": "cut",
            "from": "the third rung",
            "to": "the first rung",
            "cause": "return 43+, 52 days off",
            "rung": 1,
        }
    ]
    frozen = FrozenLine("pull_up_negative", TEMPO_GROUPS, step, rung=1)

    assert the_ladder_note(frozen) == ["Cues: lower for 4 s", "This week: rung 1"]


def test_a_step_back_frozen_naming_exercises_keeps_the_note_it_pushed() -> None:
    step = [
        {
            "step": "cut",
            "from": "pull_up_negative",
            "to": "pull_up_negative",
            "cause": "return 43+, 52 days off",
        }
    ]
    frozen = FrozenLine("pull_up_negative", TEMPO_GROUPS, step, rung=1)

    assert the_ladder_note(frozen) == [
        "Cues: lower for 4 s",
        "Next: rung 2 · 3×4 @8 · lower for 6 s",
    ]


def test_a_row_frozen_before_rungs_were_recorded_finds_its_rung_by_exercise() -> None:
    frozen = FrozenLine("weighted_negative", TEMPO_GROUPS)

    assert the_ladder_note(frozen) == ["Cues: lower for 6 s, loaded"]


def test_the_balance_ladder_note_names_the_next_rungs_exercise() -> None:
    stand = (SetGroup(2, duration_s=45, rpe=6),)
    tilts = (SetGroup(2, duration_s=60, rpe=6),)
    board = Line(
        "board_stand",
        (),
        60,
        SchemeRef(
            "exercise_ladder",
            {},
            ExerciseLadder(
                (Rung("board_stand", stand, "feet apart"), Rung("board_tilts", tilts, "slowly"))
            ),
        ),
    )
    session = SessionRoutine(
        title="Balance",
        folder_id="9000",
        week_line="Week of 2026-11-02, rotation week A",
        authored=(board,),
        lines=(
            FrozenLine(
                "board_stand", [{"type": "working", "count": 2, "duration_s": 45, "rpe": 6}], rung=1
            ),
        ),
        names={"board_stand": "Balance board: stand", "board_tilts": "Balance board: tilts"},
    )

    body = cast(dict[str, Any], project_routine(session, {"board_stand": "B-1"}, "lb"))

    assert body["exercises"][0]["notes"].splitlines()[-1] == (
        "Next: rung 2 · Balance board: tilts · 2×60 s @6 · slowly"
    )
