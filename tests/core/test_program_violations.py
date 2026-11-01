import datetime
from typing import Any

import pytest
from support.program_drafts import a_draft, a_line, a_session, toml

from coach.core.exposure import Exposure, ExposureSet
from coach.core.flag import Flag
from coach.core.goal import Goal
from coach.core.program.checks import AdoptContext, violations
from coach.core.program.parse import parse_program_draft
from coach.core.rack import IncrementRack, ListedRack, RackRow

LIBRARY: dict[str, dict[str, object]] = {
    "bb_bench_press": {"load_mode": "total", "equipment_kind": "barbell"},
    "db_curl": {"load_mode": "per_hand_x2", "equipment_kind": "dumbbell"},
    "kb_swing": {"load_mode": "single_implement", "equipment_kind": "kettlebell"},
    "pull_up": {"load_mode": "bodyweight", "equipment_kind": "bodyweight"},
    "plank": {"load_mode": "duration", "equipment_kind": "bodyweight"},
    "assisted_pull_up": {"load_mode": "assisted", "equipment_kind": "machine"},
}
HOME = {
    "barbell": IncrementRack(2.5, base=20),
    "dumbbell": ListedRack(tuple(RackRow(load) for load in (10, 12.5, 15))),
}


def a_goal(priority_lifts: tuple[str, ...]) -> Goal:
    return Goal(kind="hypertrophy", because="first goal", priority_lifts=priority_lifts, why="")


def a_context(**fields: Any) -> AdoptContext:
    values: dict[str, Any] = {
        "version_id": "pv-1",
        "library": LIBRARY,
        "racks": {"home": HOME, "gym": {}},
        "goal": a_goal(("bb_bench_press",)),
    }
    values.update(fields)
    return AdoptContext(**values)


def an_exposure() -> Exposure:
    sets = (ExposureSet(0, "working", None, 5, 8),)
    return Exposure("w-0001", "bb_bench_press", datetime.date(2026, 10, 20), sets)


def flags_of(draft: dict[str, Any], context: AdoptContext | None = None) -> list[Flag]:
    parsed = parse_program_draft(toml(draft), file="d.toml")
    return list(violations(parsed.form, context or a_context(), parsed.unknown_keys))


def keyed(draft: dict[str, Any], context: AdoptContext | None = None) -> list[str]:
    return [flag.key for flag in flags_of(draft, context)]


def one_line(**fields: Any) -> dict[str, Any]:
    return a_draft(a_session("push", a_line(**fields)))


def test_a_valid_draft_raises_nothing() -> None:
    assert keyed(a_draft()) == []


