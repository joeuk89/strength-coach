import datetime

import pytest
from support.goals import STRENGTH, WORKED, WORKED_WHY, opening, with_phase

from coach.core.errors import Invalid
from coach.core.goal import (
    Goal,
    GoalDraft,
    Milestone,
    PhaseClose,
    PhaseOpen,
    Target,
    Until,
    goal_diff,
    parse_goal_draft,
)

GOAL_ONLY = STRENGTH


def parse(text: str) -> GoalDraft:
    return parse_goal_draft(text.encode("utf-8"), file="g.toml")


def refused(text: str) -> Invalid:
    with pytest.raises(Invalid) as raised:
        parse(text)
    return raised.value


def test_the_worked_draft_parses_to_a_goal_three_milestones_and_an_open_phase() -> None:
    draft = parse(WORKED)

    assert draft.goal == Goal(
        kind="hypertrophy",
        because="first goal at onboarding",
        priority_lifts=("bb_bench_press", "pull_up"),
        why=WORKED_WHY,
        milestones=(
            Milestone("bb_deadlift", Target("bodyweight_multiple", value=2.0)),
            Milestone("bb_bench_press", Target("bodyweight_multiple", value=1.25)),
            Milestone("pull_up", Target("load_x_reps", load=0.0, reps=5)),
        ),
    )
    assert draft.open == PhaseOpen(
        kind="maintenance",
        rate_pct_bw_per_week=0.0,
        until=Until("coachs_call"),
        because="recomp at maintenance since 11 Oct 2026",
    )
    assert draft.close is None
    assert draft.hash.startswith("sha256:")


def test_a_priority_lift_named_twice_is_priority_lift_duplicate() -> None:
    error = refused(GOAL_ONLY.replace('["bb_bench_press"]', '["bb_bench_press", "bb_bench_press"]'))

    assert error.code == "priority_lift_duplicate"
    assert "bb_bench_press" in error.message


def test_a_milestone_with_no_target_is_milestone_target_missing() -> None:
    error = refused(GOAL_ONLY + '\n[[milestones]]\nexercise = "bb_deadlift"\n')

    assert error.code == "milestone_target_missing"
    assert "bb_deadlift" in error.message


@pytest.mark.parametrize(
    "target",
    [
        '{ kind = "e1rm" }',
        '{ kind = "load_x_reps", load = 100 }',
        '{ kind = "e1rm", value = 0 }',
        '{ kind = "max", value = 100 }',
    ],
)
def test_a_target_off_its_kinds_shape_is_invalid_argument(target: str) -> None:
    error = refused(GOAL_ONLY + f'\n[[milestones]]\nexercise = "bb_deadlift"\ntarget = {target}\n')

    assert error.code == "invalid_argument"


def test_a_target_carrying_a_key_of_the_other_shape_is_unknown_key() -> None:
    error = refused(
        GOAL_ONLY
        + '\n[[milestones]]\nexercise = "bb_deadlift"\n'
        + 'target = { kind = "e1rm", value = 200, reps = 1 }\n'
    )

    assert error.code == "unknown_key"


def test_an_e1rm_milestone_keeps_its_value() -> None:
    draft = parse(
        GOAL_ONLY
        + '\n[[milestones]]\nexercise = "bb_squat"\ntarget = { kind = "e1rm", value = 140 }\n'
    )

    assert draft.goal.milestones == (Milestone("bb_squat", Target("e1rm", value=140.0)),)


def test_a_goal_with_no_priority_lifts_and_no_phase_parses() -> None:
    draft = parse('kind = "hypertrophy"\nbecause = "b"\nwhy = "w"\n')

    assert draft.goal.priority_lifts == ()
    assert (draft.open, draft.close) == (None, None)


def test_an_unknown_goal_kind_is_invalid_argument() -> None:
    assert refused(GOAL_ONLY.replace('"strength"', '"maintenance"')).code == "invalid_argument"


def test_an_unknown_top_level_key_is_unknown_key() -> None:
    assert refused(GOAL_ONLY + 'emphasis = "strength"\n').code == "unknown_key"


