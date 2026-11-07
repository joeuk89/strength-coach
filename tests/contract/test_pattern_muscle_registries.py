from pathlib import Path

from support.name_lists import name_lists

from coach.core.registries.program import (
    COMPOUND_PATTERNS,
    DOSED_MUSCLES,
    HEAVY_PATTERNS,
    MUSCLES,
    PATTERNS,
)

SRC = Path(__file__).resolve().parents[2] / "src"


def test_the_heavy_patterns_are_squat_and_hinge() -> None:
    assert HEAVY_PATTERNS == ("squat", "hinge")


def test_the_compound_patterns_are_the_seven_multi_joint_ones() -> None:
    assert set(COMPOUND_PATTERNS) == {
        "squat",
        "hinge",
        "lunge",
        "horizontal_push",
        "vertical_push",
        "horizontal_pull",
        "vertical_pull",
    }


def test_the_dosed_muscles_are_the_thirteen_in_dose_order() -> None:
    assert DOSED_MUSCLES == (
        "chest",
        "lats",
        "upper_back",
        "front_delts",
        "side_delts",
        "rear_delts",
        "biceps",
        "triceps",
        "quadriceps",
        "hamstrings",
        "glutes",
        "calves",
        "abdominals",
    )


def test_no_module_but_the_registry_lists_pattern_or_muscle_names() -> None:
    names = {*PATTERNS.names(), *MUSCLES.names()}

    assert name_lists(SRC, names) == []


def test_a_planted_literal_list_of_pattern_names_is_found(tmp_path: Path) -> None:
    module = tmp_path / "coach" / "core" / "rules.py"
    module.parent.mkdir(parents=True)
    module.write_text('A = ("squat", "hinge")\nB = ("core", "optional")\n', encoding="utf-8")

    assert name_lists(tmp_path, {"squat", "hinge", "core"}) == ["coach/core/rules.py:1"]