VIOLATIONS = [
    (one_line(colour="red"), "unknown_key@version:pv-1"),
    (one_line(exercise="bb_floor_press"), "unknown_exercise@line:push/bb_floor_press"),
    (one_line(scheme={"name": "rpe_anchored"}), "unknown_scheme@line:push/bb_bench_press"),
    (one_line(load_mode="kettle"), "unknown_load_mode@line:push/bb_bench_press"),
    (a_draft(a_session("push"), a_session("push")), "duplicate_id@version:pv-1"),
    (
        a_draft(schedule={"rotation": ["A"], "A": {"mon": "push", "tue": "pull"}}),
        "schedule_session_missing@version:pv-1",
    ),
    (
        a_draft(a_session("push"), schedule={"rotation": ["A"], "A": {}}),
        "session_unscheduled@session:push",
    ),
    (
        a_draft(
            a_session("push", cadence="standing"),
            schedule={"rotation": ["A"], "A": {"mon": "push"}},
        ),
        "cadence_on_scheduled@session:push",
    ),
    (a_draft(location="cabin"), "location_unknown@version:pv-1"),
    (one_line(exercise="kb_swing", start_load=16), "equipment_unsupplied@line:push/kb_swing"),
    (a_draft(a_session("push", kind="rehab")), "rehab_in_version@session:push"),
    (
        a_draft(a_session("drill", kind="practice", tier="core", cadence="daily")),
        "practice_not_optional@session:drill",
    ),
    (
        a_draft(a_session("pt", kind="coach_led", estimated_sets={"chest": 4})),
        "coach_led_has_lines@session:pt",
    ),
    (one_line(start_load=None), "start_load_missing@line:push/bb_bench_press"),
    (one_line(start_load=61), "start_load_off_rack@line:push/bb_bench_press"),
    (
        one_line(sets=[{"count": 2, "type": "activation", "reps": 5}]),
        "no_working_sets@line:push/bb_bench_press",
    ),
    (
        one_line(sets=[{"count": 1, "type": "test", "reps": 1, "rpe": 9}]),
        "set_type_not_allowed@line:push/bb_bench_press",
    ),
    (
        one_line(
            sets=[{"count": 3, "reps": 5, "rpe": 8}],
            scheme={"name": "top_backoff", "pct_of_top": 85},
        ),
        "set_groups_off_scheme@line:push/bb_bench_press",
    ),
    (one_line(sets=[{"count": 3, "reps": [6, 8]}]), "rpe_missing@line:push/bb_bench_press"),
    (
        a_draft(
            acknowledge=[
                {"flag": "stall_streak@line:push/bb_bench_press", "because": "stall", "text": "x"}
            ]
        ),
        "acknowledgement_unmatched@version:pv-1",
    ),
]


@pytest.mark.parametrize(("draft", "key"), VIOLATIONS, ids=[k for _, k in VIOLATIONS])
def test_each_violation_fails_the_draft_with_exactly_its_code_and_scope(
    draft: dict[str, Any], key: str
) -> None:
    assert keyed(draft) == [key]


def test_hevy_template_missing_names_the_missing_columns_only_with_hevy_on() -> None:
    draft = a_draft(
        a_session("push", a_line("custom_ring_push_up", start_load=None)),
        exercise={
            "custom_ring_push_up": {
                "name": "Ring push-up",
                "load_mode": "bodyweight",
                "equipment_kind": "bodyweight",
                "pattern": "horizontal_push",
                "muscles": {"primary": ["chest"], "secondary": []},
                "hevy_title": "Ring Push Up",
            }
        },
    )

    assert keyed(draft) == []
    [flag] = flags_of(draft, a_context(hevy_on=True))
    assert flag.key == "hevy_template_missing@line:push/custom_ring_push_up"
    assert flag.params["missing_columns"] == [
        "hevy_exercise_type",
        "hevy_equipment",
        "hevy_muscle_group",
    ]


def test_goal_missing_and_priority_lifts_required_read_the_current_goal() -> None:
    assert keyed(a_draft(), a_context(goal=None)) == ["goal_missing@version:pv-1"]
    assert keyed(a_draft(emphasis="strength"), a_context(goal=a_goal(()))) == [
        "priority_lifts_required@version:pv-1"
    ]


def test_unknown_key_names_the_first_path_and_counts_a_start_load_on_a_bodyweight_line() -> None:
    [flag] = flags_of(one_line(exercise="pull_up", start_load=10))

    assert flag.code == "unknown_key"
    assert flag.params == {"key_path": "session.push.line.pull_up.start_load"}


def test_start_load_off_rack_names_the_two_nearest_rows() -> None:
    [flag] = flags_of(one_line(exercise="db_curl", start_load=11))

    assert flag.params == {"start_load": 11, "location": "home", "nearest_rows": [10, 12.5]}


def test_a_per_hand_start_load_on_the_rack_and_a_history_without_start_load_pass() -> None:
    assert keyed(one_line(exercise="db_curl", start_load=12.5)) == []
    exposed = a_context(last_exposures={"bb_bench_press": an_exposure()})
    assert keyed(one_line(start_load=None), exposed) == []