@pytest.mark.parametrize(
    ("kind", "rate"), [("deficit", -0.5), ("maintenance", 0.0), ("surplus", 0.25)]
)
def test_an_omitted_rate_is_the_phase_kinds_default(kind: str, rate: float) -> None:
    draft = parse(with_phase(GOAL_ONLY, opening(kind)))

    assert draft.open is not None
    assert draft.open.rate_pct_bw_per_week == rate


def test_a_stated_rate_stands() -> None:
    draft = parse(
        GOAL_ONLY
        + '\n[phase]\nopen = { kind = "deficit", rate_pct_bw_per_week = -0.75, '
        + 'until = { kind = "bodyweight_at_or_below", value = 80 }, because = "cut" }\n'
    )

    assert draft.open == PhaseOpen("deficit", -0.75, Until("bodyweight_at_or_below", 80.0), "cut")


def test_a_date_until_reads_a_date() -> None:
    draft = parse(
        GOAL_ONLY
        + '\n[phase]\nopen = { kind = "surplus", until = { kind = "date", value = 2027-03-01 }, '
        + 'because = "bulk" }\n'
    )

    assert draft.open is not None
    assert draft.open.until == Until("date", datetime.date(2027, 3, 1))


@pytest.mark.parametrize(
    "until",
    [
        '{ kind = "coachs_call", value = 80 }',
        '{ kind = "date" }',
        '{ kind = "bodyweight_at_or_above", value = "heavy" }',
        '{ kind = "waist" }',
    ],
)
def test_an_until_off_its_kinds_shape_is_invalid_argument(until: str) -> None:
    error = refused(
        GOAL_ONLY + f'\n[phase]\nopen = {{ kind = "surplus", until = {until}, because = "b" }}\n'
    )

    assert error.code == "invalid_argument"


def test_an_open_phase_with_no_until_is_invalid_argument() -> None:
    error = refused(GOAL_ONLY + '\n[phase]\nopen = { kind = "surplus", because = "b" }\n')

    assert error.code == "invalid_argument"


def test_a_phase_table_may_close_and_open() -> None:
    draft = parse(
        GOAL_ONLY
        + '\n[phase]\nclose = { because = "cut done" }\n'
        + 'open = { kind = "maintenance", until = { kind = "coachs_call" }, because = "hold" }\n'
    )

    assert draft.close == PhaseClose("cut done")
    assert draft.open == PhaseOpen("maintenance", 0.0, Until("coachs_call"), "hold")


def test_an_empty_phase_table_is_invalid_argument() -> None:
    assert refused(GOAL_ONLY + "\n[phase]\n").code == "invalid_argument"


def test_the_draft_names_every_exercise_it_cites() -> None:
    assert parse(WORKED).exercises() == (
        "bb_bench_press",
        "pull_up",
        "bb_deadlift",
        "bb_bench_press",
        "pull_up",
    )


def test_a_first_goal_has_no_diff() -> None:
    assert goal_diff(None, parse(WORKED).goal) is None


def test_the_diff_names_each_changed_field_and_nothing_else() -> None:
    previous = parse(WORKED).goal
    new = parse(
        STRENGTH + '\n[[milestones]]\nexercise = "bb_deadlift"\n'
        'target = { kind = "bodyweight_multiple", value = 2.0 }\n'
    ).goal

    assert goal_diff(previous, new) == {
        "kind": {"from": "hypertrophy", "to": "strength"},
        "priority_lifts": {"from": ["bb_bench_press", "pull_up"], "to": ["bb_bench_press"]},
        "milestones": {
            "added": [],
            "removed": [
                {
                    "exercise": "bb_bench_press",
                    "target": {"kind": "bodyweight_multiple", "value": 1.25},
                },
                {"exercise": "pull_up", "target": {"kind": "load_x_reps", "load": 0.0, "reps": 5}},
            ],
        },
        "why": True,
    }


def test_the_same_goal_restated_has_an_empty_diff() -> None:
    goal = parse(WORKED).goal

    assert goal_diff(goal, goal) == {}
