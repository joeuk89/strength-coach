from dataclasses import replace
from typing import Any

import pytest
from support.program_drafts import a_draft, a_ladder_line, a_line, a_rung, a_session, toml

from coach.core.flag import Flag
from coach.core.goal import Goal
from coach.core.program.checks import AdoptContext, violations
from coach.core.program.parse import parse_program_draft

BODYWEIGHT: dict[str, object] = {"load_mode": "bodyweight", "equipment_kind": "bodyweight"}
DURATION: dict[str, object] = {"load_mode": "duration", "equipment_kind": "bodyweight"}
LIBRARY: dict[str, dict[str, object]] = {
    "plank": DURATION,
    "side_plank": DURATION,
    "dead_bug": DURATION,
    "push_up": BODYWEIGHT,
}
CONTEXT = AdoptContext(
    version_id="pv-1",
    library=LIBRARY,
    racks={"home": {}},
    goal=Goal(kind="hypertrophy", because="first goal", priority_lifts=(), why=""),
)
REPS = [{"count": 3, "reps": 8, "rpe": 7}]


def flags_of(*lines: dict[str, Any], **draft: Any) -> list[Flag]:
    parsed = parse_program_draft(toml(a_draft(a_session("core", *lines), **draft)), file="d.toml")
    return list(violations(parsed.form, CONTEXT, parsed.unknown_keys))


def keyed(*lines: dict[str, Any], **draft: Any) -> list[str]:
    return [flag.key for flag in flags_of(*lines, **draft)]


def test_a_ladder_of_library_and_declared_exercises_raises_nothing() -> None:
    line = a_ladder_line("plank", a_rung(), a_rung("side_plank"), a_rung("custom_board"))
    declared = {"custom_board": {"name": "Board", **DURATION}}

    assert keyed(line, exercise=declared) == []


def test_a_rung_naming_an_exercise_nowhere_is_rung_exercise_unknown() -> None:
    [flag] = flags_of(a_ladder_line("plank", a_rung(), a_rung("custom_board")))

    assert flag.key == "rung_exercise_unknown@version:pv-1"
    assert flag.params == {"rung": 2, "exercise_id": "custom_board"}


def test_a_one_rung_ladder_is_too_short() -> None:
    [flag] = flags_of(a_ladder_line("plank", a_rung()))

    assert flag.key == "ladder_too_short@line:core/plank"
    assert flag.params == {"rungs": 1}


@pytest.mark.parametrize(
    ("line", "rung", "key"),
    [
        (a_ladder_line("plank", a_rung(), a_rung("side_plank", advance={"reps": 8})), 2, "reps"),
        (
            a_ladder_line(
                "push_up", a_rung(sets=REPS, advance={"duration_s": 60}), a_rung("plank")
            ),
            1,
            "duration_s",
        ),
        (
            a_ladder_line(
                "plank", a_rung(advance={"manual": True, "exposures": 2}), a_rung("dead_bug")
            ),
            1,
            "manual",
        ),
        (a_ladder_line(advance={"reps": 8}), 1, "reps"),
    ],
)
def test_a_criterion_key_the_rung_cannot_read_is_off_the_rung(
    line: dict[str, Any], rung: int, key: str
) -> None:
    [flag] = flags_of(line)

    assert flag.key == f"advance_criterion_off_rung@line:core/{line['exercise']}"
    assert flag.params == {"rung": rung, "criterion_key": key}


def test_manual_on_a_rung_stands_alone_over_the_ladder_criterion() -> None:
    line = a_ladder_line(
        "plank", a_rung(), a_rung("dead_bug", advance={"manual": True}), advance={"exposures": 3}
    )

    assert keyed(line) == []


def test_a_rung_group_without_rpe_is_rpe_missing() -> None:
    rung = a_rung("side_plank", sets=[{"count": 2, "duration_s": 30}])

    [flag] = flags_of(a_ladder_line("plank", a_rung(), rung))

    assert flag.key == "rpe_missing@line:core/plank"
    assert flag.params == {"scheme": "exercise_ladder", "group_index": 1}
    assert "rung 2" in flag.message