def test_an_assisted_line_needs_a_start_load_and_reads_no_rack() -> None:
    ladder = {"name": "assistance_ladder", "rungs": [40, 30, 20]}

    assert keyed(one_line(exercise="assisted_pull_up", scheme=ladder, start_load=40)) == []
    assert keyed(one_line(exercise="assisted_pull_up", scheme=ladder, start_load=None)) == [
        "start_load_missing@line:push/assisted_pull_up"
    ]


def test_an_unknown_scheme_param_and_a_missing_required_one_name_the_param() -> None:
    [extra] = flags_of(one_line(scheme={"name": "hold", "increment": 2.5}))
    [missing] = flags_of(
        one_line(
            sets=[{"count": 1, "reps": 5, "rpe": 8}, {"count": 3, "reps": 5}],
            scheme={"name": "top_backoff"},
        )
    )

    assert extra.params == {"scheme": "hold", "param": "increment"}
    assert missing.params == {"scheme": "top_backoff", "param": "pct_of_top"}


def test_top_backoff_requires_rpe_on_the_top_group_alone() -> None:
    sets = [{"count": 1, "reps": 5, "rpe": 8}, {"count": 3, "reps": 5}]

    assert keyed(one_line(sets=sets, scheme={"name": "top_backoff", "pct_of_top": 85})) == []


@pytest.mark.parametrize(
    ("sets", "scheme"),
    [
        (
            [{"count": 4, "reps": 8, "rpe": 8}, {"count": 1, "reps": 5, "rpe": 8}],
            {"name": "assistance_ladder", "rungs": [40, 30]},
        ),
        ([{"count": 5, "reps": 5}], {"name": "wave_531"}),
    ],
)
def test_the_ladder_takes_one_working_group_and_wave_531_count_only(
    sets: list[dict[str, Any]], scheme: dict[str, Any]
) -> None:
    exercise = "assisted_pull_up" if scheme["name"] == "assistance_ladder" else "bb_bench_press"

    assert keyed(one_line(exercise=exercise, sets=sets, scheme=scheme, start_load=40)) == [
        f"set_groups_off_scheme@line:push/{exercise}"
    ]


def test_wave_531_with_count_only_and_hold_with_activation_only_pass() -> None:
    assert keyed(one_line(sets=[{"count": 3}], scheme={"name": "wave_531"})) == []
    activation = [{"count": 2, "type": "activation", "reps": [6, 8], "rpe": 5}]
    assert (
        keyed(
            one_line(exercise="pull_up", sets=activation, scheme={"name": "hold"}, start_load=None)
        )
        == []
    )


def test_a_conditioning_session_runs_a_session_scheme_and_its_lines_hold() -> None:
    emom = {
        "name": "emom_density",
        "minutes": 12,
        "minutes_cap": 16,
        "minutes_step": 2,
        "reps": {"kb_swing": 12},
        "reps_cap": {"kb_swing": 15},
        "rpe_target": 7,
    }
    session = a_session(
        "swings",
        a_line("pull_up", scheme={"name": "hold"}, start_load=None),
        kind="conditioning",
        tier="optional",
        cadence="standing",
        scheme=emom,
    )

    assert keyed(a_draft(session)) == []
    assert keyed(a_draft({**session, "scheme": {"name": "linear"}})) == [
        "unknown_scheme@session:swings"
    ]


def test_an_acknowledgement_of_a_warning_adopt_did_not_raise_is_unmatched() -> None:
    key = "scheme_off_emphasis@line:push/bb_bench_press"
    entry = {"flag": key, "because": "coach_judgement", "text": "x"}
    raised = a_context(raised_warnings=frozenset({key}))

    assert keyed(a_draft(acknowledge=[entry]), raised) == []
    assert keyed(a_draft(acknowledge=[entry])) == ["acknowledgement_unmatched@version:pv-1"]


