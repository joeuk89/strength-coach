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
        next_rungs={},
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
        next_rungs={},
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
        next_rungs={},
    )

    assert [s.location for s in found.sessions] == ["home", "travel"]