def test_two_working_groups_on_a_rung_is_set_groups_off_scheme() -> None:
    groups = [{"count": 2, "duration_s": 30, "rpe": 6}, {"count": 1, "duration_s": 45, "rpe": 7}]

    [flag] = flags_of(a_ladder_line("plank", a_rung(), a_rung("side_plank", sets=groups)))

    assert flag.key == "set_groups_off_scheme@line:core/plank"
    assert flag.params == {
        "scheme": "exercise_ladder",
        "expected_shape": "exactly one working group",
    }


def test_a_warm_up_group_on_a_rung_is_not_allowed() -> None:
    groups = [{"count": 1, "type": "warm_up", "reps": 5}, {"count": 2, "duration_s": 30, "rpe": 6}]

    assert keyed(a_ladder_line("plank", a_rung(sets=groups), a_rung("side_plank"))) == [
        "set_type_not_allowed@line:core/plank"
    ]


def test_a_rung_exercise_another_line_of_the_session_names_is_a_duplicate() -> None:
    [flag] = flags_of(a_line("side_plank", sets=REPS, start_load=None), a_ladder_line())

    assert flag.key == "duplicate_id@version:pv-1"
    assert flag.params == {"session_id": "core", "exercise_id": "side_plank"}


def test_two_rungs_naming_one_exercise_with_equal_sets_and_cues_are_repeated_not_duplicate() -> (
    None
):
    line = a_ladder_line("plank", a_rung(), a_rung("side_plank"), a_rung("side_plank"))

    assert keyed(line) == ["rung_repeated@line:core/plank"]


def test_a_rung_exercise_in_another_session_is_no_duplicate() -> None:
    draft = a_draft(
        a_session("core", a_ladder_line()),
        a_session("more", a_line("side_plank", sets=REPS, start_load=None)),
    )
    parsed = parse_program_draft(toml(draft), file="d.toml")

    assert list(violations(parsed.form, CONTEXT, parsed.unknown_keys)) == []


def test_a_param_outside_the_ladder_row_is_unknown_scheme() -> None:
    [flag] = flags_of(a_ladder_line(stage=1))

    assert flag.key == "unknown_scheme@line:core/plank"
    assert flag.params == {"scheme": "exercise_ladder", "param": "stage"}


def test_a_rung_group_stating_neither_reps_nor_duration_is_set_groups_off_scheme() -> None:
    rung = a_rung("side_plank", sets=[{"count": 2, "rpe": 6}])

    [flag] = flags_of(a_ladder_line("plank", a_rung(), rung))

    assert flag.params == {
        "scheme": "exercise_ladder",
        "expected_shape": "one working group stating reps or duration_s",
    }


def test_a_declared_rung_exercise_with_no_template_is_hevy_template_missing() -> None:
    line = a_ladder_line("plank", a_rung(), a_rung("custom_board"))
    declared = {"custom_board": {"name": "Board", **DURATION}}
    parsed = parse_program_draft(
        toml(a_draft(a_session("core", line), exercise=declared)), file="d.toml"
    )

    [flag] = violations(parsed.form, replace(CONTEXT, hevy_on=True), parsed.unknown_keys)

    assert flag.key == "hevy_template_missing@line:core/plank"
    assert flag.params == {
        "exercise_id": "custom_board",
        "missing_columns": [
            "hevy_title",
            "hevy_exercise_type",
            "hevy_equipment",
            "hevy_muscle_group",
        ],
    }


