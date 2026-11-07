from typing import Any

from support.program_drafts import a_draft, a_line, a_session, toml

from coach.core.flag import Flag
from coach.core.program.checks import AdoptContext, violations
from coach.core.program.parse import parse_program_draft
from coach.core.rack import IncrementRack

CALF_HOLD: dict[str, object] = {
    "name": "Calf raise hold",
    "load_mode": "duration",
    "equipment_kind": "bodyweight",
    "pattern": "calf_raise",
    "muscles": {"primary": ["calves"], "secondary": []},
    "hevy_title": "Calf Raise Hold",
    "hevy_exercise_type": "duration",
    "hevy_equipment": "other",
    "hevy_muscle_group": "calves",
}
HEVY_ON = AdoptContext(
    version_id="pv-1",
    library={"bb_bench_press": {"load_mode": "total", "equipment_kind": "barbell"}},
    racks={"home": {"barbell": IncrementRack(2.5, base=20)}},
    hevy_on=True,
)


def declaring(**columns: Any) -> dict[str, Any]:
    exercise = {**CALF_HOLD, **columns}
    hold = a_line(
        "calf_hold", sets=[{"count": 3, "duration_s": 30}], scheme={"name": "hold"}, start_load=None
    )
    return a_draft(
        a_session("push", a_line(), hold),
        exercise={"calf_hold": {k: v for k, v in exercise.items() if v is not None}},
    )


def flags_of(draft: dict[str, Any], context: AdoptContext = HEVY_ON) -> list[Flag]:
    parsed = parse_program_draft(toml(draft), file="d.toml")
    return [
        flag
        for flag in violations(parsed.form, context, parsed.unknown_keys)
        if flag.code != "goal_missing"
    ]


def test_a_new_exercise_with_values_hevy_accepts_raises_nothing() -> None:
    assert flags_of(declaring()) == []


def test_an_equipment_hevy_does_not_accept_is_hevy_template_value_unknown() -> None:
    [flag] = flags_of(declaring(hevy_equipment="bands"))

    assert flag.key == "hevy_template_value_unknown@line:push/calf_hold"
    assert flag.severity == "violation"
    assert flag.params == {
        "exercise_id": "calf_hold",
        "column": "hevy_equipment",
        "value": "bands",
    }


def test_two_bad_columns_raise_two_flags() -> None:
    flags = flags_of(declaring(hevy_exercise_type="time", hevy_muscle_group="calf"))

    assert [(f.code, f.params["column"], f.params["value"]) for f in flags] == [
        ("hevy_template_value_unknown", "hevy_exercise_type", "time"),
        ("hevy_template_value_unknown", "hevy_muscle_group", "calf"),
    ]


def test_values_match_exactly_with_no_case_folding() -> None:
    [flag] = flags_of(declaring(hevy_equipment="Barbell"))

    assert flag.params["value"] == "Barbell"


def test_a_missing_column_is_hevy_template_missing_only() -> None:
    [flag] = flags_of(declaring(hevy_equipment=None))

    assert flag.code == "hevy_template_missing"
    assert flag.params["missing_columns"] == ["hevy_equipment"]


def test_a_free_text_title_is_not_checked() -> None:
    assert flags_of(declaring(hevy_title="anything at all")) == []


def test_without_hevy_or_with_a_template_id_no_value_is_checked() -> None:
    bad = {"hevy_equipment": "bands", "hevy_muscle_group": "calf"}

    hevy_off = AdoptContext(version_id="pv-1", library=HEVY_ON.library, racks=HEVY_ON.racks)
    assert flags_of(declaring(**bad), hevy_off) == []
    templated = {**HEVY_ON.library, "calf_hold": {"hevy_template_id": "C0FFEE01"}}
    with_template = AdoptContext(
        version_id="pv-1", library=templated, racks=HEVY_ON.racks, hevy_on=True
    )
    assert flags_of(declaring(**bad), with_template) == []
