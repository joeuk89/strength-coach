from typing import Any

from support.program_drafts import a_draft, a_line, a_session, toml

from coach.core.flag import Flag
from coach.core.program.checks import AdoptContext, violations
from coach.core.program.parse import parse_program_draft
from coach.core.rack import IncrementRack

CARRY: dict[str, object] = {
    "name": "Farmer's carry",
    "load_mode": "per_hand_x2",
    "equipment_kind": "dumbbell",
    "pattern": "carry",
    "muscles": {"primary": ["forearms"], "secondary": []},
    "hevy_title": "Farmer's Carry (Timed)",
    "hevy_exercise_type": "weight_duration",
    "hevy_equipment": "dumbbell",
    "hevy_muscle_group": "forearms",
}
CONTEXT = AdoptContext(
    version_id="pv-1",
    library={"bb_bench_press": {"load_mode": "total", "equipment_kind": "barbell"}},
    racks={
        "home": {
            "barbell": IncrementRack(2.5, base=20),
            "dumbbell": IncrementRack(5, base=10),
        }
    },
)


def carrying(sets: list[dict[str, Any]] | None = None, **columns: Any) -> dict[str, Any]:
    line = a_line(
        "farmers_carry",
        sets=sets or [{"count": 3, "duration_s": 30, "rpe": 8}],
        scheme={"name": "timed_load"},
        start_load=40,
    )
    exercise = {**CARRY, **columns}
    return a_draft(
        a_session("push", a_line(), line),
        exercise={"farmers_carry": {k: v for k, v in exercise.items() if v is not None}},
    )


def flags_of(draft: dict[str, Any]) -> list[Flag]:
    parsed = parse_program_draft(toml(draft), file="d.toml")
    return [
        flag
        for flag in violations(parsed.form, CONTEXT, parsed.unknown_keys)
        if flag.code != "goal_missing"
    ]


def test_a_timed_load_line_on_a_weight_duration_template_raises_nothing() -> None:
    assert flags_of(carrying()) == []


def test_a_timed_load_line_on_a_distance_template_is_template_untimed() -> None:
    [flag] = flags_of(carrying(hevy_exercise_type="short_distance_weight"))

    assert flag.key == "template_untimed@line:push/farmers_carry"
    assert flag.severity == "violation"
    assert flag.params == {
        "exercise_id": "farmers_carry",
        "hevy_exercise_type": "short_distance_weight",
        "needs": "weight_duration",
    }


def test_a_timed_load_line_on_an_exercise_with_no_known_template_type_is_template_untimed() -> None:
    [flag] = flags_of(carrying(hevy_exercise_type=None))

    assert (flag.code, flag.params["hevy_exercise_type"]) == ("template_untimed", None)


def test_a_timed_load_group_stating_reps_is_off_scheme() -> None:
    [flag] = flags_of(carrying([{"count": 3, "reps": 10, "rpe": 8}]))

    assert flag.code == "set_groups_off_scheme"
    assert flag.params["expected_shape"] == "exactly one working group stating duration_s"


def test_a_timed_load_group_with_no_rpe_target_is_rpe_missing() -> None:
    [flag] = flags_of(carrying([{"count": 3, "duration_s": 30}]))

    assert flag.code == "rpe_missing"