def test_a_declared_rung_exercise_with_a_bad_template_value_names_the_rung_exercise() -> None:
    line = a_ladder_line("plank", a_rung(), a_rung("custom_board"))
    template = {
        "hevy_title": "Board",
        "hevy_exercise_type": "duration",
        "hevy_equipment": "bands",
        "hevy_muscle_group": "abdominals",
    }
    declared = {"custom_board": {"name": "Board", **DURATION, **template}}
    parsed = parse_program_draft(
        toml(a_draft(a_session("core", line), exercise=declared)), file="d.toml"
    )

    [flag] = violations(parsed.form, replace(CONTEXT, hevy_on=True), parsed.unknown_keys)

    assert flag.key == "hevy_template_value_unknown@line:core/plank"
    assert flag.params == {
        "exercise_id": "custom_board",
        "column": "hevy_equipment",
        "value": "bands",
    }
    assert flag.message.startswith("custom_board has hevy_equipment 'bands'")


@pytest.mark.parametrize(
    ("row", "code", "params"),
    [
        ({"pattern": "balanse"}, "unknown_pattern", {"pattern": "balanse"}),
        (
            {"muscles": {"primary": ["cardio"], "secondary": []}},
            "unknown_muscle",
            {"muscle": "cardio"},
        ),
    ],
)
def test_a_later_rungs_bad_library_row_is_refused_as_a_lines_would_be(
    row: dict[str, object], code: str, params: dict[str, object]
) -> None:
    library = {**LIBRARY, "side_plank": {**DURATION, **row}}
    parsed = parse_program_draft(
        toml(a_draft(a_session("core", a_ladder_line("plank", a_rung(), a_rung("side_plank"))))),
        file="d.toml",
    )

    [flag] = violations(parsed.form, replace(CONTEXT, library=library), parsed.unknown_keys)

    assert flag.key == f"{code}@exercise:side_plank"
    assert flag.params == params


def test_a_rung_exercise_that_is_also_a_line_raises_one_flag_for_it() -> None:
    library = {**LIBRARY, "side_plank": {**DURATION, "pattern": "balanse"}}
    ladder = a_ladder_line("plank", a_rung(), a_rung("side_plank"))
    parsed = parse_program_draft(
        toml(
            a_draft(
                a_session("core", ladder),
                a_session("extra", a_line("side_plank", load_mode="duration")),
            )
        ),
        file="d.toml",
    )

    found = violations(parsed.form, replace(CONTEXT, library=library), parsed.unknown_keys)

    assert [f.key for f in found if f.code == "unknown_pattern"] == [
        "unknown_pattern@exercise:side_plank"
    ]


def a_tempo_rung(cues: str, **fields: Any) -> dict[str, Any]:
    return a_rung(cues=cues, sets=REPS, **fields)


def test_three_rungs_on_one_exercise_differing_only_in_cues_raise_nothing() -> None:
    line = a_ladder_line(
        "push_up",
        a_tempo_rung("lower for 4 s"),
        a_tempo_rung("lower for 6 s", exercise="push_up"),
        a_tempo_rung("lower for 8 s", exercise="push_up"),
    )

    assert keyed(line) == []


def test_two_rungs_on_one_exercise_differing_only_in_sets_raise_nothing() -> None:
    line = a_ladder_line(
        "plank",
        a_rung(cues="hold", sets=[{"count": 2, "duration_s": 30, "rpe": 6}]),
        a_rung("plank", cues="hold", sets=[{"count": 2, "duration_s": 40, "rpe": 6}]),
    )

    assert keyed(line) == []


def test_one_exercise_on_two_lines_of_a_session_is_still_duplicate_id() -> None:
    [flag] = flags_of(
        a_line("push_up", sets=REPS, start_load=None),
        a_line("push_up", sets=REPS, start_load=None),
    )

    assert flag.key == "duplicate_id@version:pv-1"
    assert flag.params == {"session_id": "core", "exercise_id": "push_up"}


