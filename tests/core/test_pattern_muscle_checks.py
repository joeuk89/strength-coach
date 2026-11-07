from typing import Any

from support.program_drafts import a_draft, a_line, a_session, toml

from coach.core.program.checks import AdoptContext, violations
from coach.core.program.parse import parse_program_draft
from coach.core.rack import IncrementRack

BALANCE: dict[str, object] = {
    "name": "Single-leg balance",
    "load_mode": "duration",
    "equipment_kind": "bodyweight",
    "pattern": "balance",
    "muscles": {"primary": [], "secondary": []},
}
CONTEXT = AdoptContext(
    version_id="pv-1",
    library={
        "bb_bench_press": {
            "load_mode": "total",
            "equipment_kind": "barbell",
            "pattern": "horizontal_push",
            "muscles": {"primary": ["chest"], "secondary": ["triceps"]},
        }
    },
    racks={"home": {"barbell": IncrementRack(2.5, base=20)}},
)


def keyed(draft: dict[str, Any], context: AdoptContext = CONTEXT) -> list[str]:
    parsed = parse_program_draft(toml(draft), file="d.toml")
    return [
        flag.key
        for flag in violations(parsed.form, context, parsed.unknown_keys)
        if flag.code != "goal_missing"
    ]


def declaring(**fields: Any) -> dict[str, Any]:
    hold = {"name": "hold"}
    line = a_line(
        "balance_hold", sets=[{"count": 3, "duration_s": 30}], scheme=hold, start_load=None
    )
    return a_draft(
        a_session("push", a_line(), line), exercise={"balance_hold": {**BALANCE, **fields}}
    )


def test_a_declared_exercise_with_a_registry_pattern_passes() -> None:
    assert keyed(declaring()) == []


def test_a_declared_exercise_with_a_misspelled_pattern_is_unknown_pattern() -> None:
    assert keyed(declaring(pattern="balanse")) == ["unknown_pattern@exercise:balance_hold"]


def test_a_declared_muscle_outside_the_registry_is_unknown_muscle() -> None:
    draft = declaring(muscles={"primary": ["quads"], "secondary": []})

    assert keyed(draft) == ["unknown_muscle@exercise:balance_hold"]


def test_a_declared_secondary_muscle_is_checked_too() -> None:
    draft = declaring(muscles={"primary": ["glutes"], "secondary": ["full_body"]})

    assert keyed(draft) == ["unknown_muscle@exercise:balance_hold"]


def test_a_declared_registry_muscle_passes() -> None:
    assert keyed(declaring(muscles={"primary": ["quadriceps"], "secondary": []})) == []


def test_empty_muscle_lists_pass() -> None:
    assert keyed(declaring(muscles={"primary": [], "secondary": []})) == []


def test_an_estimated_sets_key_outside_the_registry_is_unknown_muscle() -> None:
    pt = a_session("pt", kind="coach_led", line=None, estimated_sets={"chest": 4, "chets": 4})

    assert keyed(a_draft(a_session("push"), pt)) == ["unknown_muscle@session:pt"]


def test_registry_estimated_sets_pass() -> None:
    pt = a_session("pt", kind="coach_led", line=None, estimated_sets={"chest": 4, "lats": 4})

    assert keyed(a_draft(a_session("push"), pt)) == []


def test_a_library_row_a_line_references_is_checked_at_adopt() -> None:
    stale = {"pattern": "push", "muscles": {"primary": ["cardio"], "secondary": []}}
    library = {"bb_bench_press": {**CONTEXT.library["bb_bench_press"], **stale}}
    context = AdoptContext(version_id="pv-1", library=library, racks=CONTEXT.racks)

    assert keyed(a_draft(), context) == [
        "unknown_pattern@exercise:bb_bench_press",
        "unknown_muscle@exercise:bb_bench_press",
    ]


def test_a_library_row_the_draft_does_not_reference_is_left_alone() -> None:
    library = {**CONTEXT.library, "old_row": {"pattern": "push"}}
    context = AdoptContext(version_id="pv-1", library=library, racks=CONTEXT.racks)

    assert keyed(a_draft(), context) == []