def test_an_adopt_warning_adopt_cannot_raise_yet_passes_while_it_names_the_draft() -> None:
    entry = {
        "flag": "scheme_change_off_signal@line:push/bb_bench_press",
        "because": "coach_judgement",
        "text": "x",
    }

    assert keyed(a_draft(acknowledge=[entry])) == []
    stale = {**entry, "flag": "scheme_change_off_signal@line:push/pull_up"}
    assert keyed(a_draft(acknowledge=[stale])) == ["acknowledgement_unmatched@version:pv-1"]


def test_every_violation_is_reported_in_one_run() -> None:
    draft = a_draft(
        a_session("push", a_line(start_load=61), a_line("db_curl", start_load=None)),
        location="home",
    )

    assert keyed(draft) == [
        "start_load_off_rack@line:push/bb_bench_press",
        "start_load_missing@line:push/db_curl",
    ]


TOP_BACKOFF_SETS = [{"count": 1, "reps": 5, "rpe": 8}, {"count": 3, "reps": 5}]
EMOM = {
    "name": "emom_density",
    "minutes": 12,
    "minutes_cap": 16,
    "minutes_step": 2,
    "reps": {"kb_swing": 12},
    "reps_cap": {"kb_swing": 15},
    "rpe_target": 7,
}


def an_emom_draft(**params: Any) -> dict[str, Any]:
    return a_draft(
        a_session(
            "swings",
            a_line("pull_up", scheme={"name": "hold"}, start_load=None),
            kind="conditioning",
            tier="optional",
            cadence="standing",
            scheme={**EMOM, **params},
        )
    )


LINE = "line:push/bb_bench_press"
SWINGS = "session:swings"


@pytest.mark.parametrize(
    ("draft", "scope", "param"),
    [
        (
            one_line(scheme={"name": "linear", "misses_before_reset": 1.5}),
            LINE,
            "misses_before_reset",
        ),
        (
            one_line(scheme={"name": "linear", "misses_before_reset": 0}),
            LINE,
            "misses_before_reset",
        ),
        (one_line(scheme={"name": "linear", "reset_factor": 3}), LINE, "reset_factor"),
        (one_line(scheme={"name": "linear", "reset_factor": "0.9"}), LINE, "reset_factor"),
        (
            one_line(sets=TOP_BACKOFF_SETS, scheme={"name": "top_backoff", "pct_of_top": 850}),
            LINE,
            "pct_of_top",
        ),
        (
            one_line(sets=TOP_BACKOFF_SETS, scheme={"name": "top_backoff", "pct_of_top": "eighty"}),
            LINE,
            "pct_of_top",
        ),
        (
            one_line(
                exercise="assisted_pull_up",
                sets=[{"count": 3, "reps": 8, "rpe": 8}],
                scheme={"name": "assistance_ladder", "rungs": [20, 30]},
                start_load=20,
            ),
            "line:push/assisted_pull_up",
            "rungs",
        ),
        (an_emom_draft(rpe_target=0), SWINGS, "rpe_target"),
        (an_emom_draft(reps=12), SWINGS, "reps"),
        (an_emom_draft(reps={"kb_swing": "twelve"}), SWINGS, "reps"),
        (an_emom_draft(reps_cap=True), SWINGS, "reps_cap"),
        (an_emom_draft(minutes=True), SWINGS, "minutes"),
    ],
)
def test_a_scheme_param_of_the_wrong_type_names_the_param(
    draft: dict[str, Any], scope: str, param: str
) -> None:
    [flag] = flags_of(draft)

    assert flag.key == f"unknown_scheme@{scope}"
    assert flag.params["param"] == param


@pytest.mark.parametrize(
    "draft",
    [
        one_line(scheme={"name": "linear", "misses_before_reset": 3, "reset_factor": 0.95}),
        one_line(sets=TOP_BACKOFF_SETS, scheme={"name": "top_backoff", "pct_of_top": 100}),
        an_emom_draft(reps_cap=15, rpe_target=7.5),
    ],
)
def test_a_scheme_param_of_the_right_type_passes(draft: dict[str, Any]) -> None:
    assert keyed(draft) == []