def test_a_shared_rung_exercise_on_another_line_of_the_session_is_still_duplicate_id() -> None:
    ladder = a_ladder_line(
        "plank",
        a_rung(cues="short"),
        a_rung("side_plank", cues="short"),
        a_rung("side_plank", cues="long"),
    )

    [flag] = flags_of(ladder, a_line("side_plank", sets=REPS, start_load=None))

    assert flag.key == "duplicate_id@version:pv-1"
    assert flag.params == {"session_id": "core", "exercise_id": "side_plank"}


def test_two_rungs_equal_in_exercise_sets_and_cues_raise_rung_repeated_naming_both() -> None:
    line = a_ladder_line(
        "push_up",
        a_tempo_rung("lower for 4 s"),
        a_tempo_rung("lower for 6 s", exercise="push_up"),
        a_tempo_rung("lower for 6 s", exercise="push_up"),
    )

    [flag] = flags_of(line)

    assert flag.key == "rung_repeated@line:core/push_up"
    assert flag.params == {"rung": 3, "previous_rung": 2}


def test_a_first_rung_leaving_its_exercise_unsaid_still_compares_as_the_lines() -> None:
    line = a_ladder_line("push_up", a_tempo_rung("slow"), a_tempo_rung("slow", exercise="push_up"))

    [flag] = flags_of(line)

    assert flag.params == {"rung": 2, "previous_rung": 1}


def test_a_ladder_may_return_to_an_earlier_shape_since_only_neighbours_compare() -> None:
    line = a_ladder_line(
        "push_up",
        a_tempo_rung("lower for 4 s"),
        a_tempo_rung("lower for 6 s", exercise="push_up"),
        a_tempo_rung("lower for 4 s", exercise="push_up"),
    )

    assert keyed(line) == []


def test_three_identical_rungs_raise_one_rung_repeated_naming_the_first_pair() -> None:
    line = a_ladder_line(
        "push_up",
        a_tempo_rung("slow"),
        a_tempo_rung("slow", exercise="push_up"),
        a_tempo_rung("slow", exercise="push_up"),
    )

    [flag] = flags_of(line)

    assert flag.params == {"rung": 2, "previous_rung": 1}


def test_equal_sets_and_cues_on_another_exercise_are_not_repeated() -> None:
    line = a_ladder_line("plank", a_rung(cues="hold"), a_rung("side_plank", cues="hold"))

    assert keyed(line) == []


def test_rungs_differing_only_in_their_criterion_are_repeated() -> None:
    line = a_ladder_line(
        "push_up",
        a_tempo_rung("slow"),
        a_tempo_rung("slow", exercise="push_up", advance={"exposures": 3}),
    )

    [flag] = flags_of(line)

    assert flag.code == "rung_repeated"


def test_a_rung_differing_only_in_warm_ups_is_refused_as_a_set_type() -> None:
    warmed = [{"type": "warm_up", "count": 1, "reps": 5}, *REPS]
    line = a_ladder_line(
        "push_up",
        a_tempo_rung("slow"),
        a_rung("push_up", cues="slow", sets=warmed),
    )

    assert [flag.code for flag in flags_of(line)] == ["set_type_not_allowed"]


def test_a_shared_declared_exercise_with_no_template_raises_one_flag_for_the_line() -> None:
    parsed = parse_program_draft(
        toml(
            a_draft(
                a_session(
                    "core",
                    a_ladder_line(
                        "board",
                        a_rung(cues="short"),
                        a_rung("board", cues="long"),
                        a_rung("board", cues="longest"),
                    ),
                ),
                exercise={"board": {"name": "Board", **DURATION}},
            )
        ),
        file="d.toml",
    )

    found = violations(parsed.form, replace(CONTEXT, hevy_on=True), parsed.unknown_keys)

    assert [flag.code for flag in found] == ["hevy_template_missing"]


def test_a_shared_unknown_rung_exercise_raises_one_flag() -> None:
    line = a_ladder_line(
        "plank", a_rung(), a_rung("board", cues="short"), a_rung("board", cues="long")
    )

    assert [flag.code for flag in flags_of(line)] == ["rung_exercise_unknown"]
