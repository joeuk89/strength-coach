import datetime
from collections.abc import Mapping, Sequence

from coach.core.flag import Scope, raise_flag
from coach.core.plan_summary import SummaryLine, frozen_summary
from coach.core.prescription import PlanOverride

MONDAY = datetime.date(2026, 11, 2)
SQUAT = [{"type": "normal", "count": 4, "load": 125.0, "load_kg": 56.7, "range": [6, 8]}]
OVERHEAD = [{"type": "normal", "count": 3, "load": 85.0, "load_kg": 38.56, "range": [6, 8]}]
WEEK_FLAG = raise_flag(
    "rotation_unconfirmed",
    Scope("week", MONDAY),
    {"inferred_position": "A", "source": "program_adopt"},
    "rotation week A is inferred",
)


def a_row(
    session_id: str, day: str, exercise_id: str, set_groups: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "date": day,
        "exercise_id": exercise_id,
        "rung": None,
        "set_groups": set_groups,
        "change": "4×6–8 @8: 120 → 125",
        "steps": [],
        "flags": [WEEK_FLAG.to_json()],
    }


ROWS = [
    a_row("lower", "2026-11-02", "bb_back_squat", SQUAT),
    a_row("upper", "2026-11-04", "bb_overhead_press", OVERHEAD),
]


def test_a_frozen_summary_shows_each_planned_session_with_its_frozen_lines() -> None:
    found = frozen_summary(
        week=MONDAY,
        position="B",
        supersedes="wp-2026-11-02",
        rows=ROWS,
        overrides=(),
        locations={"lower": "home", "upper": "gym"},
        rung_labels={},
    )

    assert [(s.session_id, s.date, s.location, s.lines) for s in found.sessions] == [
        (
            "lower",
            datetime.date(2026, 11, 2),
            "home",
            (SummaryLine("bb_back_squat", SQUAT, "4×6–8 @8: 120 → 125"),),
        ),
        (
            "upper",
            datetime.date(2026, 11, 4),
            "gym",
            (SummaryLine("bb_overhead_press", OVERHEAD, "4×6–8 @8: 120 → 125"),),
        ),
    ]
    assert (found.position.week, found.position.source, found.supersedes) == (
        "B",
        "plan_in_force",
        "wp-2026-11-02",
    )


def test_a_flag_frozen_on_every_line_shows_once() -> None:
    found = frozen_summary(
        week=MONDAY,
        position="B",
        supersedes=None,
        rows=ROWS,
        overrides=(),
        locations={"lower": "home", "upper": "home"},
        rung_labels={},
    )

    assert found.flags == (WEEK_FLAG,)


def test_a_relocated_session_shows_at_its_new_location() -> None:
    relocate = PlanOverride(
        "relocate_session",
        session_id="upper",
        params={"location": "travel"},
        because="schedule",
        text="Away midweek.",
    )

    found = frozen_summary(
        week=MONDAY,
        position="B",
        supersedes=None,
        rows=ROWS,
        overrides=(relocate,),
        locations={"lower": "home", "upper": "home"},
        rung_labels={},
    )

    assert [s.location for s in found.sessions] == ["home", "travel"]


def a_capped_pin(outcome: str, exercise_id: str = "bb_back_squat") -> dict[str, object]:
    return raise_flag(
        "pin_load_capped",
        Scope("line", MONDAY, session_id="lower", exercise_id=exercise_id),
        {
            "load": 135,
            "prescribed": 125,
            "ceiling_kind": "illness",
            "rpe_cap": 7,
            "ref": None,
            "outcome": outcome,
        },
        "m",
    ).to_json()


def test_a_frozen_line_carries_the_outcome_of_its_capped_pin() -> None:
    capped = {**ROWS[0], "flags": [WEEK_FLAG.to_json(), a_capped_pin("no_effect")]}

    found = frozen_summary(
        week=MONDAY,
        position="B",
        supersedes=None,
        rows=[capped, ROWS[1]],
        overrides=(),
        locations={"lower": "home", "upper": "home"},
        rung_labels={},
    )

    assert [line.pin_outcome for s in found.sessions for line in s.lines] == ["no_effect", None]


def test_a_capped_pin_on_another_line_is_not_this_lines_outcome() -> None:
    elsewhere = a_capped_pin("reduced", exercise_id="bb_bench_press")
    capped = {**ROWS[0], "flags": [elsewhere]}

    found = frozen_summary(
        week=MONDAY,
        position="B",
        supersedes=None,
        rows=[capped],
        overrides=(),
        locations={"lower": "home"},
        rung_labels={},
    )

    assert found.sessions[0].lines[0].pin_outcome is None


def a_step(step: str, cause: str) -> dict[str, object]:
    return {"step": step, "from": 8, "to": 7, "cause": cause}


def test_a_frozen_line_the_illness_cap_binds_carries_the_cap_and_its_end() -> None:
    dated = {**ROWS[0], "steps": [a_step("rpe_ceiling", "illness until 2026-11-04")]}
    trained = {
        **ROWS[1],
        "steps": [
            a_step("rpe_ceiling", "illness until this lift is trained once"),
            a_step("rpe_ceiling", "not_binding"),
        ],
    }

    found = frozen_summary(
        week=MONDAY,
        position="B",
        supersedes=None,
        rows=[dated, trained],
        overrides=(),
        locations={"lower": "home", "upper": "home"},
        rung_labels={},
    )

    assert [line.illness_cap for s in found.sessions for line in s.lines] == [
        "illness until 2026-11-04",
        "illness until this lift is trained once",
    ]


def test_a_line_capped_by_another_ceiling_carries_no_illness_cap() -> None:
    capped = {**ROWS[0], "steps": [a_step("rpe_ceiling", "light_week")]}

    found = frozen_summary(
        week=MONDAY,
        position="B",
        supersedes=None,
        rows=[capped],
        overrides=(),
        locations={"lower": "home"},
        rung_labels={},
    )

    assert found.sessions[0].lines[0].illness_cap is None
